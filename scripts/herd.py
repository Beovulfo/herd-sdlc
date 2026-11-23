#!/usr/bin/env python3
"""herd: the evidence harness. Standard library only, Python 3.11+.

A task is `.herd/tasks/<slug>/task.toml`: a goal plus success criteria, each with a
`check` command. `herd verify` runs the checks and stores evidence. `herd gate` (the
Stop hook) refuses to let the agent finish without fresh, passing evidence.
"""
import sys

if sys.version_info < (3, 11):  # keep this block parseable by old Pythons: it runs before tomllib is imported
    if sys.argv[1:2] in (["gate"], ["lint"]):
        sys.exit(0)  # a hook must never break the session; the CLI says why below
    sys.exit("herd needs Python 3.11 or newer, found " + sys.version.split()[0])

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # ponytail: Windows has no flock; parallel inits there can still race
    fcntl = None

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
QUANT = re.compile(r"\b(any|every|whatever|whichever|many|each|arbitrary)\b", re.I)
SCALE = re.compile(r"\b(big|large|huge|massive|thousands|millions|scale|scalable)\b", re.I)
VARIES = re.compile(r"\b(vary|varies|varied|varying|variation|generated?|random\w*|seeds?|property|fuzz\w*|"
                    r"parametri[sz]ed|families|several|multiple|across|sizes?)\b", re.I)
SCALED = re.compile(r"\b(scales?|sizes?|largest?|big|biggest|huge|time limit|timed|timing|seconds|performance|"
                    r"runtime|latency|up to \d+)\b", re.I)
NOTE_KINDS = ("found", "fixed", "open", "tried")
# the standard attacks of the adversarial pass (skills/run/adversarial.md): `herd done` needs a tried note for each
ATTACKS = {"bad-input": "bad input at every entry point ends in a clear message, never a traceback",
           "collision": "two inputs on the same key or position each still count",
           "one-bad-part": "one broken entry the request does not use does not reject the whole input",
           "recount": "every reported number recomputed from the output with separate code"}
MAX_TEXT_WORDS, MAX_COVERAGE_WORDS = 40, 50  # advisory limits, see length_warnings
WORKTREES = ".claude/worktrees"  # where `herd init --worktree` puts tasks; Claude Code's EnterWorktree can enter it
OWN_FILES = (".", ":!.herd")  # pathspec: this checkout's work, not Herd's own state
# Test runners' own words for an empty run, and for a run that executed tests. Advisory, so the list
# only has to catch the common cases: unittest, pytest, cargo, go, jest, mocha.
ZERO_TESTS = re.compile(r"\bRan 0 tests?\b|\bcollected 0 items\b|\bno tests ran\b|\brunning 0 tests\b"
                        r"|\[no test files\]|\[no tests to run\]|\bNo tests found\b|^[ \t]*0 passing\b", re.M)
SOME_TESTS = re.compile(r"\bRan [1-9]\d* tests?\b|\b[1-9]\d* passed\b|\brunning [1-9]\d* tests?\b"
                        r"|^ok\s+\S+\s+(?:\(cached\)|[\d.]+s)(?!.*\[no tests to run\])"  # go's per-package line
                        r"|^[ \t]*[1-9]\d* passing\b", re.M)


def ran_zero_tests(output):
    """The output says a test runner ran no tests, and nothing in it says any suite ran some."""
    return bool(ZERO_TESTS.search(output)) and not SOME_TESTS.search(output)


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
    other = active_slug(root)
    if other and _dir(root, other).exists() and not cancelled(root, other):
        raise ValueError(f"task {other} is still active in this checkout: finish it (`herd done`), cancel it, "
                         f"or start this one in its own worktree with --worktree")
    d.mkdir(parents=True)
    (d / "task.toml").write_text(text)
    (d / "started").write_text(now() + "\n")
    if request is not None:
        (d / "request.md").write_text(request)
    (Path(root) / ".herd" / "active").write_text(slug + "\n")


def cancel_task(root, slug, reason=""):
    """Abandon a task. Its files stay as a record; the Stop gate no longer blocks on it."""
    d = _dir(root, slug)
    if not (d / "task.toml").exists():
        raise ValueError(f"no task {slug}")
    (d / "cancelled").write_text(json.dumps({"at": now(), "reason": reason.strip()}) + "\n")
    (d / "gate_blocks").unlink(missing_ok=True)
    if active_slug(root) == slug:
        (Path(root) / ".herd" / "active").unlink()


