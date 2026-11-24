#!/usr/bin/env python3
"""herd: the evidence harness. Standard library only, Python 3.11+.

A task is `.herd/tasks/<slug>/task.toml`: a goal plus success criteria, each with a
`check` command. `herd verify` runs the checks and stores evidence. `herd gate` (the
Stop hook) and `herd done` refuse to finish without fresh, passing evidence and the run rules:
red first, the standard attacks, frozen human criteria and, at medium and high risk, a review.
"""
import sys

if sys.version_info < (3, 11):  # keep this block parseable by old Pythons: it runs before tomllib is imported
    if sys.argv[1:2] in (["gate"], ["lint"], ["preinit"]):
        sys.exit(0)  # a hook must never break the session; the CLI says why below
    sys.exit("herd needs Python 3.11 or newer, found " + sys.version.split()[0])
if sys.argv[1:2] == ["preinit"]:  # the PreToolUse hook runs before every Bash command: leave before the imports
    PREINIT_RAW = sys.stdin.read() if not sys.stdin.isatty() else ""
    if "herd.py" not in PREINIT_RAW or "init" not in PREINIT_RAW:
        sys.exit(0)

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
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
NOTE_KINDS = ("found", "fixed", "open", "tried", "decision", "late-red", "review", "human-change")
# red first: files that do not count as code written before the first verify
DOC_EXT = (".md", ".rst", ".txt",  # docs, and setup and config files
           ".toml", ".json", ".yaml", ".yml", ".cfg", ".ini", ".lock")
TEST_DIRS = {"test", "tests", "spec", "specs", "__tests__", "testdata", "fixtures"}
TEST_FILE = re.compile(r"^test_.*|.*_test\.[^.]+$|.*\.(test|spec)\.[^.]+$|.*_spec\.[^.]+$|^conftest\.py$")
LEVELS = ("low", "medium", "high")
ESCALATE_AFTER = 3  # consecutive failing verifies of one criterion before the agent must ask the human
# the standard attacks of the adversarial pass (skills/run/adversarial.md): `herd done` needs a tried note for each
ATTACKS = {"bad-input": "bad input at every entry point ends in a clear message, never a traceback",
           "collision": "two inputs on the same key or position each still count",
           "one-bad-part": "one broken entry the request does not ask for does not reject the whole input, while a broken requested one still fails clearly",
           "recount": "every reported number recomputed from the output with separate code, on the generated and "
                      "collision inputs too"}
RANDOM = re.compile(r"\b(random\w*|seed(s|ed)?|fuzz\w*|property[- ]based|property tests?|hypothesis)\b", re.I)
UNIVERSAL = re.compile(r"\b(any|every|all|whatever|whichever|arbitrary)\b", re.I)  # a human claim over all inputs
# ponytail: a word list, so it misses limits worded otherwise and flags some harmless ones; it never blocks
NARROWS = re.compile(r"\b(only|first|rejected|rejects?|refused|refuses?|cannot|can't|unsupported|not supported|"
                     r"not handled|assumes?|assumed|ignored|ignores?|limited to|skipped|skips?|dropped|drops?|"
                     r"excluded|excludes?|omitted|omits?|unreachable|not reached)\b", re.I)
MAX_NARROWED = 5


def narrowing(criteria, known_limits):
    """(human any/every claims as 'C1 says "any"', known-limit sentences that narrow them). Open notes are left
    out: the report already lists them under Not proven."""
    claims = [f"{c.get('id', '?')} says '{m.group(0)}'" for c in criteria
              if c.get("source") == "human" and (m := UNIVERSAL.search(str(c.get("text", ""))))]
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", str(known_limits or ""))  # not at ';', 'e.g.' or decimals
    hits = list(dict.fromkeys(s.strip() for s in sentences if s.strip() and NARROWS.search(s)))
    return (claims, hits) if claims else ([], [])


def narrowed_claims(ev, notes=()):
    """One line per known limit that narrows a human any/every claim: shown as not proven, for the human."""
    claims, hits = narrowing(ev.get("results", []), ev.get("known_limits"))
    out = [f"{', '.join(claims)}; narrowed by: {s}" for s in hits[:MAX_NARROWED]]
    return out + ([f"and {len(hits) - MAX_NARROWED} more narrowing limits in known_limits"]
                  if len(hits) > MAX_NARROWED else [])
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
    toml_path = Path(root) / "herd.toml"
    risk = herd_triage.build_record("task", 0, goal + "\n" + (request or ""), {},
                                    toml_path.read_text() if toml_path.exists() else "")["risk"]["effective"]
    head = _git(root, "rev-parse", "HEAD").decode().strip() or None  # red first: what changed since here
    # ponytail: hashes every uncommitted file once at init (about 1 s per 20k small files); a git stat cache if slower
    changed = changed_since(root, head) or []
    edits = _take_preinit(root, slug, changed)  # what this session edited before init is the agent's, uncommitted or not
    dirty = {f: _file_sha(root, f) for f in changed if f not in edits}  # already there: not the agent's,
    (d / "start.json").write_text(json.dumps({"head": head, "risk": risk, "dirty": dirty,  # while unchanged
                                              "stashes": _stash_shas(root)} | ({"agent_edits": edits} if edits else {}))
                                  + "\n")
    if request is not None:
        (d / "request.md").write_text(request)
    (Path(root) / ".herd" / "active").write_text(slug + "\n")


def cancel_task(root, slug, reason=""):
    """Abandon a task. Its files stay as a record; the Stop gate no longer blocks on it."""
    d = _dir(root, slug)
    if not (d / "task.toml").exists():
        raise ValueError(f"no task {slug}")
    (d / "cancelled").write_text(json.dumps({"at": now(), "reason": reason.strip()}) + "\n")
    if active_slug(root) == slug:  # a task already done or cancelled did not stop now: keep its record
        _stop(root, slug, "cancelled", reason.strip())
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


def task_branch(root, slug):
    """Put a plain init's work on its own branch herd/<slug>, cut from the current one (uncommitted changes
    come along). Returns (base branch or None, warning or None); outside git it does nothing."""
    if not _git(root, "rev-parse", "--git-dir"):
        return None, None
    base = _branch(root)
    if base == f"herd/{slug}":
        return None, None
    if base in ("", "HEAD"):
        return None, f"HEAD is detached or the repository has no commit yet: create branch herd/{slug} yourself"
    p = subprocess.run(["git", "switch", "-c", f"herd/{slug}"], cwd=root, capture_output=True, text=True)
    if p.returncode:
        return None, f"could not create branch herd/{slug}: {p.stderr.strip()[-200:]}"
    (_dir(root, slug) / "base").write_text(base + "\n")  # `herd pr` targets it
    return base, None


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
        u = UNIVERSAL.search(str(c.get("text", "")))
        if u and VARIES.search(cov) and not RANDOM.search(cov):  # shapes the agent designs share the code's blind spots
            out.append(f"{cid}: human criterion says '{u.group(0)}' but its `coverage` names no random inputs "
                       "(random, seeded or fuzzed cases the agent did not design)")
        if sc and not SCALED.search(cov):
            out.append(f"{cid}: human criterion says '{sc.group(0)}' but its `coverage` has no scale statement "
                       "(largest size tried, time limit)")
    claims, hits = narrowing(task.get("criteria", []), task.get("known_limits"))
    if hits:
        out.append(f"{', '.join(claims)}, but {len(hits)} known limit{'s' if len(hits) > 1 else ''} narrow"
                   f"{'' if len(hits) > 1 else 's'} it (\"{hits[0]}\"): test the claim under each limit, or lift it; "
                   "each is shown to the human as not proven")
    if task.get("route", "standard") != "quick" and not str(task.get("known_limits", "")).strip():
        out.append("no `known_limits`: say under what conditions the claim may fail or has not been shown")
    return out


