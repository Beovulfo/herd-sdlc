#!/usr/bin/env python3
"""Report what a run's sandbox blocked and prove the run used the isolation settings.

  python3 leak_audit.py RUN_LOG.jsonl --work DIR [--plugin DIR] [--settings FILE] [--task TASK]

Exit 0 and "leak audit: clean", or exit 1 with one line per finding. The audit does not read
paths from commands: shell text cannot be parsed completely. The sandbox is the guard and
run_leg.py --selftest proves it. The audit reads only structured fields of the log: tool results
that report a sandbox violation or a denial, WebFetch and WebSearch calls, and the settings file.
--plugin is accepted for older command lines and is not used. The work folder must hold no file
named like a hidden verifier file of any task: a copy there is a finding. --task (a name or a path such
as examples/bus-transfer/) names the run's task and is refused when unknown; every task's hidden files
are checked either way, because a leaked verifier of another task is a leak too.
"""
import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_leg  # noqa: E402

BLOCK_MARKERS = ("Operation not permitted", "denied by your permission settings")
VIOLATIONS_RE = re.compile(r"<sandbox_violations>(.*?)</sandbox_violations>", re.S)
NETWORK_TOOLS = ("WebFetch", "WebSearch")


@dataclass
class Finding:
    tool: str
    detail: str
    blocked: bool


def _text(content):
    if isinstance(content, str):
        return content
    return " ".join(b.get("text", "") for b in content if isinstance(b, dict)) if isinstance(content, list) else ""


def check_settings(path):  # noqa: C901
    """Findings for isolation settings that are missing or weaker than run_leg.py writes."""
    try:
        s = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [Finding("settings", f"not isolated: cannot read settings {path}", False)]
    if not isinstance(s, dict):
        return [Finding("settings", f"not isolated: settings {path} is not an object", False)]

    def get(obj, *keys):
        for k in keys:
            obj = obj.get(k) if isinstance(obj, dict) else None
        return obj

    def has(obj, keys, item):
        v = get(obj, *keys)
        return isinstance(v, list) and item in v

    missing = []
    if get(s, "sandbox", "enabled") is not True:
        missing.append("sandbox.enabled is not true")
    if get(s, "sandbox", "allowUnsandboxedCommands") is not False:
        missing.append("sandbox.allowUnsandboxedCommands is not false")
    if not has(s, ("sandbox", "filesystem", "denyRead"), "~/"):
        missing.append('sandbox.filesystem.denyRead lacks "~/"')
    for item in ("Read(~/**)", "WebFetch", "WebSearch"):
        if not has(s, ("permissions", "deny"), item):
            missing.append(f'permissions.deny lacks "{item}"')
    return [Finding("settings", f"not isolated: {m}", False) for m in missing]


def check_work(work, task=None):
    """Findings for files under work named like the hidden verifier files of any task. A given task must be known."""
    if task:
        run_leg.resolve_task(task)
    names = run_leg.PLANTED_NAMES
    found = []
    for cur, _dirs, files in os.walk(work, onerror=lambda e: None):
        found += [os.path.join(cur, f) for f in files if f in names]
    return [Finding("work", f"hidden verifier file in the work folder: {p}", False) for p in sorted(found)]


def audit(log_path, work, plugin=None, settings=None, task=None):  # noqa: C901
    settings = settings or Path(work).resolve().parent / "settings.json"
    findings = check_settings(settings) + check_work(work, task)
    calls = {}
    with open(log_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            content = (ev.get("message") or {}).get("content") if isinstance(ev, dict) else None
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if ev.get("type") == "assistant" and block.get("type") == "tool_use":
                    name = block.get("name", "?")
                    calls[block.get("id")] = name
                    if name in NETWORK_TOOLS:
                        findings.append(Finding(name, "network tool call", False))
                elif ev.get("type") == "user" and block.get("type") == "tool_result":
                    text = _text(block.get("content"))
                    name = calls.get(block.get("tool_use_id"), "?")
                    for body in VIOLATIONS_RE.findall(text):
                        for v in (x.strip() for x in body.splitlines()):
                            if v:
                                findings.append(Finding(name, f"sandbox violation: {v}", True))
                    for m in BLOCK_MARKERS:
                        if m in text:
                            findings.append(Finding(name, f"{m}", True))
    return findings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("log")
    ap.add_argument("--work", required=True)
    ap.add_argument("--plugin")
    ap.add_argument("--settings")
    ap.add_argument("--task")
    a = ap.parse_args(argv)
    try:
        found = audit(a.log, a.work, a.plugin, a.settings, a.task)
    except ValueError as e:
        print(f"leak audit: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"leak audit: cannot read {a.log}: {e.strerror}", file=sys.stderr)
        return 2
    for f in found:
        print(f"{f.tool}\t{f.detail}\t{'blocked' if f.blocked else 'not blocked'}")
    if not found:
        print("leak audit: clean")
        return 0
    print(f"leak audit: {len(found)} findings ({sum(f.blocked for f in found)} blocked)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