def cancelled(root, slug):
    p = _dir(root, slug) / "cancelled"
    return json.loads(p.read_text()) if p.exists() else None


def _branch(root):
    return _git(root, "rev-parse", "--abbrev-ref", "HEAD").decode().strip()


def _gitpath(root, what):
    out = _git(root, "rev-parse", what).decode().strip()
    return str((Path(root) / out).resolve()) if out else ""  # older git prints these relative to root


def toplevel(path):
    """The work tree root that contains path, or path itself outside git."""
    top = _git(path, "rev-parse", "--show-toplevel").decode().strip()
    return Path(top) if top else Path(path)


def find_root(path):
    """The nearest folder up to the work tree root that has `.herd/` or `herd.toml`, else the work tree root.

    A project in a subfolder of a repository (a monorepo package) keeps its own `.herd/`.
    """
    path, top = Path(path).resolve(), toplevel(path).resolve()
    for d in (path, *path.parents):
        if (d / ".herd").is_dir() or (d / "herd.toml").is_file():
            return d
        if d == top:
            break
    return top


def _main_checkout(root):
    """The repository's main work tree (the first `git worktree list` entry), also for submodules."""
    first = _git(root, "worktree", "list", "--porcelain").decode().splitlines()[:1]
    return Path(first[0].split(" ", 1)[1]) if first and first[0].startswith("worktree ") else toplevel(root)


def _ignore_locally(root, patterns):
    """Add patterns to the repository's own `info/exclude` (never committed) when missing."""
    exclude = Path(_gitpath(root, "--git-common-dir")) / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    have = exclude.read_text().splitlines() if exclude.exists() else []
    missing = [p for p in patterns if p not in have]
    if missing:
        with exclude.open("a") as fh:
            fh.write("".join(f"{p}\n" for p in missing))


def worktree_required(root):
    try:
        cfg = tomllib.loads((Path(root) / "herd.toml").read_text()).get("worktree")
    except (OSError, tomllib.TOMLDecodeError):
        return False
    return isinstance(cfg, dict) and cfg.get("required") is True


def check_worktree_rule(root, slug):
    """With `[worktree] required = true`, a plain init must run in a linked worktree on herd/<slug>."""
    if not worktree_required(root):
        return
    linked = _gitpath(root, "--git-dir") != _gitpath(root, "--git-common-dir")
    if not linked or _branch(root) != f"herd/{slug}":
        raise ValueError(f"herd.toml requires each task in its own worktree on herd/{slug}: "
                         f"run `herd init {slug} \"<goal>\" --worktree` instead")


def init_worktree(root, slug, goal, quick_check=None, request=None):
    """Start a task on a new herd/<slug> branch in its own worktree, cut from the current local branch.

    Returns (path, base branch, whether uncommitted changes were left behind in the starting checkout).
    """
    if not SLUG.fullmatch(slug):
        raise ValueError("slug must be lower-case letters, digits and dashes (max 41 chars)")
    base = _branch(root)
    if base in ("", "HEAD"):
        raise ValueError("start from a local branch: HEAD is detached or the repository has no commit yet")
    # other agents' worktrees and every checkout's Herd state stay out of `git status` and `git add -A`
    _ignore_locally(root, [f"/{WORKTREES}/", ".herd/"])
    tree = _main_checkout(root) / WORKTREES / f"herd-{slug}"
    # git reads every worktree's admin files during `worktree add` and fails on one that a parallel
    # add has half written, so parallel inits take turns for this one call
    with open(Path(_gitpath(root, "--git-common-dir")) / "herd-worktree.lock", "a") as lock:
        if fcntl:
            fcntl.flock(lock, fcntl.LOCK_EX)  # released when the file closes
        p = subprocess.run(["git", "worktree", "add", "-b", f"herd/{slug}", str(tree), "HEAD"],
                           cwd=root, capture_output=True, text=True)
    if p.returncode:
        raise ValueError(f"git worktree add failed: {p.stderr.strip()[-300:]}")
    path = tree / Path(root).resolve().relative_to(toplevel(root).resolve())  # same subfolder as the project
    try:
        init_task(path, slug, goal, quick_check=quick_check, request=request)
        (_dir(path, slug) / "base").write_text(base + "\n")
    except Exception:  # undo only what this call made: its own new worktree and branch
        subprocess.run(["git", "worktree", "remove", "--force", str(tree)], cwd=root, capture_output=True)
        subprocess.run(["git", "branch", "-D", f"herd/{slug}"], cwd=root, capture_output=True)
        raise
    pointer = Path(root) / ".herd" / "elsewhere"
    pointer.mkdir(parents=True, exist_ok=True)
    (pointer / slug).write_text(str(path) + "\n")  # one file per task: safe when several inits run at once
    left = bool(_git(root, "status", "--porcelain", "--", *OWN_FILES).strip())
    return path, base, left