# ---- evidence -------------------------------------------------------------

PREINIT_MAX_AGE = 600  # seconds: the hook runs right before `herd init`; an older record is another run's
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def _preinit_path(root, slug):
    """The hook's record for one task, inside .git (shared by worktrees, never committed)."""
    common = _git(root, "rev-parse", "--git-common-dir").decode().strip()
    return (Path(root) / common).resolve() / f"herd-preinit-{slug}.json" if common and SLUG.fullmatch(slug) else None


def _init_target(command, cwd):
    """(folder, slug) when a Bash command runs `herd.py init <slug>`, else None. Follows a leading `cd <dir> &&`."""
    try:
        words = shlex.split(command)
    except ValueError:
        return None
    where = Path(cwd)
    if len(words) > 2 and words[0] == "cd" and words[2] in ("&&", ";"):
        where = (where / words[1]).resolve()
    for i, w in enumerate(words[:-2]):
        if w.endswith("herd.py") and words[i + 1] == "init":
            slug = next((x for x in words[i + 2:] if not x.startswith("-")), "")
            return (where, slug) if SLUG.fullmatch(slug) else None
    return None


def _edited_files(log):
    """Absolute paths the session (and its subagents) edited with Edit, Write, MultiEdit or NotebookEdit."""
    logs = [log] + sorted((log.parent / log.stem / "subagents").glob("*.jsonl"))
    files = set()
    for f in logs:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                content = json.loads(line).get("message", {}).get("content", [])
            except (ValueError, AttributeError):
                continue
            for c in content if isinstance(content, list) else []:
                inp = c.get("input") if isinstance(c, dict) and c.get("type") == "tool_use" else None
                if c.get("name") in EDIT_TOOLS and isinstance(inp, dict):
                    path = inp.get("file_path") or inp.get("notebook_path")
                    if isinstance(path, str) and path:
                        files.add(path)
    return files


def preinit(hook):
    """PreToolUse hook on Bash. Right before `herd init <slug>`, record the files this session (and its subagents)
    edited, from the session log, so red first counts them as the agent's even if they are uncommitted at init.
    The record is per task and always written, so another task's init never reads it. Never blocks, prints
    nothing; other commands return at once. ponytail: edits made through Bash (sed, cat >) are not seen."""
    if not isinstance(hook, dict):
        return
    cwd = Path(str(hook.get("cwd") or "."))
    target = _init_target(str((hook.get("tool_input") or {}).get("command", "")), cwd)
    if not target:
        return
    where, slug = target
    log = Path(str(hook.get("transcript_path") or ""))
    files = _edited_files(log) if log.is_file() else set()
    record = _preinit_path(where, slug)
    if record:
        record.write_text(json.dumps({"at": datetime.now(timezone.utc).timestamp(),
                                      "files": sorted(str((cwd / f).resolve()) for f in files)}))


def _take_preinit(root, slug, changed):
    """The hook's record for this task, consumed: changed paths (relative to root) the session edited before init."""
    target = _preinit_path(root, slug)
    if not target or not target.exists():
        return []
    rec = _state(target, {})
    target.unlink(missing_ok=True)
    try:
        if datetime.now(timezone.utc).timestamp() - float(rec.get("at") or 0) > PREINIT_MAX_AGE:
            return []
        base = Path(root).resolve()
        edited = {str(Path(f).relative_to(base)) for f in rec.get("files") or []
                  if isinstance(f, str) and Path(f).is_relative_to(base)}
    except (TypeError, ValueError):  # a hand-edited record never stops `herd init`
        return []
    return sorted(f for f in changed if f in edited)


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


def content_id(root):
    """Git tree id of the working tree's content, ignoring .herd/: the same before and after a commit."""
    index = _git(root, "rev-parse", "--git-path", "index").decode().strip()
    if not index:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        tmp_index = Path(tmp) / "index"
        try:
            shutil.copy(Path(root) / index, tmp_index)  # reuses git's file cache: only changed files are hashed
        except OSError:
            pass
        env = dict(os.environ, GIT_INDEX_FILE=str(tmp_index))
        run = lambda *a: subprocess.run(["git", *a], cwd=root, env=env, capture_output=True, text=True)  # noqa: E731
        if run("add", "-A", "--", *OWN_FILES).returncode:
            return None
        out = run("write-tree")
        return out.stdout.strip() if out.returncode == 0 else None


def _task_sha(root, slug):
    return hashlib.sha1((_dir(root, slug) / "task.toml").read_bytes()).hexdigest()


def _state(path, default):
    """One of Herd's own small JSON state files; a missing or corrupt one counts as `default`, never an error."""
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return default
    return data if isinstance(data, dict if default is None else type(default)) else default


def _file_sha(root, path):
    try:
        return hashlib.sha1((Path(root) / path).read_bytes()).hexdigest()
    except OSError:
        return None


def _stash_shas(root):
    return [s.split("\t", 1)[0] for s in _git(root, "stash", "list", "--format=%H%x09%gs").decode().splitlines()]


def _stashed_since(root, before):
    """Stash entries made on this branch since `herd init` (before: the stash ids then): a way to hide code
    from the red run. The stash list is shared by all worktrees; a branch is checked out in only one."""
    if before is None:
        return []
    branch = _branch(root)
    branch = "(no branch)" if branch in ("", "HEAD") else branch
    subject = re.compile(r"(WIP on|On) " + re.escape(branch) + ":")
    return [s.split("\t", 1)[1] for s in _git(root, "stash", "list", "--format=%H%x09%gs").decode().splitlines()
            if "\t" in s and s.split("\t", 1)[0] not in before and subject.match(s.split("\t", 1)[1])]


BUILT_EXT = (".pyc", ".pyo", ".class", ".o", ".so", ".dylib", ".dll", ".exe", ".log")
BUILT_DIRS = {"__pycache__", "node_modules", ".pytest_cache", ".mypy_cache", ".ruff_cache"}  # never source code;
# build/, dist/ and target/ can be (cmd/dist/main.go), and real build output is normally gitignored


