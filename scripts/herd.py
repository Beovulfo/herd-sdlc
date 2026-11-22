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
import shlex
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import herd_detect  # noqa: E402
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
# For a `human` criterion add `coverage = "what the check proves and what it does not"`.
# Optional top level: test_budget = "...", known_limits = "when the claim may fail".
#
# [[criteria]]
# id = "C1"
# text = "Given ..., when ..., then ..."
# source = "agent-proposed"
# check = "python3 -m unittest"
'''


QUICK = '''route = "quick"
goal = {goal}

[[criteria]]
id = "C1"
text = {goal}
source = "agent-proposed"
check = {check}
'''

VACUOUS = re.compile(r"(true|:|exit 0|echo\b.*|test -[fe] \S+)")
PER_FILE_LINT = {
    "python": ('ruff check {file}', '["**/*.py"]'),
    "node": ('npx eslint {file}', '["**/*.js", "**/*.jsx", "**/*.ts", "**/*.tsx"]'),
}
LINT_TIMEOUT = 20


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _secs(a, b):
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return int((datetime.strptime(b, fmt) - datetime.strptime(a, fmt)).total_seconds())


def fmt_duration(secs):
    h, rem = divmod(int(secs), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s" if m else f"{s}s"


def _dir(root, slug):
    return Path(root) / ".herd" / "tasks" / slug


def active_slug(root):
    p = Path(root) / ".herd" / "active"
    return p.read_text().strip() if p.exists() else None


# ---- task -----------------------------------------------------------------

def init_task(root, slug, goal, quick_check=None, request=None):
    """Create a task. quick_check makes a one-criterion `quick` task (refused at a high risk floor).

    request is the human's message, verbatim: human criteria must quote it (see human_unquoted).
    """
    if not SLUG.fullmatch(slug):
        raise ValueError("slug must be lower-case letters, digits and dashes (max 41 chars)")
    d = _dir(root, slug)
    if d.exists():
        raise ValueError(f"task {slug} already exists")
    if quick_check is None:
        text = TEMPLATE.format(goal=json.dumps(goal))
    else:
        if not quick_check.strip():
            raise ValueError("--quick needs a non-empty check")
        toml_path = Path(root) / "herd.toml"
        rec = herd_triage.build_record("task", 0, goal, {}, toml_path.read_text() if toml_path.exists() else "")
        if rec["risk"]["floor"] == "high":
            raise ValueError("risk floor is high: use the full criteria flow, not --quick")
        text = QUICK.format(goal=json.dumps(goal), check=json.dumps(quick_check))
    d.mkdir(parents=True)
    (d / "task.toml").write_text(text)
    (d / "started").write_text(now() + "\n")
    if request is not None:
        (d / "request.md").write_text(request)
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
    route = task.get("route", "standard")
    if route not in ("quick", "standard"):
        errs.append("route must be quick or standard")
    elif route == "quick":
        if len(crit) != 1:
            errs.append("quick route needs exactly one criterion")
        elif not str(crit[0].get("check", "")).strip():
            errs.append("quick route needs a runnable check")
    for key in ("test_budget", "known_limits"):
        if key in task and not isinstance(task[key], str):
            errs.append(f"{key}: must be a string")
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
        if "coverage" in c and not isinstance(c["coverage"], str):
            errs.append(f"{cid}: coverage must be a string")
    return errs


def _squash(s):
    return re.sub(r"\s+", " ", s.strip().lower())


def human_unquoted(task, request):
    """Ids of `human` criteria whose text is not a verbatim quote of the request. None if no request."""
    if request is None:
        return None
    req = _squash(request)
    return [c.get("id", "?") for c in task.get("criteria", [])
            if c.get("source") == "human" and _squash(str(c.get("text", ""))) not in req]


def check_warnings(task, request=None):
    """Advisory only: checks that cannot show the criterion holds (a denylist with known gaps),
    and human criteria that are not a verbatim quote of the human's request."""
    out = []
    if request is None:
        if any(c.get("source") == "human" for c in task.get("criteria", [])):
            out.append("no request recorded (`herd init ... --request`): cannot confirm human criteria are verbatim")
    else:
        for cid in human_unquoted(task, request):
            out.append(f"{cid}: human criterion is not a verbatim quote of the request; quote the human's words and "
                       "put your own scenario in a separate agent-proposed criterion")
    for c in task.get("criteria", []):
        check = c.get("check")
        if isinstance(check, str) and check.strip() and VACUOUS.fullmatch(check.strip()):
            out.append(f"{c.get('id', '?')}: check `{check.strip()}` does not run project code, so it proves little")
    return out


def coverage_warnings(task):
    """Advisory: say what a human criterion's check does not cover, and when the claim may fail."""
    out = []
    for c in task.get("criteria", []):
        if c.get("source") == "human" and not str(c.get("coverage", "")).strip():
            out.append(f"{c.get('id', '?')}: human criterion has no `coverage`: say what its check proves "
                       "and what it does not (every word of the criterion, such as `many` or `step by step`)")
    if task.get("route", "standard") != "quick" and not str(task.get("known_limits", "")).strip():
        out.append("no `known_limits`: say under what conditions the claim may fail or has not been shown")
    return out


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
             "coverage": c.get("coverage"), "exit_code": None, "output_tail": "", "status": "unchecked"}
        if c["check"].strip():
            r["exit_code"], r["output_tail"] = run_check(root, c["check"], c.get("timeout_s", DEFAULT_TIMEOUT))
            r["status"] = "passing" if r["exit_code"] == 0 else "failing"
        results.append(r)
    summary = {s: sum(r["status"] == s for r in results) for s in ("passing", "failing", "unchecked")}
    head = _git(root, "rev-parse", "HEAD").decode().strip() or "none"
    dirty = bool(_git(root, "status", "--porcelain", "--", ".", ":!.herd").strip())
    red_path = _dir(root, slug) / "red.json"
    checked = [r for r in results if r["status"] != "unchecked"]
    if not red_path.exists() and checked:  # first verify with a runnable check: how many were red
        red_path.write_text(json.dumps({"at": now(), "failed": sum(r["status"] == "failing" for r in checked),
                                        "total": len(checked)}))
    red = json.loads(red_path.read_text()) if red_path.exists() else None
    req_path = _dir(root, slug) / "request.md"
    human_not_verbatim = human_unquoted(task, req_path.read_text() if req_path.exists() else None)
    timing, started_path = None, _dir(root, slug) / "started"
    if started_path.exists():  # wall clock from `herd init`, so it includes any waiting on the human
        started = started_path.read_text().strip()
        timing = {"started_at": started, "elapsed_s": _secs(started, now())}
        if red:
            timing["first_verify_s"] = _secs(started, red["at"])
    ev = {"task": slug, "goal": task["goal"], "at": now(), "head": head, "dirty": dirty,
          "route": task.get("route", "standard"), "test_budget": task.get("test_budget"),
          "known_limits": task.get("known_limits"),
          "red": {"failed": red["failed"], "total": red["total"]} if red else None, "timing": timing,
          "human_not_verbatim": human_not_verbatim,
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
             f"Result: {s['passing']} passing, {s['failing']} failing, {s['unchecked']} unchecked"]
    if ev.get("route") == "quick":
        lines.append("Route: quick")
    if ev.get("red"):
        lines.append(f"First verify: {ev['red']['failed']} of {ev['red']['total']} checks failed before the work")
    if ev.get("timing"):
        t = ev["timing"]
        first = f"; first verify at {fmt_duration(t['first_verify_s'])}" if "first_verify_s" in t else ""
        lines.append(f"Elapsed: {fmt_duration(t['elapsed_s'])} from herd init to this verify{first} "
                     "(wall clock, includes any waiting on the human)")
    if ev.get("human_not_verbatim"):
        lines.append("Human criteria not quoted verbatim from the request: " + ", ".join(ev["human_not_verbatim"])
                     + " (a human should confirm they were not narrowed)")
    if ev.get("test_budget"):
        lines.append(f"Test budget: {ev['test_budget']}")
    if ev.get("known_limits"):
        lines.append(f"Known limits: {ev['known_limits']}")
    lines += ["", "| id | status | source | check |", "| --- | --- | --- | --- |"]
    for r in ev["results"]:
        lines.append(f"| {r['id']} | {r['status']} | {r['source']} | `{r['check'] or '-'}` |")
    covered = [r for r in ev["results"] if r["source"] == "human" and str(r.get("coverage") or "").strip()]
    if covered:
        lines += ["", "Coverage of human criteria (what each check proves and does not):"]
        lines += [f"- {r['id']}: {r['coverage'].strip()}" for r in covered]
    for r in ev["results"]:
        if r["status"] == "failing":
            lines += ["", f"Failing {r['id']} (exit {r['exit_code']}), output tail:", "```", r["output_tail"].strip(), "```"]
    if s["unchecked"]:
        lines += ["", "Unchecked criteria have no runnable check and are never counted as met."]
    return "\n".join(lines) + "\n"


# ---- lint hook ------------------------------------------------------------

def lint(hook):
    """PostToolUse hook: run the project's per-file lint after an edit.

    Non-blocking: failures come back as additionalContext. Opt-in via [lint] in herd.toml,
    and only while a Herd task is active.
    """
    cwd = Path(hook.get("cwd") or Path.cwd())
    fp = (hook.get("tool_input") or {}).get("file_path")
    if not fp or not active_slug(cwd):
        return None
    try:
        rel = Path(fp).resolve().relative_to(cwd.resolve())
        cfg = tomllib.loads((cwd / "herd.toml").read_text()).get("lint")
    except (ValueError, OSError, tomllib.TOMLDecodeError):
        return None
    if not isinstance(cfg, dict) or not isinstance(cfg.get("command"), str):
        return None
    if not any(PurePosixPath(rel.as_posix()).full_match(g) for g in cfg.get("globs", ["**/*"])):
        return None
    cmd = cfg["command"].replace("{file}", shlex.quote(rel.as_posix()))
    code, out = run_check(cwd, cmd, cfg.get("timeout_s", LINT_TIMEOUT))
    if code == 0:
        return None
    head = f"Herd lint for {rel}: {out}" if code is None else f"Herd lint failed for {rel} (exit {code}):\n{out}"
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": head}}


def suggest_lint(root):
    """A [lint] block for herd.toml from the detected project type, for the human to paste."""
    found = [d["type"] for d in herd_detect.detect(root) if d["type"] in PER_FILE_LINT]
    if not found:
        return "no per-file lint command is known for this project; set one yourself in herd.toml"
    cmd, globs = PER_FILE_LINT[found[0]]
    lines = ["[lint]", f'command = "{cmd}"', f"globs = {globs}", f"timeout_s = {LINT_TIMEOUT}"]
    for t in found[1:]:
        lines.append(f'# also {t}: command = "{PER_FILE_LINT[t][0]}"  (one command per [lint]; pick by globs)')
    return "\n".join(lines)


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
    """Slug from the arguments, the active task, or the only task that exists."""
    slug = args[0] if args else active_slug(root)
    if slug:
        return slug
    tasks_dir = Path(root) / ".herd" / "tasks"
    tasks = sorted(p.name for p in tasks_dir.iterdir() if (p / "task.toml").exists()) if tasks_dir.exists() else []
    if len(tasks) == 1:
        return tasks[0]
    if tasks:
        sys.exit(f"no active task; pass one of: {', '.join(tasks)}")
    sys.exit("no active task: run `herd init <slug> \"<goal>\"`")


def main(argv):
    root = Path.cwd()
    cmd, args = (argv[0], argv[1:]) if argv else ("status", [])
    try:
        if cmd == "init":
            quick = request = None
            if "--quick" in args:
                i = args.index("--quick")
                quick = args[i + 1]
                args = args[:i] + args[i + 2:]
            if "--request" in args:
                i = args.index("--request")
                request = args[i + 1]
                args = args[:i] + args[i + 2:]
            init_task(root, args[0], args[1], quick_check=quick, request=request)
            if quick is None:
                print(f"created .herd/tasks/{args[0]}/task.toml (commented template): add criteria with checks, then run `herd check`")
            else:
                print(f"created quick task {args[0]} with one criterion: run `herd verify` and expect it to fail first")
        elif cmd == "check":
            slug = _slug_arg(root, args)
            task = load_task(root, slug)
            errs = validate_task(task)
            print("\n".join(errs) if errs else "ok")
            req_path = _dir(root, slug) / "request.md"
            for w in check_warnings(task, req_path.read_text() if req_path.exists() else None) + coverage_warnings(task):
                print(f"warning: {w}")
            return 1 if errs else 0
        elif cmd == "detect":
            print(json.dumps(herd_detect.detect(root), indent=2))
        elif cmd == "lint":
            if "--suggest" in args:
                print(suggest_lint(root))
            else:
                raw = sys.stdin.read() if not sys.stdin.isatty() else ""
                try:
                    hook = json.loads(raw) if raw.strip() else {}
                except ValueError:
                    hook = {}
                out = lint(hook)
                if out:
                    print(json.dumps(out))
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
    except (ValueError, FileNotFoundError, IndexError) as e:
        print(f"herd: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