def elsewhere(root):
    """Tasks started from this checkout that live in their own worktree: {slug: path}."""
    d = Path(root) / ".herd" / "elsewhere"
    found = {p.name: p.read_text().strip() for p in sorted(d.iterdir())} if d.exists() else {}
    return {k: v for k, v in found.items() if Path(v).exists()}  # a removed worktree is forgotten


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


def length_warnings(task):
    """Advisory: long criterion and coverage texts cost tokens on every read and hide the point."""
    out = []
    for c in task.get("criteria", []):
        cid = c.get("id", "?")
        if len(str(c.get("text", "")).split()) > MAX_TEXT_WORDS and c.get("source") != "human":
            out.append(f"{cid}: criterion text over {MAX_TEXT_WORDS} words; keep one testable sentence")
        if len(str(c.get("coverage", "")).split()) > MAX_COVERAGE_WORDS:
            out.append(f"{cid}: coverage over {MAX_COVERAGE_WORDS} words; name what the check proves and misses, briefly")
    return out


def coverage_warnings(task):
    """Advisory: say what a human criterion's check does not cover, and when the claim may fail."""
    out = []
    for c in task.get("criteria", []):
        if c.get("source") != "human":
            continue
        cid, cov = c.get("id", "?"), str(c.get("coverage", "")).strip()
        if not cov:
            out.append(f"{cid}: human criterion has no `coverage`: say what its check proves "
                       "and what it does not (every word of the criterion, such as `many` or `step by step`)")
            continue
        q, sc = QUANT.search(str(c.get("text", ""))), SCALE.search(str(c.get("text", "")))
        if q and not VARIES.search(cov):
            out.append(f"{cid}: human criterion says '{q.group(0)}' but its `coverage` does not say what varies "
                       "(generated inputs, seeds, families, sizes)")
        if sc and not SCALED.search(cov):
            out.append(f"{cid}: human criterion says '{sc.group(0)}' but its `coverage` has no scale statement "
                       "(largest size tried, time limit)")
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
    h.update(_git(root, "diff", "HEAD", "--", *OWN_FILES))
    for name in sorted(_git(root, "ls-files", "--others", "--exclude-standard", "--", *OWN_FILES).decode().splitlines()):
        h.update(name.encode())
        try:
            h.update((Path(root) / name).read_bytes())
        except OSError:
            pass
    return h.hexdigest()


def _task_sha(root, slug):
    return hashlib.sha1((_dir(root, slug) / "task.toml").read_bytes()).hexdigest()


def run_check(root, check, timeout, full=False):
    """Exit code (None on timeout) and the output tail; with full=True, the whole output instead."""
    try:
        p = subprocess.run(check, shell=True, cwd=root, capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, out if full else out[-TAIL_CHARS:]
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
             "coverage": c.get("coverage"), "exit_code": None, "output_tail": "", "status": "unchecked",
             "zero_tests": False}
        if c["check"].strip():
            r["exit_code"], out = run_check(root, c["check"], c.get("timeout_s", DEFAULT_TIMEOUT), full=True)
            r["output_tail"] = out[-TAIL_CHARS:]
            r["status"] = "passing" if r["exit_code"] == 0 else "failing"
            r["zero_tests"] = r["status"] == "passing" and ran_zero_tests(out)  # advisory, the gate ignores it
        results.append(r)
    summary = {s: sum(r["status"] == s for r in results) for s in ("passing", "failing", "unchecked")}
    head = _git(root, "rev-parse", "HEAD").decode().strip() or "none"
    dirty = bool(_git(root, "status", "--porcelain", "--", *OWN_FILES).strip())
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
          "known_limits": task.get("known_limits"), "notes": load_notes(root, slug),
          "red": {"failed": red["failed"], "total": red["total"]} if red else None, "timing": timing,
          "human_not_verbatim": human_not_verbatim,
          "fingerprint": fingerprint(root), "task_sha": _task_sha(root, slug),
          "results": results, "summary": summary}
    (_dir(root, slug) / "evidence.json").write_text(json.dumps(ev, indent=2))
    return ev