def is_code(path, root=None):
    """A changed path that counts as code for red first: not Herd's own state, docs, config, tests or build
    output; a file without an extension only with a shebang."""
    parts = Path(path).parts
    if not parts or parts[0] == ".herd" or path.lower().endswith(DOC_EXT + BUILT_EXT) or BUILT_DIRS & set(parts):
        return False  # Herd's state, docs, config, and what running the code leaves behind
    name = parts[-1]
    if name.startswith(".") or TEST_DIRS & {s.lower() for s in parts[:-1]}:  # .gitignore; anything under tests/
        return False
    if "." not in name:  # README, LICENSE, Makefile are not code; an executable script with a shebang is
        try:
            return root is not None and (Path(root) / path).read_bytes()[:2] == b"#!"
        except OSError:
            return False
    return not (TEST_DIRS & {s.lower() for s in parts[:-1]} or TEST_FILE.match(name))


def changed_since(root, head):
    """Paths (relative to root) changed since commit head, tracked or new; None when that cannot be told."""
    if not head:
        return None
    p = subprocess.run(["git", "diff", "--name-only", "--relative", "--diff-filter=d", head], cwd=root,
                       capture_output=True, text=True)
    if p.returncode:
        return None
    new = _git(root, "ls-files", "--others", "--exclude-standard").decode().splitlines()
    return sorted({x for x in p.stdout.splitlines() + new if x and not x.startswith(".herd/")})


def risk_of(root, start, changed):
    """Effective risk: the higher of the level stored at init and the level the changed files match."""
    toml_path = Path(root) / "herd.toml"
    try:
        rules, _ = herd_triage._rules_from(toml_path.read_text() if toml_path.exists() else "")
    except (OSError, ValueError, tomllib.TOMLDecodeError):  # unreadable rules fail closed
        return {"start": start.get("risk"), "changed": "high", "effective": "high", "rules": ["herd.toml unreadable"]}
    level, matched = "low", []
    if changed:
        found, matched, _src = herd_triage.floor(changed, {}, rules)
        level = found if matched else "low"
    begin = start.get("risk") if start.get("risk") in LEVELS else "medium"
    effective = max(begin, level, key=LEVELS.index)
    return {"start": begin, "changed": level, "effective": effective, "rules": matched}


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
    attacks, ran = [], {}  # each standard-attack note's command runs like a criterion check, once per verify
    for n in load_notes(root, slug):
        if n["kind"] != "tried" or not n.get("attack"):
            continue
        a = {"attack": n["attack"], "text": n["text"], "at": n["at"], "check": n.get("check"), "exit_code": None,
             "output_tail": "", "zero_tests": False,
             # no command counts only as a stated n/a, never by default (old notes, hand-edited logs)
             "status": "na" if n["text"].strip().lower().startswith("n/a:") else "nocheck"}
        if a["check"]:
            key = (a["check"], n.get("timeout_s", DEFAULT_TIMEOUT))
            if key not in ran:
                ran[key] = run_check(root, a["check"], key[1], full=True)
            a["exit_code"], out = ran[key]
            a["output_tail"] = out[-TAIL_CHARS:]
            a["status"] = "passing" if a["exit_code"] == 0 else "failing"
            a["zero_tests"] = a["status"] == "passing" and ran_zero_tests(out)
            a["vacuous"] = bool(VACUOUS.fullmatch(a["check"]))  # runs no project code: proves nothing
        attacks.append(a)
    head = _git(root, "rev-parse", "HEAD").decode().strip() or "none"
    dirty = bool(_git(root, "status", "--porcelain", "--", *OWN_FILES).strip())
    d = _dir(root, slug)
    if (d / "started").exists() and not (d / "start.json").exists():  # a task from before Herd 0.4.0, or deleted:
        req = d / "request.md"  # red first cannot be checked (the gate wants a --late-red reason), the risk is
        toml_path = Path(root) / "herd.toml"  # triaged again from the goal and the request, and the criteria
        risk = herd_triage.build_record("task", 0, task["goal"] + "\n" + (req.read_text() if req.exists() else ""), {},
                                        toml_path.read_text() if toml_path.exists() else "")["risk"]["effective"]
        (d / "start.json").write_text(json.dumps({"head": None, "legacy": True, "risk": risk}) + "\n")
        if not (d / "frozen.json").exists():  # are frozen from now on
            (d / "frozen.json").write_text(json.dumps(
                {c["id"]: {"text": c["text"], "source": c["source"], "check": c["check"]} for c in task["criteria"]}))
    start = _state(d / "start.json", {})  # missing or corrupt: red first and the stored risk are unknown
    changed = changed_since(root, start.get("head"))
    red_path, frozen_path = d / "red.json", d / "frozen.json"
    checked = [r for r in results if r["status"] != "unchecked"]
    pre = start.get("dirty") or {}
    pre = pre if isinstance(pre, dict) else {}
    mine = None if changed is None else [f for f in changed  # a file dirty at init is the agent's once it changes
                                         if f not in pre or (pre[f] is not None and pre[f] != _file_sha(root, f))]
    snapshot = {c["id"]: {"text": c["text"], "source": c["source"], "check": c["check"]} for c in task["criteria"]}
    lost = [f.name for f in (d / "start.json", red_path, frozen_path) if f.exists() and _state(f, None) is None]
    if (d / "evidence.json").exists() and not frozen_path.exists():
        lost.append("frozen.json")  # deleted after the first verify: never re-freeze the edited criteria
    elif not frozen_path.exists():  # the human criteria are frozen at the first verify, checked or not
        frozen_path.write_text(json.dumps(snapshot))
    first = not red_path.exists() and bool(checked)
    if first:  # first verify with a runnable check: how many were red, and what code already existed
        fz = _state(frozen_path, {})  # the checks the red run saw are the baseline for "check changed"
        frozen_path.write_text(json.dumps({cid: dict(fz.get(cid, s), check=s["check"]) for cid, s in snapshot.items()}
                                          | {cid: c for cid, c in fz.items() if cid not in snapshot}))
        red_path.write_text(json.dumps({
            "at": now(), "at_epoch": datetime.now(timezone.utc).timestamp(),
            "failed": sum(r["status"] == "failing" for r in checked), "total": len(checked),
            "code_before": None if mine is None else [f for f in mine if is_code(f, root)], "seen": mine or [],
            "stashed": _stashed_since(root, start.get("stashes"))}))
    red = _state(red_path, {}) or None
    red_unreadable = sorted(set(lost)) or False
    hidden = []  # code that existed before the first verify but was moved aside for it (mv keeps the mtime)
    if red and mine is not None and red.get("at_epoch"):
        for f in mine:
            try:
                old = (Path(root) / f).stat().st_mtime < red["at_epoch"] - 1
            except OSError:
                old = False
            if is_code(f, root) and f not in set(red.get("seen") or []) and old:
                hidden.append(f)
    frozen = _state(frozen_path, {})
    for n in load_notes(root, slug) if not lost else []:  # the human changed their own criterion:
        cid = n["text"].split(":", 1)[0].strip() if n["kind"] == "human-change" else None  # `--human-change "C1: ..."`
        if (cid in frozen and cid not in snapshot and frozen[cid].get("by_note") != n["at"]
                and re.search(r"\b(drop|dropped|remove|removed|delete|deleted)\b", n["text"], re.I)):
            del frozen[cid]  # the human dropped it: a note that says so, not one already used for a rewording
            frozen_path.write_text(json.dumps(frozen))
        elif (cid in snapshot and frozen.get(cid) != snapshot[cid] and frozen.get(cid, {}).get("by_note") != n["at"]
              and _squash(snapshot[cid]["text"]) in _squash(n["text"])):  # the note quotes the new wording
            frozen[cid] = dict(snapshot[cid], by_note=n["at"])
            frozen_path.write_text(json.dumps(frozen))
    frozen = {cid: {k: v for k, v in c.items() if k != "by_note"} for cid, c in frozen.items()}
    now_by_id = {c["id"]: c for c in task["criteria"]}
    human_changed = [(cid, "removed" if cid not in now_by_id else "changed") for cid, c in frozen.items()
                     if c["source"] == "human" and (cid not in now_by_id or now_by_id[cid]["text"] != c["text"]
                                                    or now_by_id[cid]["source"] != "human")]
    checks_changed = [cid for cid, c in now_by_id.items() if frozen and cid in frozen and c["check"] != frozen[cid]["check"]]
    human_checks = [cid for cid in checks_changed if frozen[cid]["source"] == "human"]
    added = [cid for cid in now_by_id if frozen and cid not in frozen]
    req_path = d / "request.md"
    request_text = req_path.read_text() if req_path.exists() else None
    human_not_verbatim = human_unquoted(task, request_text)
    warnings = check_warnings(task, request_text) + coverage_warnings(task) + length_warnings(task)
    fails_path = d / "fails.json"  # consecutive failing verifies per criterion, for the escalation rule
    fails = _state(fails_path, {})
    fails = {r["id"]: fails.get(r["id"], 0) + 1 if r["status"] == "failing" and not first else 0 for r in results}
    fails_path.write_text(json.dumps(fails))  # the intended red run is not a failed attempt
    if summary["passing"] and not summary["failing"] and not (d / "green.json").exists():
        # all checks passed for the first time; "notes" orders it among the notes (timestamps are to the second)
        (d / "green.json").write_text(json.dumps({"at": now(), "notes": len(load_notes(root, slug))}))
    timing, started_path = None, _dir(root, slug) / "started"
    if started_path.exists():  # wall clock from `herd init`, so it includes any waiting on the human
        started = started_path.read_text().strip()
        timing = {"started_at": started, "elapsed_s": _secs(started, now())}
        if red:
            timing["first_verify_s"] = _secs(started, red["at"])
    ev = {"task": slug, "goal": task["goal"], "at": now(), "head": head, "dirty": dirty,
          "route": task.get("route", "standard"), "test_budget": task.get("test_budget"),
          "known_limits": task.get("known_limits"), "notes": load_notes(root, slug),
          "red": {"failed": red.get("failed", 0), "total": red.get("total", 0), "code_before": red.get("code_before"),
                  "code_hidden": hidden, "stashed": red.get("stashed") or []} if red else None, "red_unreadable": red_unreadable, "timing": timing,
          "human_not_verbatim": human_not_verbatim, "risk": risk_of(root, start, changed if changed is not None else changed_since(root, "HEAD")),
          "legacy": bool(start.get("legacy") or not start), "human_changed": human_changed, "checks_changed": checks_changed, "human_checks_changed": human_checks,
          "added_after_red": added,
          "warnings": warnings, "escalate": [cid for cid, n in fails.items() if n >= ESCALATE_AFTER],
          "fingerprint": fingerprint(root), "content": content_id(root), "task_sha": _task_sha(root, slug),
          "results": results, "summary": summary, "attacks": attacks}
    (_dir(root, slug) / "evidence.json").write_text(json.dumps(ev, indent=2))
    return ev


