#!/usr/bin/env python3
"""herd: the evidence harness. Standard library only, Python 3.13+.

A task is `.herd/tasks/<slug>/task.toml`: a goal plus success criteria, each with a
`check` command. `herd verify` runs the checks and stores evidence. `herd gate` (the
Stop hook) refuses to let the agent finish without fresh, passing evidence.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import herd_triage  # noqa: E402

SELF = os.path.abspath(__file__)
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,40}")
SOURCES = ("human", "agent-proposed")
TAIL_CHARS = 2000
DEFAULT_TIMEOUT = 300
MAX_BLOCKS = 3  # ponytail: circuit breaker so a stuck agent can stop and escalate instead of looping

TEMPLATE = '''goal = {goal}

# One [[criteria]] block per success criterion. `check` is a shell command; exit 0 means pass.
# source = "human" for criteria the human wrote, "agent-proposed" for ones you added.
# An empty check is allowed: the criterion is then `unchecked` and never counts as met.
#
# [[criteria]]
# id = "C1"
# text = "Given ..., when ..., then ..."
# source = "agent-proposed"
# check = "python3 -m unittest"
'''


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dir(root, slug):
    return Path(root) / ".herd" / "tasks" / slug


def active_slug(root):
    p = Path(root) / ".herd" / "active"
    return p.read_text().strip() if p.exists() else None


# ---- task -----------------------------------------------------------------

def init_task(root, slug, goal):
    if not SLUG.fullmatch(slug):
        raise ValueError("slug must be lower-case letters, digits and dashes (max 41 chars)")
    d = _dir(root, slug)
    if d.exists():
        raise ValueError(f"task {slug} already exists")
    d.mkdir(parents=True)
    (d / "task.toml").write_text(TEMPLATE.format(goal=json.dumps(goal)))
    (Path(root) / ".herd" / "active").write_text(slug + "\n")


def load_task(root, slug):
    return tomllib.loads((_dir(root, slug) / "task.toml").read_text())


def validate_task(task):
    errs, seen = [], set()
    if not str(task.get("goal", "")).strip():
        errs.append("goal is empty")
    crit = task.get("criteria", [])
    if not crit:
        errs.append("no criteria: add at least one [[criteria]] block")
    for c in crit:
        cid = c.get("id", "?")
        if not c.get("id"):
            errs.append("a criterion has no id")
        if cid in seen:
            errs.append(f"duplicate criterion id {cid}")
        seen.add(cid)
        if not str(c.get("text", "")).strip():
            errs.append(f"{cid}: text is empty")
        if c.get("source") not in SOURCES:
            errs.append(f"{cid}: source must be one of {SOURCES}")
        if not isinstance(c.get("check"), str):
            errs.append(f"{cid}: check is missing (use an empty string for unchecked)")
    return errs


# ---- evidence -------------------------------------------------------------

def _git(root, *args):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True)
    return p.stdout if p.returncode == 0 else b""


def fingerprint(root):
    """Hash of HEAD, tracked changes and untracked file contents, ignoring .herd/."""
    h = hashlib.sha1()
    h.update(_git(root, "rev-parse", "HEAD"))
    h.update(_git(root, "diff", "HEAD", "--", ".", ":!.herd"))
    for name in sorted(_git(root, "ls-files", "--others", "--exclude-standard", "--", ".", ":!.herd").decode().splitlines()):
        h.update(name.encode())
        try:
            h.update((Path(root) / name).read_bytes())
        except OSError:
            pass
    return h.hexdigest()


def _task_sha(root, slug):
    return hashlib.sha1((_dir(root, slug) / "task.toml").read_bytes()).hexdigest()


def run_check(root, check, timeout):
    try:
        p = subprocess.run(check, shell=True, cwd=root, capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, out[-TAIL_CHARS:]
    except subprocess.TimeoutExpired:
        return None, f"timeout after {timeout}s"


def verify(root, slug):
    task = load_task(root, slug)
    errs = validate_task(task)
    if errs:
        raise ValueError("; ".join(errs))
    results = []
    for c in task["criteria"]:
        r = {"id": c["id"], "text": c["text"], "source": c["source"], "check": c["check"],
             "exit_code": None, "output_tail": "", "status": "unchecked"}
        if c["check"].strip():
            r["exit_code"], r["output_tail"] = run_check(root, c["check"], c.get("timeout_s", DEFAULT_TIMEOUT))
            r["status"] = "passing" if r["exit_code"] == 0 else "failing"
        results.append(r)
    summary = {s: sum(r["status"] == s for r in results) for s in ("passing", "failing", "unchecked")}
    head = _git(root, "rev-parse", "HEAD").decode().strip() or "none"
    dirty = bool(_git(root, "status", "--porcelain", "--", ".", ":!.herd").strip())
    ev = {"task": slug, "goal": task["goal"], "at": now(), "head": head, "dirty": dirty,
          "fingerprint": fingerprint(root), "task_sha": _task_sha(root, slug),
          "results": results, "summary": summary}
    (_dir(root, slug) / "evidence.json").write_text(json.dumps(ev, indent=2))
    return ev


def load_evidence(root, slug):
    p = _dir(root, slug) / "evidence.json"
    return json.loads(p.read_text()) if p.exists() else None


def report(ev):
    s = ev["summary"]
    lines = [f"# Evidence: {ev['task']}", "", f"Goal: {ev['goal']}",
             f"Run at {ev['at']} on commit {ev['head'][:12]}" + (" plus uncommitted changes" if ev.get("dirty") else ""),
             f"Result: {s['passing']} passing, {s['failing']} failing, {s['unchecked']} unchecked", "",
             "| id | status | source | check |", "| --- | --- | --- | --- |"]
    for r in ev["results"]:
        lines.append(f"| {r['id']} | {r['status']} | {r['source']} | `{r['check'] or '-'}` |")
    for r in ev["results"]:
        if r["status"] == "failing":
            lines += ["", f"Failing {r['id']} (exit {r['exit_code']}), output tail:", "```", r["output_tail"].strip(), "```"]
    if s["unchecked"]:
        lines += ["", "Unchecked criteria have no runnable check and are never counted as met."]
    return "\n".join(lines) + "\n"


# ---- gate -----------------------------------------------------------------

def problems(root, slug):
    """Reasons the task is not done, from stored evidence. Empty list means done."""
    ev = load_evidence(root, slug)
    if ev is None:
        return ["no evidence yet: run `herd verify`"]
    if ev["task_sha"] != _task_sha(root, slug) or ev["fingerprint"] != fingerprint(root):
        return ["evidence is stale (the workspace or task.toml changed after the last verify): run `herd verify`"]
    out = [f"{r['id']} is failing: {r['text']}" for r in ev["results"] if r["status"] == "failing"]
    if not ev["summary"]["passing"] and not out:
        out.append("no passing criterion: give at least one criterion a runnable check")
    return out


def gate(root, hook):
    """Stop hook. None allows the stop; a dict blocks it with a reason for the agent."""
    slug = active_slug(root)
    if not slug or not _dir(root, slug).exists():
        return None
    counter = _dir(root, slug) / "gate_blocks"
    probs = problems(root, slug)
    if not probs:
        counter.unlink(missing_ok=True)
        return None
    n = int(counter.read_text()) if counter.exists() else 0
    if n >= MAX_BLOCKS:
        return None
    counter.write_text(str(n + 1))
    cmd = f"python3 {SELF} verify"
    reason = (f"Herd task `{slug}` is not done ({n + 1}/{MAX_BLOCKS} stop attempts blocked). "
              + "; ".join(probs) + f". Run `{cmd}` after fixing. If you are stuck, ask the human one question and stop.")
    return {"decision": "block", "reason": reason}


# ---- cli ------------------------------------------------------------------

def _slug_arg(root, args):
    slug = args[0] if args else active_slug(root)
    if not slug:
        sys.exit("no active task: run `herd init <slug> \"<goal>\"`")
    return slug


def main(argv):
    root = Path.cwd()
    cmd, args = (argv[0], argv[1:]) if argv else ("status", [])
    try:
        if cmd == "init":
            init_task(root, args[0], args[1])
            print(f"created .herd/tasks/{args[0]}/task.toml (commented template): add criteria with checks, then run `herd check`")
        elif cmd == "check":
            errs = validate_task(load_task(root, _slug_arg(root, args)))
            print("\n".join(errs) if errs else "ok")
            return 1 if errs else 0
        elif cmd == "verify":
            ev = verify(root, _slug_arg(root, args))
            s = ev["summary"]
            print(f"{s['passing']} passing, {s['failing']} failing, {s['unchecked']} unchecked")
            for r in ev["results"]:
                print(f"  {r['id']} {r['status']}: {r['text']}")
            return 1 if s["failing"] else 0
        elif cmd == "status":
            slug = _slug_arg(root, args)
            ev = load_evidence(root, slug)
            print(report(ev) if ev else f"task {slug}: no evidence yet")
            probs = problems(root, slug)
            print("not done: " + "; ".join(probs) if probs else "done: evidence is fresh and passing")
        elif cmd == "done":
            slug = _slug_arg(root, args)
            probs = problems(root, slug)
            if probs:
                print("not done: " + "; ".join(probs), file=sys.stderr)
                return 1
            text = report(load_evidence(root, slug))
            (_dir(root, slug) / "evidence.md").write_text(text)
            (root / ".herd" / "active").unlink(missing_ok=True)
            print(text)
            print("done: evidence is fresh and passing")
        elif cmd == "gate":
            raw = sys.stdin.read() if not sys.stdin.isatty() else ""
            hook = json.loads(raw) if raw.strip() else {}
            out = gate(Path(hook.get("cwd") or root), hook)
            if out:
                print(json.dumps(out))
        elif cmd == "triage":
            toml_path = root / "herd.toml"
            rec = herd_triage.build_record("task", 0, " ".join(args), {}, toml_path.read_text() if toml_path.exists() else "")
            print(json.dumps(rec, indent=2))
        else:
            print(__doc__)
            return 2
    except (ValueError, FileNotFoundError) as e:
        print(f"herd: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