def add_note(root, slug, kind, text, attack=None):
    """Append a caveat to the task's log: found, fixed, open (a known limit) or tried (adversarial attempt).

    attack names which standard attack a tried note covers (one of ATTACKS)."""
    if kind not in NOTE_KINDS:
        raise ValueError(f"note kind must be one of {NOTE_KINDS}")
    if attack is not None and (kind != "tried" or attack not in ATTACKS):
        raise ValueError(f"--attack goes with --tried and is one of: {', '.join(ATTACKS)}")
    if not text.strip():
        raise ValueError("note text is empty")
    d, started = _dir(root, slug), _dir(root, slug) / "started"
    t = now()
    rec = {"at": t, "kind": kind, "text": text.strip(),
           "elapsed_s": _secs(started.read_text().strip(), t) if started.exists() else None}
    if attack:
        rec["attack"] = attack
    with open(d / "notes.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")


def load_notes(root, slug):
    p = _dir(root, slug) / "notes.jsonl"
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()] if p.exists() else []


def load_evidence(root, slug):
    p = _dir(root, slug) / "evidence.json"
    return json.loads(p.read_text()) if p.exists() else None


BATCH_S = 5
MAX_PR_NOTES = 60  # keeps the PR description well under GitHub's 65,536-character limit


def _largest_batch(notes):
    """Most notes whose timestamps fall inside one BATCH_S window (a sign they were logged together)."""
    times = sorted(_secs("2000-01-01T00:00:00Z", n["at"]) for n in notes if n.get("at"))
    best = 0
    for i, t in enumerate(times):
        best = max(best, sum(1 for u in times[i:] if u - t <= BATCH_S))
    return best


def _attack_line(notes):
    """`Adversarial pass: ...` with the standard attacks covered and missing; None when nothing was tried."""
    tried = [n for n in notes if n["kind"] == "tried"]
    if not tried:
        return None
    covered = {n.get("attack") for n in tried}
    missing = [a for a in ATTACKS if a not in covered]
    return (f"Adversarial pass: {len(tried)} attempt{'s' if len(tried) != 1 else ''} recorded; standard attacks "
            + (f"missing: {', '.join(missing)}" if missing else "all logged"))


def report(ev, notes=None):
    s = ev["summary"]
    notes = ev.get("notes") or [] if notes is None else notes
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
    if ev.get("route") != "quick":
        lines.append(_attack_line(notes) or "Adversarial pass: not recorded")
    lines += ["", "| id | status | source | check |", "| --- | --- | --- | --- |"]
    for r in ev["results"]:
        lines.append(f"| {r['id']} | {r['status']} | {r['source']} | `{r['check'] or '-'}` |")
    zero = [r["id"] for r in ev["results"] if r.get("zero_tests")]
    if zero:
        lines += [""] + [f"Warning: {cid} passed but ran zero tests (its output says no tests ran), so it proves "
                         "nothing yet: point its check at real tests" for cid in zero]
    covered = [r for r in ev["results"] if r["source"] == "human" and str(r.get("coverage") or "").strip()]
    if covered:
        lines += ["", "Coverage of human criteria (what each check proves and does not):"]
        lines += [f"- {r['id']}: {r['coverage'].strip()}" for r in covered]
    if notes:
        count = {k: sum(n["kind"] == k for n in notes) for k in NOTE_KINDS}
        lines.append("")
        if count["found"] or count["fixed"] or count["open"]:
            lines.append(f"Caveats during the run: {count['found']} found, {count['fixed']} fixed, {count['open']} open")
        for n in notes:
            when = f"{fmt_duration(n['elapsed_s'])} " if n.get("elapsed_s") is not None else ""
            lines.append(f"- {when}{n['kind']}: {n['text']}")
        batch = _largest_batch(notes)
        if batch >= 3:
            lines.append(f"Note: {batch} notes were logged within {BATCH_S} s of each other, so their times show "
                         "when they were written, not when found.")
    for r in ev["results"]:
        if r["status"] == "failing":
            lines += ["", f"Failing {r['id']} (exit {r['exit_code']}), output tail:", "```", r["output_tail"].strip(), "```"]
    if s["unchecked"]:
        lines += ["", "Unchecked criteria have no runnable check and are never counted as met."]
    return "\n".join(lines) + "\n"


# ---- pull request ---------------------------------------------------------