def add_note(root, slug, kind, text, attack=None, check=None, timeout=None, extra=None):
    """Append a note to the task's log: one of NOTE_KINDS (found, fixed, open for a known limit, tried for an
    adversarial attempt, decision, late-red, review, human-change).

    attack names which standard attack a tried note covers (one of ATTACKS); check is the command that
    shows it, run by `herd verify`. An attack that cannot apply has no check and text starting `n/a:`."""
    if kind not in NOTE_KINDS:
        raise ValueError(f"note kind must be one of {NOTE_KINDS}")
    if attack is not None and (kind != "tried" or attack not in ATTACKS):
        raise ValueError(f"--attack goes with --tried and is one of: {', '.join(ATTACKS)}")
    if check is not None and (attack is None or not check.strip()):
        raise ValueError("--check goes with --attack and needs a command")
    if timeout is not None and (check is None or timeout <= 0):
        raise ValueError("--timeout goes with --check and is a positive number of seconds")
    if not text.strip():
        raise ValueError("note text is empty")
    if attack and check is None and not text.strip().lower().startswith("n/a:"):
        raise ValueError(f'--attack {attack} needs --check "<command that shows the attack>", run by herd verify; '
                         'an attack that cannot apply needs text starting "n/a:" with the reason')
    d, started = _dir(root, slug), _dir(root, slug) / "started"
    t = now()
    rec = {"at": t, "kind": kind, "text": text.strip(),
           "elapsed_s": _secs(started.read_text().strip(), t) if started.exists() else None}
    if attack:
        rec["attack"] = attack
    if check is not None:
        rec["check"] = check.strip()
    if timeout is not None:
        rec["timeout_s"] = timeout
    rec.update(extra or {})
    with open(d / "notes.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")


def add_review(root, slug, by=None, text="", skipped=False):
    """Record the fresh-context review: who reviewed and what they found, or why it was skipped."""
    if not text.strip() or bool(by and by.strip()) == bool(skipped):
        raise ValueError('use `herd review --by "<reviewer>" "<what they found>"` or `herd review --skipped "<why>"`')
    ev = load_evidence(root, slug) or {}  # the code state the review saw: it counts only for that state and risk
    extra = {"skipped": True} if skipped else {"by": by.strip()}
    extra.update({"content": ev.get("content"), "risk": (ev.get("risk") or {}).get("effective")})
    add_note(root, slug, "review", text, extra=extra)


def review_needed(ev):
    """The standard route at medium and high risk needs a fresh-context review."""
    return ev.get("route") != "quick" and (ev.get("risk") or {}).get("effective") in ("medium", "high")


def review_state(root, slug, ev, notes):
    """(counts, why not): the latest review counts only after all checks first passed, at the current risk or
    above, and at high risk only for the content it saw (a commit alone does not change that)."""
    rv = [n for n in notes if n["kind"] == "review"]
    if not rv:
        return False, "no review recorded"
    n, green = rv[-1], _state(_dir(root, slug) / "green.json", {})
    if not green or notes.index(n) < green.get("notes", len(notes)):
        return False, "the review was recorded before all checks first passed: review the finished change"
    risk = (ev.get("risk") or {}).get("effective", "medium")
    if n.get("risk") not in LEVELS:
        return False, "the review was recorded before any `herd verify`: review the finished change"
    if LEVELS.index(n["risk"]) < LEVELS.index(risk):
        return False, f"the risk rose to {risk} after the review: review again"
    if risk == "high" and n.get("content") != ev.get("content"):  # a commit alone does not change the content
        return False, "the code changed after the review, and the risk is high: review the final change"
    return True, None


def final_report(root, slug, ev, notes):
    """The run skill's seven-line final report, filled from the evidence and the notes."""
    results = ev["results"]
    proven = [r for r in results if r["status"] == "passing" and not r.get("zero_tests")]
    branch = _branch(root) or "no branch"
    done = (f"{ev['goal']}; committed on {branch} at {ev['head'][:7]}" if not ev.get("dirty")
            else f"{ev['goal']}; not committed, on {branch}")
    pr = _dir(root, slug) / "pr"
    where = str((_dir(root, slug) / "evidence.md").relative_to(root)) + (f" and {pr.read_text().strip()}" if pr.exists() else "")
    gaps = [f"{r['id']} {r['status']}" for r in results if r["status"] != "passing"]
    gaps += [f"{r['id']} ran zero tests" for r in results if r.get("zero_tests")]
    gaps += [n["text"] for n in notes if n["kind"] == "open"] + _rule_lines(ev, notes)
    review = _review(notes)
    if ev.get("route") != "quick" and (review is None or review.startswith("skipped:")):
        gaps.append("unreviewed")
    caveats = [f"{n['kind']}" + (f" at {fmt_duration(n['elapsed_s'])}" if n.get("elapsed_s") is not None else "")
               + f": {n['text']}" for n in notes if n["kind"] in ("found", "fixed")]
    stop = load_stop(root, slug)
    caveats = ([stop_line(stop)] if stop else []) + caveats
    decisions = [n["text"] for n in notes if n["kind"] == "decision"]
    return [f"Done: {done}.",
            f"Proven: {len(proven)} of {len(results)} criteria; evidence in {where}.",
            f"Not proven: {'; '.join(gaps) if gaps else 'nothing open'}.",
            f"Caveats: {'; '.join(caveats) if caveats else 'none'}.",
            f"Decisions: {' | '.join(decisions) if decisions else 'none recorded'}.",
            f"Limits: {(ev.get('known_limits') or 'none stated').rstrip('.')}.",
            f"Review: {review or ('not needed (quick route)' if ev.get('route') == 'quick' else 'none recorded')}".rstrip('.') + "."]


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


def _attack_state(a):
    return "vacuous" if a.get("vacuous") else "zero" if a.get("zero_tests") else a["status"]


def _attack_states(attacks):
    """State per standard attack from its latest note: (state, command or n/a text). A later note replaces an
    earlier one, so a mistyped or renamed command never blocks for good; earlier commands that now fail
    stay visible through _superseded_failing."""
    return {a["attack"]: (_attack_state(a), a.get("check") or a["text"]) for a in attacks or []}


def _superseded_failing(attacks):
    """Earlier commands, replaced by a later note for the same attack, that fail at this verify."""
    latest = {a["attack"]: i for i, a in enumerate(attacks or [])}
    return [a for i, a in enumerate(attacks or []) if a["status"] == "failing" and latest[a["attack"]] != i]


def _attack_line(notes, attacks):
    """`Adversarial pass: ...` with each standard attack's verified state; None when nothing was tried."""
    tried = [n for n in notes if n["kind"] == "tried"]
    if not tried:
        return None
    best = _attack_states(attacks)
    words = {"passing": "passing", "failing": "failing", "zero": "ran zero tests", "vacuous": "runs no project code"}
    parts = [f"{a} {best[a][1]}" if best[a][0] == "na" else f"{a} has no command" if best[a][0] == "nocheck"
             else f"{a} {words[best[a][0]]} (`{best[a][1]}`)" for a in ATTACKS if a in best]
    missing = [a for a in ATTACKS if a not in best]
    return (f"Adversarial pass: {len(tried)} attempt{'s' if len(tried) != 1 else ''} recorded"
            + (f"; {'; '.join(parts)}" if parts else "") + (f"; missing: {', '.join(missing)}" if missing else ""))


def _review(notes):
    """The latest review note as one phrase: "<who>: <what>", "skipped: <why>", or None."""
    rv = [n for n in notes if n["kind"] == "review"]
    if not rv:
        return None
    n = rv[-1]
    return f"skipped: {n['text']}" if n.get("skipped") else f"{n.get('by', 'reviewer')}: {n['text']}"


def _early_code(ev):
    """Code files that existed before the first verify: changed before it, or moved aside for it (a stash is
    reported separately, from red.json's `stashed`)."""
    red = ev.get("red") or {}
    return sorted(set(red.get("code_before") or []) | set(red.get("code_hidden") or []))