def _cell(text):
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def _ticks(text, least=1):
    """A backtick run longer than any inside text, so a code span or fence cannot be broken by it."""
    return "`" * max(least, max((len(m) for m in re.findall(r"`+", text)), default=0) + 1)


def _code(text):
    t = _ticks(text)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{t}{pad}{_cell(text)}{pad}{t}"


def _clip(text, limit=60):
    """Long check commands are cut in the table; Reproduce has them in full."""
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


def _stale(root, slug, ev):
    return ev["task_sha"] != _task_sha(root, slug) or ev["fingerprint"] != fingerprint(root)


def pr_body(root, slug):
    """The PR description, evidence first: what is proven and by which check, then what is not, then how to re-run."""
    task, ev, notes = load_task(root, slug), load_evidence(root, slug), load_notes(root, slug)
    head = [f"# Evidence: {slug}", "", f"**Goal:** {task['goal']}", ""]
    foot = ["", "---", "Opened by Herd with `herd pr`. Herd never merges: review the evidence above, then merge."]
    if ev is None:
        return "\n".join(head + ["No evidence yet: `herd verify` has not run. The next `herd pr` replaces this."]
                         + foot) + "\n"
    s, results = ev["summary"], ev["results"]
    stale = _stale(root, slug, ev)
    if stale:
        fresh = ("**The evidence is stale:** the code or the task changed after the last `herd verify`, "
                 "so these results may no longer hold.")
    else:
        fresh = (f"The evidence is fresh: the checks ran at {ev['at']} on commit `{ev['head'][:12]}`"
                 + (" plus uncommitted changes." if ev.get("dirty") else "."))
    proven = [r for r in results if r["status"] == "passing" and not r.get("zero_tests")]
    zero = sum(bool(r.get("zero_tests")) for r in results)
    lines = head + [f"**Result:** {len(proven)} of {len(results)} criteria proven by a passing check "
                    f"({s['failing']} failing, {s['unchecked']} unchecked"
                    + (f", {zero} passed without running any test" if zero else "") + ").", "", fresh, ""]
    lines += [f"## What was proven at commit `{ev['head'][:12]}`, before later changes (stale: re-run `herd verify`)"
              if stale else "## What is proven", ""]
    passing = proven
    if passing:
        lines += ["| id | source | criterion | proof: the check that passed |", "| --- | --- | --- | --- |"]
        lines += [f"| {r['id']} | {r['source']} | {_cell(r['text'])} | {_code(_clip(r['check']))} exit 0 |"
                  for r in passing]
    else:
        lines.append("Nothing yet: no criterion has a passing check.")
    gaps = [f"- {r['id']} is failing (exit {r['exit_code']}): {r['text']}" for r in results if r["status"] == "failing"]
    gaps += [f"- {r['id']} is unchecked, never counted as met: {r['text']}" for r in results if r["status"] == "unchecked"]
    gaps += [f"- {r['id']} passed but ran zero tests, so it proves nothing yet" for r in results if r.get("zero_tests")]
    gaps += [f"- {cid} is a human criterion not quoted verbatim from the request" for cid in ev.get("human_not_verbatim") or []]
    gaps += [f"- {r['id']}, what its check proves and does not: {r['coverage'].strip()}"
             for r in results if r["source"] == "human" and str(r.get("coverage") or "").strip()]
    if ev.get("known_limits"):
        gaps.append(f"- Known limits: {ev['known_limits']}")
    gaps += [f"- Open caveat: {n['text']}" for n in notes if n["kind"] == "open"]
    if ev.get("route") != "quick" and not any(n["kind"] == "tried" for n in notes):
        gaps.append("- No adversarial pass was recorded")
    lines += ["", "## What is not proven", ""] + (gaps or ["- Nothing recorded, which is unusual: ask what the checks miss"])
    details = [f"Route: {ev.get('route', 'standard')}"]
    if ev.get("red"):
        details.append(f"First verify: {ev['red']['failed']} of {ev['red']['total']} checks failed before the work")
    if ev.get("timing"):
        details.append(f"Elapsed: {fmt_duration(ev['timing']['elapsed_s'])} from `herd init` to the last verify")
    if ev.get("test_budget"):
        details.append(f"Test budget: {ev['test_budget']}")
    if _attack_line(notes):
        details.append(_attack_line(notes))
    # the reviewer's view ends here; the rest is collapsed, nothing is dropped
    count = {k: sum(n["kind"] == k for n in notes) for k in NOTE_KINDS}
    lines += ["", "<details><summary>Run details and caveat log "
              f"({count['tried']} tried, {count['found']} found, {count['fixed']} fixed)</summary>", ""]
    lines += [f"- {d}" for d in details]
    # ponytail: output tails stay out of the PR (they can hold secrets); the reviewer re-runs the check instead
    if notes:
        shown = notes[:MAX_PR_NOTES]
        lines += ["", "Caveats logged during the run:", ""]
        lines += [f"- {fmt_duration(n['elapsed_s']) + ' ' if n.get('elapsed_s') is not None else ''}"
                  f"{n['kind']}: {n['text']}" for n in shown]
        if len(notes) > len(shown):
            lines.append(f"- and {len(notes) - len(shown)} more: run `herd status {slug}`")
    lines += ["", "</details>"]
    checks = [r["check"] for r in results if r["check"].strip()]
    fence = _ticks("\n".join(checks), least=3)
    lines += ["", "<details><summary>Reproduce: run from the repository root</summary>", "",
              fence + "bash"] + checks + [fence, "", "</details>"]
    return "\n".join(lines + foot) + "\n"


def pr_title(goal, slug, limit=72):
    """The goal's first line, cut at a word boundary to fit a PR list."""
    line = (str(goal).strip().splitlines() or [slug])[0].strip() or slug
    if len(line) <= limit:
        return line
    cut = line[:limit - 3].rsplit(" ", 1)[0].rstrip(" ,;:")
    return cut + "..."


def open_pr(root, slug, yes=False):
    """Push the task's herd/* branch and open or update its PR with the evidence. Opt-in; no other branch."""
    try:
        cfg = tomllib.loads((Path(root) / "herd.toml").read_text()).get("pr")
    except (OSError, tomllib.TOMLDecodeError):
        cfg = None
    if not (yes or (isinstance(cfg, dict) and cfg.get("open") is True)):
        raise ValueError("herd pr is opt-in: set `[pr] open = true` in herd.toml, or pass --yes when the request "
                         "asks for a pull request")
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").decode().strip()
    if branch != f"herd/{slug}":
        raise ValueError(f"herd pr pushes only the task's branch herd/{slug}; this is `{branch or 'no branch'}`")
    if _git(root, "status", "--porcelain", "--", *OWN_FILES).strip():
        raise ValueError("herd pr needs a clean working tree: commit the work, run `herd verify`, then `herd pr`, "
                         "so the pull request contains exactly the code the evidence is about")
    if not shutil.which("gh"):
        raise ValueError("herd pr needs the GitHub CLI `gh` on PATH")
    body = pr_body(root, slug)
    p = subprocess.run(["git", "push", "-u", "origin", branch], cwd=root, capture_output=True, text=True)
    if p.returncode:
        raise ValueError(f"git push failed: {p.stderr.strip()[-500:]}")
    view = subprocess.run(["gh", "pr", "view", branch, "--json", "url,state", "-q", 'select(.state == "OPEN") | .url'],
                          cwd=root, capture_output=True, text=True)
    url = view.stdout.strip() if view.returncode == 0 else ""  # empty unless an open PR exists
    if url:
        cmd = ["gh", "pr", "edit", branch, "--body-file", "-"]
    else:
        base_file = _dir(root, slug) / "base"
        base = ["--base", base_file.read_text().strip()] if base_file.exists() else []
        cmd = ["gh", "pr", "create", "--head", branch, *base, "--title", pr_title(load_task(root, slug)["goal"], slug), "--body-file", "-"]
    p = subprocess.run(cmd, cwd=root, input=body, capture_output=True, text=True)
    if p.returncode:
        raise ValueError(f"`{' '.join(cmd[:3])}` failed: {(p.stderr or p.stdout).strip()[-500:]}")
    url = url or p.stdout.strip().splitlines()[-1]
    (_dir(root, slug) / "pr").write_text(url + "\n")  # `herd done` refreshes this PR's description
    return url


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
    if not any(herd_triage.glob_match(rel.as_posix(), g) for g in cfg.get("globs", ["**/*"])):
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
    if ev.get("route") != "quick":
        tried = {n.get("attack") for n in load_notes(root, slug) if n["kind"] == "tried"}
        missing = [a for a in ATTACKS if a not in tried]
        if missing:
            out.append("adversarial pass incomplete (skills/run/adversarial.md): try "
                       + "; ".join(f"{a}: {ATTACKS[a]}" for a in missing)
                       + ". Log each with `herd note --tried --attack <name> \"what you ran and saw\"`")
    return out