def _rule_lines(ev, notes):
    """What the run-rule checks found, one line each: red first, criteria changes, review, warnings."""
    out = []
    code = _early_code(ev)
    if ev.get("red") and ev["red"].get("code_before") is None:
        out.append("Red first not checked: the task started before Herd 0.4.0 or with no git commit"
                   + ("; human criteria frozen only from the upgrade" if ev.get("legacy") else ""))
    if ev.get("red_unreadable"):
        out.append("Red first and the criteria freeze are unknown: Herd's state files are missing or unreadable")
    if code:
        why = [n["text"] for n in notes if n["kind"] == "late-red"]
        out.append(f"Red first not proven: {', '.join(code[:5])}{' and more' if len(code) > 5 else ''} changed "
                   "before the first verify" + (f". Reason: {why[-1]}" if why else ""))
    out += [f"{cid} was removed after the first verify" if how == "removed" else f"{cid} changed after the first verify"
            for cid, how in ev.get("human_changed") or []]
    out += [f"{cid}: check changed after the first verify, so it was never seen failing"
            for cid in ev.get("checks_changed") or []]
    out += [f"{cid}: added after the first verify, so it was never seen failing" for cid in ev.get("added_after_red") or []]
    out += narrowed_claims(ev, notes)
    if (ev.get("red") or {}).get("stashed"):
        out.append("Red first not proven: a git stash was made on this branch before the first verify")
    out += [f"Human criterion changed with the human's words, for you to confirm: {n['text']}"
            for n in notes if n["kind"] == "human-change"]
    rv = [n for n in notes if n["kind"] == "review" and not n.get("skipped")]
    if rv and rv[-1].get("content") and rv[-1]["content"] != ev.get("content"):
        out.append("The code changed after the review")
    return out


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
        lines.append(_attack_line(notes, ev.get("attacks")) or "Adversarial pass: not recorded")
    if ev.get("risk"):
        rk = ev["risk"]
        lines.append(f"Risk: {rk['effective']}" + (f" (changed files match {', '.join(rk['rules'])})" if rk["rules"] else ""))
    if ev.get("route") != "quick":
        lines.append(f"Review: {_review(notes) or 'none recorded'}")
    lines += _rule_lines(ev, notes)
    if ev.get("warnings"):
        lines += ["", "Warnings from herd check:"] + [f"- {w}" for w in ev["warnings"]]
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
    stop = load_stop(root, slug)
    if stop:
        lines += [stop_line(stop) + ".", ""]
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
    elif ev.get("route") != "quick":
        best = _attack_states(ev.get("attacks"))
        gaps += [f"- Attack {a} marked {best[a][1]}" for a in ATTACKS if best.get(a, ("",))[0] == "na"]
        gaps += [f"- Earlier {s['attack']} command now fails: `{s['check']}`" for s in _superseded_failing(ev.get("attacks"))]
        bad = [a + ("" if a not in best else {"failing": " (command fails)", "zero": " (command ran zero tests)",
                                              "nocheck": " (no command)", "vacuous": " (command runs no project code)"}
                    .get(best[a][0], "")) for a in ATTACKS if best.get(a, ("none",))[0] not in ("passing", "na")]
        if bad:
            gaps.append("- Standard attacks without a passing command: " + ", ".join(bad))
    gaps += [f"- {line}" for line in _rule_lines(ev, notes)]
    review = _review(notes)
    if ev.get("route") != "quick" and (review is None or review.startswith("skipped:")):
        gaps.append(f"- The change is unreviewed: {review[len('skipped: '):] if review else 'no review recorded'}")
    if ev.get("warnings"):
        w = ev["warnings"]
        gaps.append(f"- {len(w)} `herd check` warning{'s' if len(w) != 1 else ''}"
                    + (f", first: {w[0]}" if len(w) > 1 else f": {w[0]}"))
    lines += ["", "## What is not proven", ""] + (gaps or ["- Nothing recorded, which is unusual: ask what the checks miss"])
    details = [f"Route: {ev.get('route', 'standard')}"]
    if ev.get("red"):
        details.append(f"First verify: {ev['red']['failed']} of {ev['red']['total']} checks failed before the work")
    if ev.get("timing"):
        details.append(f"Elapsed: {fmt_duration(ev['timing']['elapsed_s'])} from `herd init` to the last verify")
    if ev.get("test_budget"):
        details.append(f"Test budget: {ev['test_budget']}")
    if _attack_line(notes, ev.get("attacks")):
        details.append(_attack_line(notes, ev.get("attacks")))
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


def pr_wanted(root):
    """True when herd.toml has `[pr] open = true`."""
    try:
        cfg = tomllib.loads((Path(root) / "herd.toml").read_text()).get("pr")
    except (OSError, tomllib.TOMLDecodeError):
        return False
    return isinstance(cfg, dict) and cfg.get("open") is True


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


# ---- stop record ----------------------------------------------------------

STOP_REASONS = ("released", "done_refused", "cancelled", "escalated")
STATE_ERRORS = (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError)  # unreadable or wrong shape
# the next action for the first problem, by the problem's wording in problems(); {0} is the first group
NEXT_STEPS = ((re.compile(r"^(.+?) is failing: "), "fix {0}, then run `herd verify`"),  # first: an id may be any text
              (re.compile(r"^(?:no evidence yet|evidence is stale|attack commands were logged)"), "run `herd verify`"),
              (re.compile(r"^no passing criterion"), "give at least one criterion a runnable check, then run `herd verify`"),
              (re.compile(r"^red first not proven"), "say why the code came before the first verify with "
                                                     "`herd note --late-red \"<why>\"`, then run `herd verify`"),
              (re.compile(r"^(?:the check of )?human criterion (\S+)"),
               "restore human criterion {0} as the human wrote it, or record the human's change with "
               "`herd note --human-change`, then run `herd verify`"),
              (re.compile(r"^review missing"), "get a fresh-context review of the finished change, record it with "
                                               "`herd review`, then run `herd verify`"),
              (re.compile(r"^adversarial pass incomplete"), "log each missing standard attack with `herd note --tried "
                                                            "--attack <name> --check \"<command>\"`, then run `herd verify`"))


def _escalations(root, slug):
    """Why the agent must ask the human now: criteria that failed ESCALATE_AFTER verifies in a row."""
    try:
        return [f"{cid} failed {ESCALATE_AFTER} times in a row" for cid in (load_evidence(root, slug) or {}).get("escalate") or []]
    except STATE_ERRORS:
        return []


def next_step(probs):
    """The action for the first problem, from NEXT_STEPS; a problem it does not know gets a generic step."""
    if not probs:
        return "run `herd done`"
    for pattern, step in NEXT_STEPS:
        m = pattern.match(probs[0])
        if m:
            return step.format(*m.groups())
    return f"fix this, then run `herd verify`: {_clip(probs[0], 200)}"


def write_stop(root, slug, reason, detail=""):
    """Write stopped.json: why the task stopped without `herd done`, what was left, and whether and how it can go on.
    `resumable` and `next` come from problems() and the state files, never from the agent."""
    if reason not in STOP_REASONS:
        raise ValueError(f"stop reason must be one of {STOP_REASONS}")
    d = _dir(root, slug)
    ev, notes, probs, lost = None, [], [], False
    try:
        ev = load_evidence(root, slug)
        if ev is not None and not isinstance(ev, dict):
            raise ValueError("not a JSON object")
    except STATE_ERRORS as e:
        ev, probs, lost = None, [f"evidence.json is unreadable: {e}"], True
    try:
        notes = load_notes(root, slug)
    except STATE_ERRORS as e:
        probs.append(f"notes.jsonl is unreadable: {e}")
        lost = True
    review = evidence = None
    if not probs:
        try:
            probs = problems(root, slug)
            if ev:
                ok, why = review_state(root, slug, ev, notes)
                latest = _review(notes)
                review = {"needed": review_needed(ev),
                          "latest": None if latest is None else _clip(latest, 200) + ("" if ok else f" (does not count: {why})")}
        except STATE_ERRORS as e:  # valid JSON of the wrong shape, a deleted task.toml
            probs, lost = [f"a state file is unreadable or has the wrong shape: {e!r}"], True
    try:  # kept when only notes.jsonl is bad
        evidence = {"verified_at": ev["at"], "sha": ev["head"], "stale": _stale(root, slug, ev)} if ev else None
    except STATE_ERRORS:
        evidence = None
    lost = lost or bool(ev and ev.get("red_unreadable"))
    causes = _escalations(root, slug)
    if reason == "cancelled":
        resumable, step = False, "start a new task"
    elif lost:
        resumable, step = False, "a human restores the state files, or cancels"
    elif reason == "escalated" or causes:
        resumable, step = False, "the human answers one question about: " + "; ".join(causes or [detail])
    else:
        resumable, step = True, next_step(probs)
        if not probs and _git(root, "status", "--porcelain", "--", *OWN_FILES).strip():
            step = "commit the work, run `herd verify`, then run `herd done`"
    if causes and not detail:  # released while an escalation is open: the reason alone would hide it
        detail = "; ".join(causes)
    try:
        elapsed = _secs((d / "started").read_text().strip(), now())
    except (OSError, ValueError):  # missing or hand-edited: the rest of the record still counts
        elapsed = None
    rec = {"at": now(), "reason": reason, "detail": detail, "problems": probs,
           "evidence": evidence, "review": review,
           # blocked stop attempts: on problems, or reminders to run `herd done` (done_refused)
           "elapsed_s": elapsed, "gate_blocks": max(_count(d / "gate_blocks"), _count(d / "done_blocks")),
           "resumable": resumable, "next": step}
    (d / "stopped.json").write_text(json.dumps(rec, indent=2) + "\n")
    return rec


def _stop(root, slug, reason, detail=""):
    """write_stop for the gate and cancel: a failure is one stderr line, never a broken hook or a lost cancel."""
    try:
        write_stop(root, slug, reason, detail)
    except Exception as e:  # noqa: BLE001
        print(f"herd: could not write stopped.json: {e}", file=sys.stderr)


def load_stop(root, slug):
    """The stop record, or None when there is none or it is unreadable."""
    return _state(_dir(root, slug) / "stopped.json", None)


def stop_line(rec):
    """`Stopped before: <reason> at <at>`, with when `herd done` resolved it."""
    return (f"Stopped before: {rec.get('reason')} at {rec.get('at')}"
            + (f", resolved at {rec['resolved_at']}" if rec.get("resolved_at") else ""))


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
    notes = load_notes(root, slug)
    code = _early_code(ev)
    if ev.get("red_unreadable"):
        lost = ev["red_unreadable"] if isinstance(ev["red_unreadable"], list) else ["red.json or frozen.json"]
        out.append(f"{', '.join(lost)} in {_dir(root, slug)} is missing or unreadable, so red first and the criteria "
                   "freeze are lost: restore it, or cancel and start a new task")
    stashed = (ev.get("red") or {}).get("stashed")
    if (code or stashed or ev.get("legacy")) and not any(n["kind"] == "late-red" for n in notes):
        what = (f"{', '.join(code[:5])} changed before the first verify" if code
                else "a git stash was made on this branch between `herd init` and the first verify" if stashed
                else "start.json is missing (the task started before Herd 0.4.0, or the file was deleted), "
                     "so it cannot be checked")
        out.append(f"red first not proven: {what}. If that was deliberate, say why with "
                   "`herd note --late-red \"<why>\"`; it shows in the report and the PR")
    out += [f"human criterion {cid} {'was removed' if how == 'removed' else 'changed'} after the first verify: "
            "restore it exactly as the human wrote it; if the human changed it, record their words with "
            f"`herd note --human-change \"{cid}: <the human's words, quoting the new text>\"`"
            for cid, how in ev.get("human_changed") or []]
    out += [f"the check of human criterion {cid} changed after the first verify: restore it, or, if the human "
            f"changed it, record their words with `herd note --human-change \"{cid}: <the criterion text>\"`"
            for cid in ev.get("human_checks_changed") or []]
    risk = (ev.get("risk") or {}).get("effective")
    ok, why = review_state(root, slug, ev, notes)
    if review_needed(ev) and not ok:
        out.append(f"review missing ({why}): risk is {risk}. Get a fresh-context review of the finished change, "
                   "then record it with `herd review --by \"<reviewer>\" \"<what they found>\"`, "
                   "or `herd review --skipped \"<why>\"`")
    if ev.get("route") != "quick":
        ran = {(a["at"], a["text"], a.get("check")) for a in ev.get("attacks") or []}
        if any(n["kind"] == "tried" and n.get("attack") and (n["at"], n["text"], n.get("check")) not in ran
               for n in load_notes(root, slug)):
            out.append("attack commands were logged after the last verify and have not run: run `herd verify`")
        best = _attack_states(ev.get("attacks"))
        why = {"failing": "its command fails", "zero": "its command ran zero tests", "nocheck": "logged without a command",
               "vacuous": "its command runs no project code"}
        missing = [a for a in ATTACKS if best.get(a, ("none",))[0] not in ("passing", "na")]
        if missing:
            out.append("adversarial pass incomplete (skills/run/adversarial.md): "
                       + "; ".join(f"{a} ({why.get(best.get(a, ('none',))[0], 'no passing command')}): {ATTACKS[a]}"
                                   for a in missing)
                       + ". Log each with `herd note --tried --attack <name> --check \"<command>\" \"what it shows\"`,"
                       " then run `herd verify`")
    return out


def _count(path):
    """A block counter; missing or hand-edited counts as 0."""
    try:
        text = path.read_text().strip()
    except OSError:  # missing, or not a file
        return 0
    return int(text) if text.isdigit() else 0