def gate(root, hook):
    """Stop hook. None allows the stop; a dict blocks it with a reason for the agent."""
    slug = active_slug(root)
    if not slug or not _dir(root, slug).exists() or cancelled(root, slug):
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
              + "; ".join(probs) + f". Run `{cmd}` after fixing. If you are stuck, ask the human one question and stop."
              + f" If the human abandoned the task, run `python3 {SELF} cancel --reason \"...\"`.")
    return {"decision": "block", "reason": reason}


# ---- cli ------------------------------------------------------------------

def _slug_arg(root, args):
    """Slug from the arguments, the active task, or the only task that exists."""
    slug = args[0] if args else active_slug(root)
    moved = elsewhere(root)
    if slug and slug in moved and not _dir(root, slug).exists():
        sys.exit(f"task {slug} lives in its worktree {moved[slug]}: work from there "
                 "(Claude Code: EnterWorktree with that path; otherwise cd into it)")
    if slug:
        return slug
    tasks_dir = Path(root) / ".herd" / "tasks"
    tasks = sorted(p.name for p in tasks_dir.iterdir() if (p / "task.toml").exists()) if tasks_dir.exists() else []
    if len(tasks) == 1:
        return tasks[0]
    if tasks:
        sys.exit(f"no active task; pass one of: {', '.join(tasks)}")
    if moved:
        sys.exit("no task in this checkout; tasks started here live in their worktrees: "
                 + ", ".join(f"{k} in {v}" for k, v in moved.items()) + ". Work from there")
    sys.exit("no active task: run `herd init <slug> \"<goal>\"`")


USAGE = {
    "init": 'herd init <slug> "<goal>" [--request "<message>"] [--quick "<check>"] [--worktree]',
    "check": "herd check [slug]",
    "note": 'herd note --found|--fixed|--open|--tried [--attack bad-input|collision|one-bad-part|recount] "text"',
    "detect": "herd detect",
    "lint": "herd lint [--suggest]   (without --suggest: the PostToolUse hook, reads hook JSON on stdin)",
    "verify": "herd verify [slug] [--verbose]",
    "status": "herd status [slug]",
    "done": "herd done [slug] [--verbose]",
    "cancel": 'herd cancel [slug] [--reason "text"]',
    "pr": "herd pr [slug] [--yes]   (push the herd/* branch, open or update its PR with the evidence)",
    "gate": "herd gate   (the Stop hook, reads hook JSON on stdin)",
    "triage": 'herd triage "<text>" [--json]',
}


class UsageError(Exception):
    pass


def _opt(args, flag):
    """Remove `flag value` from args; return (value or None, rest)."""
    if flag not in args:
        return None, args
    i = args.index(flag)
    if i + 1 >= len(args):
        raise UsageError
    return args[i + 1], args[:i] + args[i + 2:]


def main(argv):
    root = find_root(Path.cwd())
    cmd, args = (argv[0], argv[1:]) if argv else ("status", [])
    if cmd in ("help", "-h", "--help"):
        print(__doc__ + "\nCommands:\n" + "\n".join(f"  {u}" for u in USAGE.values()))
        return 0
    if cmd not in USAGE:
        print(f"herd: unknown command `{cmd}`; run `herd help`", file=sys.stderr)
        return 2
    try:
        if cmd == "init":
            quick, args = _opt(args, "--quick")
            request, args = _opt(args, "--request")
            worktree = "--worktree" in args
            args = [a for a in args if a != "--worktree"]
            if len(args) != 2:
                raise UsageError
            if worktree:
                path, base, left = init_worktree(root, args[0], args[1], quick_check=quick, request=request)
                print(f"created worktree {path} on branch herd/{args[0]}, cut from {base}. Work from there: in Claude "
                      "Code, EnterWorktree with that path; otherwise cd into it. Run every herd command from it.")
                if left:
                    print(f"warning: uncommitted changes in {base} were not carried into the worktree", file=sys.stderr)
                return 0
            check_worktree_rule(root, args[0])
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
            for w in (check_warnings(task, req_path.read_text() if req_path.exists() else None)
                      + coverage_warnings(task) + length_warnings(task)):
                print(f"warning: {w}")
            return 1 if errs else 0
        elif cmd == "note":
            kinds = {"--found": "found", "--fixed": "fixed", "--open": "open", "--tried": "tried"}
            attack, args = _opt(args, "--attack")
            flags = [a for a in args if a.startswith("--")]
            rest = [a for a in args if not a.startswith("--")]
            if len(flags) != 1 or flags[0] not in kinds or len(rest) != 1:
                raise UsageError
            add_note(root, _slug_arg(root, []), kinds[flags[0]], rest[0], attack=attack)
            print(f"noted ({kinds[flags[0]]}): {rest[0]}")
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
            verbose = "--verbose" in args
            ev = verify(root, _slug_arg(root, [a for a in args if a != "--verbose"]))
            s = ev["summary"]
            print(f"{s['passing']} passing, {s['failing']} failing, {s['unchecked']} unchecked")
            for r in ev["results"]:  # by default only what needs attention
                zero = " (ran zero tests)" if r.get("zero_tests") else ""
                if verbose or r["status"] != "passing" or zero:
                    print(f"  {r['id']} {r['status']}{zero}: {r['text']}")
            return 1 if s["failing"] else 0
        elif cmd == "status":
            slug = _slug_arg(root, args)
            ev = load_evidence(root, slug)
            print(report(ev, load_notes(root, slug)) if ev else f"task {slug}: no evidence yet")
            c = cancelled(root, slug)
            if c:
                print(f"cancelled at {c['at']}" + (f": {c['reason']}" if c["reason"] else ""))
                return 0
            probs = problems(root, slug)
            print("not done: " + "; ".join(probs) if probs else "done: evidence is fresh and passing")
        elif cmd == "done":
            verbose = "--verbose" in args
            slug = _slug_arg(root, [a for a in args if a != "--verbose"])
            probs = problems(root, slug)
            if probs:
                print("not done: " + "; ".join(probs), file=sys.stderr)
                return 1
            ev = load_evidence(root, slug)
            text = report(ev, load_notes(root, slug))
            (_dir(root, slug) / "evidence.md").write_text(text)
            (root / ".herd" / "active").unlink(missing_ok=True)
            if verbose:
                print(text)
            proven = sum(r["status"] == "passing" and not r.get("zero_tests") for r in ev["results"])
            print(f"done: evidence is fresh and passing ({proven} of {len(ev['results'])} criteria proven)")
            print(f"report: {(_dir(root, slug) / 'evidence.md').relative_to(root)}")
            if (_dir(root, slug) / "pr").exists():  # a PR exists: its description must show the final evidence
                try:
                    print(f"pr: description updated with the final evidence: {open_pr(root, slug, yes=True)}")
                except ValueError as e:
                    print(f"warning: the pull request still shows older evidence ({e}); run `herd pr` again",
                          file=sys.stderr)
        elif cmd == "pr":
            slug = _slug_arg(root, [a for a in args if a != "--yes"])
            print(open_pr(root, slug, yes="--yes" in args))
            probs = problems(root, slug)
            if probs:
                print("warning: the pull request shows evidence that is not done: " + "; ".join(probs), file=sys.stderr)
        elif cmd == "cancel":
            reason, args = _opt(args, "--reason")
            slug = _slug_arg(root, args)
            cancel_task(root, slug, reason or "")
            print(f"cancelled {slug}: its files stay in .herd/tasks/{slug}/ and the Stop gate no longer blocks")
        elif cmd == "gate":
            raw = sys.stdin.read() if not sys.stdin.isatty() else ""
            hook = json.loads(raw) if raw.strip() else {}
            out = gate(find_root(Path(hook.get("cwd") or root)), hook)
            if out:
                print(json.dumps(out))
        elif cmd == "triage":
            as_json = "--json" in args
            text = " ".join(a for a in args if a != "--json")
            toml_path = root / "herd.toml"
            rec = herd_triage.build_record("task", 0, text, {}, toml_path.read_text() if toml_path.exists() else "")
            risk = rec["risk"]
            why = ", ".join(risk["floor_rules"]) or "default: no path rule matched"
            if rec.get("status") == "fallback":  # never hide a broken config behind the default
                why = f"fallback: {rec.get('cause')}; check herd.toml"
            print(json.dumps(rec, indent=2) if as_json else f"risk: {risk['effective']} ({why})")
    except UsageError:
        print(f"herd: usage: {USAGE[cmd]}", file=sys.stderr)
        return 1
    except (ValueError, FileNotFoundError) as e:
        print(f"herd: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