def gate(root, hook):
    """Stop hook. None allows the stop; a dict blocks it with a reason for the agent."""
    slug = active_slug(root)
    if not slug or not _dir(root, slug).exists() or cancelled(root, slug):
        return None
    counter = _dir(root, slug) / "gate_blocks"
    try:
        probs = problems(root, slug)
    except STATE_ERRORS as e:  # a corrupt or hand-edited state file: block and say so, never crash the hook
        probs = [f"a state file of task {slug} is unreadable ({e}): a human restores it, or cancels the task"]
    if not probs:  # everything passes, but only `herd done` checks the commit and prints the final report
        counter.unlink(missing_ok=True)
        done_counter = _dir(root, slug) / "done_blocks"
        n = _count(done_counter)
        if n >= MAX_BLOCKS:  # `herd done` keeps refusing (say, it may not commit): let the agent stop and ask
            _stop(root, slug, "done_refused")
            return None
        done_counter.write_text(str(n + 1))
        commit = (" Commit first: pull requests are on, so `herd done` refuses uncommitted work; if you may not"
                  " commit, say so and stop." if _git(root, "status", "--porcelain", "--", *OWN_FILES).strip()
                  and (pr_wanted(root) or (_dir(root, slug) / "pr").exists()) else "")
        return {"decision": "block", "reason": f"Herd task `{slug}`: the evidence passes ({n + 1}/{MAX_BLOCKS})."
                f"{commit} Run `python3 {SELF} done` to close the task and print the final report, then paste it."}
    (_dir(root, slug) / "done_blocks").unlink(missing_ok=True)  # passing again later reminds about `herd done` again
    n = _count(counter)
    if n >= MAX_BLOCKS:
        _stop(root, slug, "released")
        return None
    counter.write_text(str(n + 1))
    cmd = f"python3 {SELF} verify"
    causes = _escalations(root, slug)
    if causes:
        _stop(root, slug, "escalated", "; ".join(causes))
    esc = [f"{c}: ask the human one question" for c in causes]
    reason = (f"Herd task `{slug}` is not done ({n + 1}/{MAX_BLOCKS} stop attempts blocked). "
              + "; ".join(probs + esc) + f". Run `{cmd}` after fixing. If you are stuck, ask the human one question and stop."
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
    "note": 'herd note --found|--fixed|--open|--decision|--late-red|--human-change|--tried [--attack bad-input|collision|one-bad-part|recount --check "<command>" [--timeout S]] "text"',
    "review": 'herd review --by "<reviewer>" "<what they found>"  |  herd review --skipped "<why>"',
    "detect": "herd detect",
    "lint": "herd lint [--suggest]   (without --suggest: the PostToolUse hook, reads hook JSON on stdin)",
    "verify": "herd verify [slug] [--verbose]",
    "status": "herd status [slug] [--json]   (--json: the stop record, or null)",
    "done": "herd done [slug] [--verbose]",
    "cancel": 'herd cancel [slug] [--reason "text"]',
    "pr": "herd pr [slug] [--yes]   (push the herd/* branch, open or update its PR with the evidence)",
    "gate": "herd gate   (the Stop hook, reads hook JSON on stdin)",
    "preinit": "herd preinit   (PreToolUse hook on Bash: before `herd init`, records files the session already edited)",
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
            base, warn = task_branch(root, args[0])
            if base:
                print(f"switched to new branch herd/{args[0]}, cut from {base}")
            if warn:
                print(f"warning: {warn}", file=sys.stderr)
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
            kinds = {"--found": "found", "--fixed": "fixed", "--open": "open", "--tried": "tried",
                     "--decision": "decision", "--late-red": "late-red", "--human-change": "human-change"}
            attack, args = _opt(args, "--attack")
            check, args = _opt(args, "--check")
            timeout, args = _opt(args, "--timeout")
            try:
                timeout = None if timeout is None else float(timeout)
            except ValueError:
                raise UsageError
            flags = [a for a in args if a.startswith("--")]
            rest = [a for a in args if not a.startswith("--")]
            if len(flags) != 1 or flags[0] not in kinds or len(rest) != 1:
                raise UsageError
            add_note(root, _slug_arg(root, []), kinds[flags[0]], rest[0], attack=attack, check=check, timeout=timeout)
            if check and VACUOUS.fullmatch(check.strip()):
                print(f"warning: `{check.strip()}` runs no project code, so it does not count for {attack}",
                      file=sys.stderr)
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
            words = {"failing": "failing", "zero": "passing (ran zero tests)", "vacuous": "runs no project code",
                     "nocheck": "has no command", "na": "n/a", "passing": "passing"}
            states = _attack_states(ev.get("attacks"))
            for name, (state, what) in states.items():  # attacks like criteria: only what needs attention
                if verbose or state != "passing":
                    print(f"  attack {name} {words[state]}: {what}")
            if ev.get("warnings"):  # one line here; the full list is in the report (`herd status`)
                w = ev["warnings"]
                print(f"  {len(w)} herd check warning{'s' if len(w) != 1 else ''}: {w[0]}"
                      + (" (and more: `herd check` lists them)" if len(w) > 1 else ""))
            for cid in ev.get("escalate") or []:
                print(f"  {cid} failed {ESCALATE_AFTER} times in a row: ask the human one question (see the run skill)")
            return 1 if s["failing"] or any(st == "failing" for st, _ in states.values()) else 0
        elif cmd == "status":
            as_json = "--json" in args
            slug = _slug_arg(root, [a for a in args if a != "--json"])
            stop = load_stop(root, slug)
            if as_json:
                print(json.dumps(stop, indent=2))
                return 0
            ev = load_evidence(root, slug)
            if stop:
                went_on = isinstance(ev, dict) and str(ev.get("at", "")) > str(stop.get("at", ""))
                print(f"Stopped {stop.get('at')}: {stop.get('reason')}. "
                      + (f"Resolved at {stop['resolved_at']} by herd done." if stop.get("resolved_at")
                         else "The task went on after it (newer evidence): see below." if went_on
                         else f"Next: {stop.get('next')}"))
            print(report(ev, load_notes(root, slug)) if ev else f"task {slug}: no evidence yet")
            c = cancelled(root, slug)
            if c:
                print(f"cancelled at {c['at']}" + (f": {c['reason']}" if c["reason"] else ""))
                return 0
            probs = problems(root, slug)
            print("not done: " + "; ".join(probs) if probs else "done: evidence is fresh and passing")
        elif cmd == "review":
            skipped, args = _opt(args, "--skipped")
            by, args = _opt(args, "--by")
            if (skipped is None) == (by is None) or len(args) != (0 if skipped is not None else 1):
                raise UsageError
            add_review(root, _slug_arg(root, []), by=by, text=skipped if skipped is not None else args[0],
                       skipped=skipped is not None)
            print("review recorded" + (" as skipped" if skipped is not None else f" by {by}"))
        elif cmd == "done":
            verbose = "--verbose" in args
            slug = _slug_arg(root, [a for a in args if a != "--verbose"])
            probs = problems(root, slug)
            if probs:
                print("not done: " + "; ".join(probs), file=sys.stderr)
                return 1
            if _git(root, "status", "--porcelain", "--", *OWN_FILES).strip():  # work outside a commit
                if pr_wanted(root) or (_dir(root, slug) / "pr").exists():
                    print("not done: commit the work first: pull requests are on, and the pull request must hold "
                          "exactly the verified code (commit, `herd verify`, then `herd done`)", file=sys.stderr)
                    return 1
                print("warning: uncommitted work: the evidence names the commit plus uncommitted changes; "
                      "commit on the task branch if the project allows it", file=sys.stderr)
            ev = load_evidence(root, slug)
            notes = load_notes(root, slug)
            stop = load_stop(root, slug)
            if stop and not stop.get("resolved_at"):  # the record stays; it says the task went on and finished
                stop["resolved_at"] = now()
                (_dir(root, slug) / "stopped.json").write_text(json.dumps(stop, indent=2) + "\n")
            text = report(ev, notes)
            (_dir(root, slug) / "evidence.md").write_text(text)
            (root / ".herd" / "active").unlink(missing_ok=True)
            if verbose:
                print(text)
            proven = sum(r["status"] == "passing" and not r.get("zero_tests") for r in ev["results"])
            print(f"done: evidence is fresh and passing ({proven} of {len(ev['results'])} criteria proven)")
            print(f"report: {(_dir(root, slug) / 'evidence.md').relative_to(root)}")
            print("final report (paste it as written):")
            print("\n".join(final_report(root, slug, ev, notes)))
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
        elif cmd == "preinit":  # PreToolUse hook on Bash: must never break or slow the session
            try:
                raw = globals().get("PREINIT_RAW")  # read by the fast path at the top of this file
                raw = raw if raw is not None else (sys.stdin.read() if not sys.stdin.isatty() else "")
                preinit(json.loads(raw) if raw.strip() else {})
            except Exception:  # noqa: BLE001 - a hook that fails must not stop the agent's command
                pass
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
