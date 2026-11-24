#!/usr/bin/env python3
"""herd: the evidence harness. Standard library only, Python 3.11+.

A task is `.herd/tasks/<slug>/task.toml`: a goal plus success criteria, each with a
`check` command. `herd verify` runs the checks and stores evidence. `herd gate` (the
Stop hook) and `herd done` refuse to finish without fresh, passing evidence and the run rules:
red first, the standard attacks, frozen human criteria and, at medium and high risk, a review.
"""
import sys

if sys.version_info < (3, 11):  # keep this block parseable by old Pythons: it runs before tomllib is imported
    if sys.argv[1:2] in (["gate"], ["lint"], ["preinit"], ["guard"], ["review-hook"]):
        sys.exit(0)  # a hook must never break the session; the CLI says why below
    sys.exit("herd needs Python 3.11 or newer, found " + sys.version.split()[0])
if sys.argv[1:2] == ["preinit"]:  # the PreToolUse hook runs before every Bash command: leave before the imports
    PREINIT_RAW = sys.stdin.read() if not sys.stdin.isatty() else ""
    if "herd.py" not in PREINIT_RAW or "init" not in PREINIT_RAW:
        sys.exit(0)


def _active_root(hook):
    """The nearest folder, above the hook's cwd, CLAUDE_PROJECT_DIR, the edited file or a `cd` target, that has an
    active task (`.herd/active`), or None. The session's cwd moves with `cd`, and a nested git repository has no
    `.herd`, so the cwd alone can miss the task. Standard library only, before the imports: the guard's fast path."""
    import os
    import re
    hook = hook if isinstance(hook, dict) else {}
    inp = hook.get("tool_input") if isinstance(hook.get("tool_input"), dict) else {}
    cwd = hook.get("cwd") if isinstance(hook.get("cwd"), str) and hook.get("cwd") else os.getcwd()
    starts = [cwd, os.environ.get("CLAUDE_PROJECT_DIR") or ""]
    starts += [os.path.dirname(os.path.join(cwd, inp[k])) for k in ("file_path", "notebook_path")
               if isinstance(inp.get(k), str) and inp[k]]
    if isinstance(inp.get("command"), str):
        starts += [os.path.join(cwd, os.path.expanduser(m.strip("'\""))) for m in re.findall(r"\bcd\s+(\S+)", inp["command"])]
    for start in filter(None, starts):
        d = os.path.realpath(start)
        while not os.path.isfile(os.path.join(d, ".herd", "active")):
            try:  # a git worktree has its own tasks: never reach the checkout that holds it
                with open(os.path.join(d, ".git")) as f:
                    if "/worktrees/" in f.read(500):
                        break
            except OSError:
                pass
            if os.path.dirname(d) == d:
                break
            d = os.path.dirname(d)
        else:
            return d
    return None


if sys.argv[1:2] == ["guard"]:  # the PreToolUse guard runs before every Bash command and edit: with no active
    import json  # task, leave before the other imports
    GUARD_RAW = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        _hook = json.loads(GUARD_RAW)
    except Exception:  # noqa: BLE001 - bad input (even nested too deep): the CLI path below reports it
        _hook = {}
    try:
        _found = _active_root(_hook)
    except Exception:  # noqa: BLE001 - a deleted cwd and the like: the CLI path below reports it in one line
        _found = ""
    if _found is None:
        sys.exit(0)

import fnmatch
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import tomllib
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # ponytail: Windows has no flock; parallel inits there can still race
    fcntl = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import herd_detect
import herd_triage

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
# Top level, needed at medium and high risk: test_budget = "what is and is not tested",
# known_limits = "when the claim may fail", and one [[inputs]] table per input (inputs = [] if none):
#
# [[inputs]]
# human = "the input as the human described it"
# program = "the input as the program receives it"
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
NOTE_KINDS = ("found", "fixed", "open", "tried", "decision", "late-red", "review", "human-change", "guard")
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
                      "collision inputs too",
           "refusal": "every kind of input the program refuses (cannot be reached, not found, invalid) is confirmed "
                      "refusable by separate, simpler code on generated inputs, so nothing it could serve is refused"}
REFUSAL_FIRST = ("no refusal attack yet: before building, list what the program will refuse (cannot be reached, "
                 "not found, invalid) and log `herd note --tried --attack refusal --check \"<command>\"` with "
                 "separate code; it should fail now")
# at medium and high risk on the standard route `herd done` refuses while one is empty; what to write, for the message
REQUIRED = {"test_budget": "<what is tested and what is not, at which level>",
            "known_limits": "<when the claim may fail or has not been shown>"}
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
    edits, log = _take_preinit(root, slug, changed)  # what this session edited before init is the agent's
    dirty = {f: _file_sha(root, f) for f in changed if f not in edits}  # already there: not the agent's,
    (d / "start.json").write_text(json.dumps({"head": head, "risk": risk, "dirty": dirty,  # while unchanged
                                              "stashes": _stash_shas(root)} | ({"agent_edits": edits} if edits else {})
                                             | ({"transcript": log, "sessions": [log]} if log else {})
                                             | {"review": dict(zip(("tiers", "step"), review_tiers(root)))})
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


QUOTES = str.maketrans({c: None for c in "'\"`\u2018\u2019\u201a\u201b\u201c\u201d\u201e\u00ab\u00bb\u2039\u203a"})


def _squash(s, markers=True):
    """Text as a quote compares it: what copying from Markdown, chat or a terminal changes is dropped (Unicode
    forms, case, spacing and line wraps, quotes, emphasis, code ticks, escapes, link targets, spaced dashes,
    sentence punctuation and, with markers, line-start list, heading and quote markers). Words, numbers,
    identifiers (max_len) and operators (<, >=, !=, 2*3) stay."""
    s = unicodedata.normalize("NFKC", str(s)).casefold()
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)  # [text](url) -> text
    s = re.sub(r"\\([^\w\s])", r"\1", s)  # Markdown escapes: \* -> *
    if markers:  # the request's Markdown; a criterion that starts with `> 5` keeps it
        s = re.sub(r"(?m)^[ \t]*(?:>[ \t]*)*(?:#{1,6}[ \t]+|[-*+][ \t]+|\d+[.)][ \t]+)?", "", s)
    s = re.sub(r"(?<!\w)[*_~]+|[*_~]+(?!\w)", "", s.translate(QUOTES))  # emphasis at a word's edge, not 2*3 or a_b
    s = re.sub(r"[\u2010-\u2015\u2212]", "-", s)  # every dash and minus is a hyphen
    s = re.sub(r"(?:^|(?<=\s))-+(?=\s|$)", " ", s)  # a spaced dash is punctuation
    s = re.sub(r"[.,;:!?\u2026]+(?=\s|$)", " ", s)  # sentence punctuation, not 20.5, a:b or !=
    return re.sub(r"\s+", " ", s).strip()


def _quotes(text, source):
    """text is a verbatim quote of source, as _squash compares them; an empty quote quotes nothing."""
    t = _squash(text, markers=False)
    # whole words and numbers: `return 1` is not in `return 10`, `return 1.5`, `1-2` or `1,000`
    edge_l, edge_r = r"(?<!\w)(?<!\w[.,/:-])", r"(?!\w)(?![.,/:-]\w)"
    return bool(t) and re.search(edge_l + re.escape(t) + edge_r, _squash(source)) is not None


def corrections(frozen, snapshot, request):
    """{"corrected": ids, "removed": ids} when the human criteria changed after the first verify only toward the
    request's words, else None. That holds when every human criterion now quotes the request, and every frozen human
    text that quoted it, or that the human reworded with a note, is still inside some human criterion (so none of the
    human's words was narrowed or dropped); a frozen text that did not quote the request was never the human's words.
    Removing a human criterion, or turning it agent-proposed, still needs the human's note. Only criteria whose text
    changed in words under an id frozen before are re-frozen, check included: a text unchanged but for case, spacing or
    punctuation keeps its frozen check, so a weakened check there still needs the note; a new id stays "added"."""
    now = {cid: s for cid, s in snapshot.items() if s["source"] == "human"}
    old = {cid: c for cid, c in frozen.items() if isinstance(c, dict) and c.get("source") == "human"}
    if not now or not all(_quotes(s["text"], request) for s in now.values()):
        return None
    if not all(any(_quotes(c.get("text", ""), s["text"]) for s in now.values())  # the human's words, kept
               for c in old.values() if _quotes(c.get("text", ""), request) or c.get("by_note")):
        return None
    if any(cid not in now for cid in old):  # removed, or turned agent-proposed: its check goes with it, so ask
        return None
    changed = sorted(cid for cid, s in now.items() if isinstance(frozen.get(cid), dict)  # a new id stays "added"
                     and (_squash(frozen[cid].get("text", "")) != _squash(s["text"])
                          or frozen[cid].get("source") != "human"))
    return {"corrected": changed} if changed else None


def human_unquoted(task, request, notes=()):
    """Ids of `human` criteria whose text is not a verbatim quote of the request, nor of a `human-change` note
    for that id (the human's own rewording, the note the frozen-criteria rule accepts). None if no request."""
    if request is None:
        return None
    changes = {}
    for n in notes:
        if n.get("kind") == "human-change":
            changes.setdefault(str(n.get("text", "")).split(":", 1)[0].strip(), []).append(str(n.get("text", "")))
    return [c.get("id", "?") for c in task.get("criteria", [])
            if c.get("source") == "human" and not any(_quotes(str(c.get("text", "")), src)
                                                      for src in [request] + changes.get(c.get("id"), []))]


def check_warnings(task, request=None, notes=()):
    """Advisory only: checks that cannot show the criterion holds (a denylist with known gaps),
    and human criteria that are not a verbatim quote of the human's request."""
    out = []
    if request is None:
        if any(c.get("source") == "human" for c in task.get("criteria", [])):
            out.append("no request recorded (`herd init ... --request`): cannot confirm human criteria are verbatim")
    else:
        for cid in human_unquoted(task, request, notes):
            out.append(f"{cid}: human criterion is not a verbatim quote of the request, so `herd done` refuses; quote "
                       "the human's words and put your own scenario in a separate agent-proposed criterion")
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


def inputs_line(inputs):
    """`Inputs: <as the human described it> -> <as the program receives it>`, for the human to compare."""
    return "Inputs (as you described them -> as the program receives them): " + "; ".join(
        f"{str(x.get('human', '?')).strip()} -> {str(x.get('program', '?')).strip()}" for x in inputs if isinstance(x, dict))


INPUTS_TABLE = ('`[[inputs]]`, `human = "<the input as the human described it>"`, `program = "<the input as the '
                'program receives it>"`, one line each, one table per input')


def input_warnings(task):
    """Each input of a standard task as the human described it and as the program receives it, by structure only.
    A warning at low risk; at medium and high risk `herd done` refuses while one is left (problems())."""
    ins = task.get("inputs")
    if task.get("route", "standard") == "quick":
        return []
    out = [f"{c.get('id', '?')} has an `inputs` key inside its [[criteria]] table: inputs belong at the top level "
           f"of task.toml as {INPUTS_TABLE}, not inside [[criteria]]: move them there"
           for c in task.get("criteria", []) if isinstance(c, dict) and "inputs" in c]
    if ins is None:
        return out + [f"no `inputs`: add to task.toml, at the top level, {INPUTS_TABLE} (or `inputs = []` before "
                      "the first table if it takes none), so a step the caller must do first is seen before building"]
    if not isinstance(ins, list):
        return out + [f"`inputs` must be a list of tables: write {INPUTS_TABLE}"]
    bad = [i for i, x in enumerate(ins, 1) if not (isinstance(x, dict) and str(x.get("human", "")).strip()
                                                    and str(x.get("program", "")).strip())]
    return out + [f"inputs #{i}: give `human` (the input as the human described it) and `program` (as the program "
                  "receives it)" for i in bad]


def refusal_late(root, slug, red):
    """The refusal attack first logged after the first verify (by note order, not by time): it did not shape the design."""
    notes = load_notes(root, slug)
    i = next((i for i, n in enumerate(notes) if n["kind"] == "tried" and n.get("attack") == "refusal"), None)
    if i is None or not red or not isinstance(red.get("notes"), int) or i < red["notes"]:
        return []
    return ["refusal attack was logged after the first verify, so it did not shape the design: log it before building"]


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
        record.write_text(json.dumps({"at": datetime.now(timezone.utc).timestamp(), "transcript": str(log),
                                      "files": sorted(str((cwd / f).resolve()) for f in files)}))


def _take_preinit(root, slug, changed):
    """The hook's record for this task, consumed: (changed paths, relative to root, the session edited before init;
    the session log, which `herd status` reads for the builder's model, or None)."""
    target = _preinit_path(root, slug)
    if not target or not target.exists():
        return [], None
    rec = _state(target, {})
    target.unlink(missing_ok=True)
    try:
        if datetime.now(timezone.utc).timestamp() - float(rec.get("at") or 0) > PREINIT_MAX_AGE:
            return [], None
        base = Path(root).resolve()
        edited = {str(Path(f).relative_to(base)) for f in rec.get("files") or []
                  if isinstance(f, str) and Path(f).is_relative_to(base)}
    except (TypeError, ValueError):  # a hand-edited record never stops `herd init`
        return [], None
    log = rec.get("transcript")
    return sorted(f for f in changed if f in edited), log if isinstance(log, str) and log else None


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


def task_changes(root, start, changed):
    """The changed paths that are the task's: a file already dirty at `herd init` counts once it changes again.
    None when the changes cannot be told (no commit at init)."""
    pre = start.get("dirty") or {}
    pre = pre if isinstance(pre, dict) else {}
    return None if changed is None else [f for f in changed
                                         if f not in pre or (pre[f] is not None and pre[f] != _file_sha(root, f))]


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
    mine = task_changes(root, start, changed)
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
            "at": now(), "at_epoch": datetime.now(timezone.utc).timestamp(), "notes": len(load_notes(root, slug)),
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
              and _quotes(snapshot[cid]["text"], n["text"])):  # the note quotes the new wording, as human_unquoted reads it
            frozen[cid] = dict(snapshot[cid], by_note=n["at"])
            frozen_path.write_text(json.dumps(frozen))
    req_path = d / "request.md"
    request_text = req_path.read_text() if req_path.exists() else None
    fixed = corrections(frozen, snapshot, request_text) if request_text is not None and not lost else None
    if fixed:  # the human criteria moved toward the request's words, keeping every earlier quote: re-freeze them
        for cid in fixed["corrected"]:
            frozen[cid] = dict(snapshot[cid], corrected=True)
        frozen_path.write_text(json.dumps(frozen))
    corrected = sorted(cid for cid, c in frozen.items() if c.get("corrected"))
    frozen = {cid: {k: v for k, v in c.items() if k not in ("by_note", "corrected")} for cid, c in frozen.items()}
    now_by_id = {c["id"]: c for c in task["criteria"]}
    human_changed = [(cid, "removed" if cid not in now_by_id else "changed") for cid, c in frozen.items()
                     if c["source"] == "human" and (cid not in now_by_id or _squash(now_by_id[cid]["text"]) != _squash(c["text"])
                                                    or now_by_id[cid]["source"] != "human")]
    checks_changed = [cid for cid, c in now_by_id.items() if frozen and cid in frozen and c["check"] != frozen[cid]["check"]]
    human_checks = [cid for cid in checks_changed if frozen[cid]["source"] == "human"]
    added = [cid for cid in now_by_id if frozen and cid not in frozen]
    human_not_verbatim = human_unquoted(task, request_text, load_notes(root, slug))
    inputs_left = input_warnings(task)
    warnings = (check_warnings(task, request_text, load_notes(root, slug)) + coverage_warnings(task) + length_warnings(task)
                + inputs_left
                + ([REFUSAL_FIRST] if first and not any(a.get("attack") == "refusal" for a in attacks) else [])
                + refusal_late(root, slug, red))
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
          "inputs": task.get("inputs"), "inputs_left": inputs_left, "red": {"failed": red.get("failed", 0), "total": red.get("total", 0), "code_before": red.get("code_before"),
                  "code_hidden": hidden, "stashed": red.get("stashed") or []} if red else None, "red_unreadable": red_unreadable, "timing": timing,
          "human_not_verbatim": human_not_verbatim, "risk": risk_of(root, start, changed if changed is not None else changed_since(root, "HEAD")),
          "legacy": bool(start.get("legacy") or not start), "human_changed": human_changed, "human_corrected": corrected, "checks_changed": checks_changed, "human_checks_changed": human_checks,
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


def add_review(root, slug, by, text, extra=None):
    """Record a review: who reviewed and what they found. At medium and high risk only one the review hook
    records (extra has source "hook", the tiers and the verdict) counts; `herd review --by` is a note."""
    if not text.strip() or not (by and by.strip()):
        raise ValueError('use `herd review --by "<reviewer>" "<what they found>"`')
    ev = load_evidence(root, slug) or {}  # the code state the review saw: it counts only for that state and risk
    add_note(root, slug, "review", text, extra={"by": by.strip(), "content": ev.get("content"),
                                                "risk": (ev.get("risk") or {}).get("effective")} | (extra or {}))


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
    if n.get("over_cap"):
        return False, "the review limit was reached before this review, so it cannot pass the task: stop and ask the human"
    if not green or notes.index(n) < green.get("notes", len(notes)):
        return False, "the review was recorded before all checks first passed: review the finished change"
    risk = (ev.get("risk") or {}).get("effective", "medium")
    if n.get("risk") not in LEVELS:
        return False, "the review was recorded before any `herd verify`: review the finished change"
    if LEVELS.index(n["risk"]) < LEVELS.index(risk):
        return False, f"the risk rose to {risk} after the review: review again"
    if risk == "high" and n.get("content") != ev.get("content"):  # a commit alone does not change the content
        return False, "the code changed after the review, and the risk is high: review the final change"
    return _tier_rule(root, slug, n)


def _tier_rule(root, slug, n):
    """(counts, why not) for a review note by the rules of the review hook (design B4)."""
    if n.get("source") != "hook":
        return False, "recorded by hand, not by the review hook: spawn herd-reviewer"
    tiers, step = review_tiers(root, slug)
    t = tiers.index(n["tier"]) if n.get("tier") in tiers else None
    b = tiers.index(n["builder_tier"]) if n.get("builder_tier") in tiers else None
    if t is None or b is None:
        which = "reviewer's" if t is None else "builder's"
        return False, f"the {which} model could not be read: {n.get('unread') or 'its tier is unknown'}"
    if n.get("saw") is None:
        return False, "the review was recorded before Herd 0.10.0 checked what the reviewer read: spawn herd-reviewer again"
    if not n["saw"] and n.get("diff_seen") and n.get("new_unread"):  # 0.12.1: new files are in no git diff
        return False, (f"the reviewer printed the diff but did not read these new files, which no git diff shows: "
                       f"{', '.join(n['new_unread'])}: spawn herd-reviewer again with what `herd review-brief` prints")
    if not n["saw"]:
        missed = n.get("code_unread") or []
        more = (n.get("code_total") or 0) - (n.get("code_read") or 0) - len(missed)
        return False, (f"the reviewer did not read: {', '.join(missed)}{f' and {more} more' if more > 0 else ''}, and "
                       "ran no `git diff` or `git show`: spawn herd-reviewer again and have it read the diff")
    if n.get("verdict") != "PASS":
        return False, "the review found Blocker or Major issues, or gave no verdict: fix them and review again"
    need = min(b + step, len(tiers) - 1)
    if t < need:
        return False, (f"review by {tiers[t]} does not count: the builder ran on {tiers[b]}, the reviewer must be "
                       f"{tiers[need]} or higher. Spawn herd-reviewer with model {tiers[need]}")
    return True, None


# ---- review hook ----------------------------------------------------------

REVIEWER = "herd:herd-reviewer"  # the plugin agent's agent_type (spike S3); a project's own copy does not count
DEFAULT_TIERS, DEFAULT_STEP = ("haiku", "sonnet", "opus"), 1  # 0.10.0: one tier above again (0 in 0.8 and 0.9)
VERDICT = re.compile(r"\s*HERD-REVIEW: (PASS|FAIL)\s*")
REVIEW_CHARS = 2000
READERS = {"cat", "nl", "less", "more", "head", "tail", "bat", "sed"}  # Bash commands that print a file's lines
SHOWS_CHANGE = ("git diff", "git show", "git log -p", "git log --patch")
SUMMARY_ONLY = {"--stat", "--shortstat", "--numstat", "--dirstat", "--name-only", "--name-status", "--summary",
                "--compact-summary", "--raw", "--quiet", "--no-patch", "-s", "--check", "--output"}  # no changed lines
# `path:line` or `path:first-last` in a report: a path with a file extension or a folder; not a URL, time or C1:2
REF = re.compile(r"(?<![\w/.:-])(/?(?:[\w.-]+/)*[\w-][\w.-]*\.[A-Za-z]\w*|/?(?:[\w.-]+/)+[\w.-]+):(\d+)(?:-(\d+))?(?![\w-])")
MAX_REFS = 20


def review_tiers(root, slug=None):
    """([review] tiers, lowest first, and step): for a task, as herd.toml had them at `herd init` (so an edit
    during the task cannot change the rule); otherwise from herd.toml. Unreadable or odd means the defaults."""
    cfg = _state(_dir(root, slug) / "start.json", {}).get("review") if slug else None
    if not isinstance(cfg, dict):
        try:
            cfg = tomllib.loads((Path(root) / "herd.toml").read_text()).get("review")
        except (OSError, tomllib.TOMLDecodeError):
            cfg = None
    cfg = cfg if isinstance(cfg, dict) else {}
    tiers, step = cfg.get("tiers"), cfg.get("step")
    ok = isinstance(tiers, list) and tiers and all(isinstance(t, str) and t.strip() for t in tiers)
    tiers = [t.strip().lower() for t in tiers] if ok else list(DEFAULT_TIERS)
    return tiers, step if isinstance(step, int) and not isinstance(step, bool) and step >= 0 else DEFAULT_STEP


def tier_of(model, tiers):
    """The first tier whose name the model id contains, or None."""
    return next((t for t in tiers if isinstance(model, str) and t in model.lower()), None)


def _assistant_lines(path, last_turn=False):
    """The assistant lines of a Claude Code session log, as dicts; an unreadable file gives none. With last_turn,
    only those after the last prompt (a user line that is not a tool result), so an old turn's report is not read."""
    try:
        raw = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except (OSError, TypeError, ValueError):
        return []
    out = []
    for line in raw:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict) or not isinstance(d.get("message"), dict):
            continue
        content = d["message"].get("content")
        if last_turn and d.get("type") == "user" and not (isinstance(content, list) and any(
                isinstance(c, dict) and c.get("type") == "tool_result" for c in content)):
            out = []
        elif d.get("type") == "assistant":
            out.append(d)
    return out


def _model(line):
    m = line["message"].get("model")
    return m if isinstance(m, str) and m and m != "<synthetic>" else None


def _final_text(lines):
    """The reviewer's report: the last assistant text block or SubagentHandback message (spike S3)."""
    for line in reversed(lines):
        content = line["message"].get("content")
        for c in reversed(content if isinstance(content, list) else []):
            if not isinstance(c, dict):
                continue
            if c.get("type") == "text" and isinstance(c.get("text"), str) and c["text"].strip():
                return c["text"]
            if c.get("type") == "tool_use" and c.get("name") == "SubagentHandback":
                msg = (c.get("input") or {}).get("message") if isinstance(c.get("input"), dict) else None
                if isinstance(msg, str) and msg.strip():
                    return msg
    return None


def _when(stamp):
    try:
        t = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)  # a stamp without a zone is UTC, like Herd's own


def builder_tier(path, since, tiers):
    """(the builder's highest tier among the main log's assistant lines at or after since, or None; why None)."""
    start = _when(since) if since else None
    lines = [ln for ln in _assistant_lines(path) if _model(ln)
             and (start is None or ((w := _when(ln.get("timestamp"))) is not None and w >= start))]
    if not lines:
        return None, f"no model in the main session log {path} since the task started"
    models = list(dict.fromkeys(_model(ln) for ln in lines))
    unknown = [m for m in models if tier_of(m, tiers) is None]
    if unknown:
        return None, f"{unknown[0]} matches no tier"
    return max((tier_of(m, tiers) for m in models), key=tiers.index), None


def review_need(root, slug):
    """(the tier the reviewer needs or None, the builder's tier or why it is unknown), from the latest session log
    the gate or `herd init` saw."""
    tiers, step = review_tiers(root, slug)
    log = _state(_dir(root, slug) / "start.json", {}).get("transcript")
    started = _dir(root, slug) / "started"
    try:
        since = started.read_text().strip()
    except OSError:
        since = None
    b, why = builder_tier(log, since, tiers) if isinstance(log, str) else (None, "the builder's model is not known yet")
    return (tiers[min(tiers.index(b) + step, len(tiers) - 1)], b) if b else (None, why)


def _shows_change(words, cwd):
    """A git command that prints the changed lines: diff, show, or log with a patch, without a summary-only flag."""
    if not any(_rule_hit(r, words, cwd) for r in SHOWS_CHANGE):
        return False
    if any(REDIRECT.fullmatch(w) for w in words):  # `git diff > d.txt` or `> /dev/null`: the reviewer saw nothing
        return False
    return bool({"-p", "-u", "--patch"} & set(words)) or not any(w.split("=", 1)[0] in SUMMARY_ONLY for w in words)


def reviewer_saw(root, cwd, lines):
    """(whether the reviewer ran a git command that prints the change, the files under root it read), from the tool
    calls in its log: Read, and Bash readers such as cat or sed. Shell text is read as the guard reads it."""
    base, diff, read = os.path.realpath(root), False, set()

    def rel(path, here):
        try:
            full = os.path.realpath(os.path.join(here, os.path.expanduser(path)))
        except (ValueError, OSError):  # a NUL in the path and the like: not a file it read
            return None
        return Path(full).relative_to(base).as_posix() if full.startswith(base + os.sep) else None
    for line in lines:
        content = line["message"].get("content")
        for c in content if isinstance(content, list) else []:
            inp = c.get("input") if isinstance(c, dict) and c.get("type") == "tool_use" else None
            if not isinstance(inp, dict):
                continue
            if c.get("name") == "Read" and isinstance(inp.get("file_path"), str) and inp["file_path"]:
                read.add(rel(inp["file_path"], cwd))
            elif c.get("name") == "Bash" and isinstance(inp.get("command"), str):
                here = cwd
                for words in _segments(inp["command"]):
                    name = Path(words[0]).name
                    if name in ("cd", "pushd") and len(words) > 1:
                        here = os.path.normpath(os.path.join(here, os.path.expanduser(words[1])))
                    elif name == "git":
                        diff = diff or _shows_change(words, here)
                    elif name in READERS:
                        read |= {rel(w, here) for w in words[1:] if not w.startswith("-")}
    read.discard(None)
    return diff, read


def bad_refs(root, text):
    """The `path:line` references of a report whose file is not in the repository or whose line is past its end."""
    tops = list(dict.fromkeys(os.path.realpath(t) for t in (root, toplevel(root))))
    files = None  # the repository's files, listed once, for a path given without its folders (herd.py:5)
    out = []
    for m in REF.finditer(text or ""):
        path, first, last = m[1], int(m[2]), int(m[3] or m[2])
        found = [f for t in tops if (f := os.path.realpath(os.path.join(t, path))).startswith(t + os.sep)
                 and os.path.isfile(f)][:1]
        if not found and not path.startswith(("/", "../")):
            if files is None:
                files = _git(root, "ls-files", "--cached", "--others", "--exclude-standard").decode().splitlines()
            found = [os.path.join(root, f) for f in files if f == path or f.endswith("/" + path)]
        sizes = []
        for f in found:
            try:
                sizes.append(len(Path(f).read_bytes().splitlines()))
            except OSError:
                pass
        why = ("no such file in the repository" if not sizes else None if any(1 <= first <= last <= n for n in sizes)
               else "lines start at 1" if first < 1
               else f"{path} has {max(sizes)} line{'s' if max(sizes) != 1 else ''}")
        if why and f"{m[0]} ({why})" not in out:
            out.append(f"{m[0]} ({why})")
    return out[:MAX_REFS]


def untracked(root):
    """Paths (relative to root) git does not track yet and does not ignore: in no `git diff`."""
    return set(_git(root, "ls-files", "--others", "--exclude-standard").decode().splitlines())


def review_files(root, slug):
    """(the changed files a reviewer must read unless it prints the diff, or None when the changes cannot be told;
    whether they are every changed file because no code file changed). The review hook counts against this list,
    and `herd review-brief` prints it, so the brief and the check agree."""
    start = _state(_dir(root, slug) / "start.json", {})
    mine = task_changes(root, start, changed_since(root, start.get("head")))
    code = None if mine is None else [f for f in mine if is_code(f, root)]
    files = [f for f in mine or [] if not (f.lower().endswith(BUILT_EXT) or BUILT_DIRS & set(Path(f).parts))]
    any_file = code == [] and bool(files)  # no code changed (tests, config, CI): every changed file but build output
    return (files if any_file else code), any_file


def pass_hint(root, slug, ev, notes):
    """One line once a review that counts is recorded for this content: stop working, commit, `herd done`; and what
    the review rule does with later edits at this risk. None otherwise."""
    if (not ev or not review_needed(ev) or ev["summary"]["failing"] or _stale(root, slug, ev)
            or not review_state(root, slug, ev, notes)[0]):
        return None
    later = ("at high risk any file you change after it needs another review (a commit alone does not)"
             if (ev.get("risk") or {}).get("effective") == "high" else
             "at medium risk it keeps counting after edits unless the risk rises to high, but no reviewer sees them")
    return (f"Review passed and counts: fix only Blocker and Major findings, start no new work, commit and run "
            f"`herd done`; {later}")


def review_brief(root, slug):
    """The reviewer's brief, assembled from Herd's records, for the builder to pass to herd-reviewer as it is: the
    goal, the criteria with their checks, test_budget, known_limits, the request verbatim, the inputs, the files the
    review hook will check were read, and the diff command from the commit `herd init` started from."""
    task, d = load_task(root, slug), _dir(root, slug)
    head = _state(d / "start.json", {}).get("head")
    req = (d / "request.md").read_text() if (d / "request.md").exists() else None
    files, any_file = review_files(root, slug)
    out = ["Review this finished change for Herd. Judge only what you read and run.", "", f"Goal: {task.get('goal', '')}",
           "", "Criteria (id, source, text, check):"]
    out += [f"- {c.get('id', '?')} ({c.get('source', '?')}): {c.get('text', '')}"
            + (f" Check: `{c['check']}`" if str(c.get("check") or "").strip() else " Check: none (unchecked)")
            for c in task.get("criteria", []) if isinstance(c, dict)]
    out += ["", f"Test budget: {task.get('test_budget') or 'none stated'}",
            f"Known limits: {task.get('known_limits') or 'none stated'}"]
    if isinstance(task.get("inputs"), list) and any(isinstance(x, dict) for x in task["inputs"]):
        out.append(inputs_line(task["inputs"]))
    out += ["", "The human's request, word for word:", req.strip() if req else "(none recorded)", ""]
    if files is None:
        out.append("Changed files: unknown (no commit at `herd init`): read the diff with `git diff HEAD` and "
                   "`git status`.")
    else:
        what = "changed files (no code file changed)" if any_file else "changed code files"
        out.append(f"Read every one of these {len(files)} {what} with Read before you judge, or print the whole diff:")
        out += [f"- {f}" for f in files] or ["- (none)"]
        out.append(f"Diff, committed and not: `git diff {head}`")
        new = [f for f in files if f in untracked(root)]
        if new:  # no git diff shows a file git does not track: the review hook needs these read either way
            out.append("New files, in no `git diff`: read each one with Read: " + ", ".join(new))
    return "\n".join(out) + "\n"


def review_hook(root, hook):
    """SubagentStop hook for the herd-reviewer agent: record its review from the session logs, never from what
    an agent writes. Never blocks and prints nothing; other agents and stops with no active task do nothing."""
    if not isinstance(hook, dict) or hook.get("agent_type") != REVIEWER:
        return
    slug = active_slug(root)
    if not slug or not _dir(root, slug).exists() or cancelled(root, slug):
        return
    tiers, _ = review_tiers(root, slug)
    main, rev = hook.get("transcript_path"), hook.get("agent_transcript_path")
    try:  # where Claude Code keeps a subagent's log (spike S3): <session>.jsonl and <session>/subagents/agent-<id>.jsonl
        home = Path(main).parent / Path(main).stem / "subagents" / f"agent-{hook.get('agent_id')}.jsonl"
        placed = Path(os.path.realpath(home)) == Path(os.path.realpath(rev))
    except (TypeError, ValueError):
        placed = False
    lines = _assistant_lines(rev) if placed else []
    model = next((m for m in map(_model, reversed(lines)) if m), None)
    text = _final_text(_assistant_lines(rev, last_turn=True)) if placed else None
    if text is None and isinstance(hook.get("last_assistant_message"), str):
        text = hook["last_assistant_message"]
    last = next((line for line in reversed((text or "").splitlines()) if line.strip()), "")
    found = VERDICT.fullmatch(last.strip().strip("`*_"))  # Markdown around the line is formatting, not a new verdict
    tier = tier_of(model, tiers)
    started = _dir(root, slug) / "started"
    since = started.read_text().strip() if started.exists() else None
    sessions = _state(_dir(root, slug) / "start.json", {}).get("sessions") or []
    known = {os.path.realpath(x) for x in sessions if isinstance(x, str)}
    if isinstance(main, str) and os.path.realpath(main) in known:
        btier, bwhy = builder_tier(main, since, tiers)
    else:  # logs the agent wrote itself, handed to a copy of this hook: not a session Claude Code ran
        btier, bwhy = None, ("the main session log is not one Herd saw (only the pre-init hook, the guard and the "
                             "Stop gate record sessions)")
    unread = (f"the reviewer's log is not where Claude Code keeps it ({rev})" if not placed
              else None if tier else f"{model} matches no tier" if model else f"no model in the reviewer's log {rev}")
    diff, read = reviewer_saw(root, str(hook.get("cwd") or root), lines)
    code, any_file = review_files(root, slug)
    new = [f for f in code or [] if f in untracked(root) and f not in read]  # in no git diff: must be read
    extra = {"source": "hook", "tier": tier, "builder_tier": btier, "top": tier == tiers[-1],
             "verdict": found[1] if found else "none", "unread": unread or bwhy,
             # what the reviewer saw (0.10.0): it counts only if it printed the diff or read every changed code file
             "diff_seen": diff, "code_total": None if code is None else len(code),
             "code_read": None if code is None else sum(f in read for f in code),
             "code_unread": [f for f in code or [] if f not in read][:MAX_REFS], "any_file": any_file,
             "new_unread": new[:MAX_REFS], "bad_refs": bad_refs(root, text),
             "saw": code is None or all(f in read for f in code) or (diff and not new)}
    # a round, for escalation and the report: after all checks first passed, by a reviewer whose tier would count
    extra["round"] = (_dir(root, slug) / "green.json").exists() and _tier_rule(root, slug, dict(extra, verdict="PASS"))[0]
    if len(_reviews_since_pass(load_notes(root, slug))) >= MAX_REVIEW_ROUNDS:  # recorded, but it cannot pass or reset
        extra.update(over_cap=True, round=False)
    add_review(root, slug, by=model or "an unknown model", text=_clip((text or "").strip() or "(no report)", REVIEW_CHARS),
               extra=extra)


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
    guarded = guard_line(notes)
    caveats = ([stop_line(stop)] if stop else []) + ([guarded] if guarded else []) + caveats
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
    times = sorted(_secs("2000-01-01T00:00:00Z", n["at"]) for n in notes if n.get("at") and n.get("kind") != "guard")
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


def _first_line(text, limit=200):
    """A review report's first line that is not its verdict, for the one-line report; the notes keep the rest."""
    line = next((x.strip() for x in str(text).splitlines() if x.strip() and not VERDICT.fullmatch(x)), "(no report)")
    return _clip(line, limit)


def _failed_rounds(notes):
    """Review rounds (see review_hook) without PASS since the last PASS, before the latest review."""
    rv = [n for n in notes if n["kind"] == "review" and n.get("round")]
    rv = rv[:-1] if rv and notes and rv[-1] is [n for n in notes if n["kind"] == "review"][-1] else rv
    return len(rv) - next((i + 1 for i in range(len(rv) - 1, -1, -1) if rv[i].get("verdict") == "PASS"), 0)


MAX_REVIEW_ROUNDS = 2  # reviewer runs since the last PASS that counts; the next one is refused (issue #45)
LIMIT_RESET = "review limit"  # a `herd note --decision` starting with these words, from the human, resets the count
OPEN_FINDING = re.compile(r"^\W*(Blocker|Major)\b", re.I)


def _reviews_since_pass(notes):
    """Reviews the hook recorded since the last PASS that counts as a round, or the last reset decision note."""
    start = 0
    for i, n in enumerate(notes):
        if (n.get("kind") == "review" and n.get("round") and n.get("verdict") == "PASS") or (
                n.get("kind") == "decision" and str(n.get("text", "")).lower().startswith(LIMIT_RESET)):
            start = i + 1
    return [n for n in notes[start:] if n.get("kind") == "review" and n.get("source") == "hook"]


def review_limit(notes):
    """The message once MAX_REVIEW_ROUNDS reviews ran since the last PASS (every run counts, round or not): stop and
    ask the human, with the open Blocker and Major lines of the last review. None below the limit."""
    rv = _reviews_since_pass(notes)
    if len(rv) < MAX_REVIEW_ROUNDS:
        return None
    open_ = [x.strip() for x in str(rv[-1].get("text", "")).splitlines() if OPEN_FINDING.match(x)]
    return (f"review limit reached: {len(rv)} reviews since the last PASS (limit {MAX_REVIEW_ROUNDS}). Run no more "
            "reviews: stop and ask the human one question. Open Blocker and Major findings from the last review: "
            + ("; ".join(open_) if open_ else "none listed")
            + ". The human lifts the limit with `herd note --decision \"Review limit: <what the human said>\"`.")


def _seen(n):
    """How much of the change a hook-recorded reviewer saw, from its log: `ran git diff or git show, read 2 of 3
    changed code files`; empty for a review recorded before 0.10.0."""
    if n.get("saw") is None:
        return ""
    total = n.get("code_total")
    return ("; " + ("ran git diff or git show" if n.get("diff_seen") else "no git diff or git show") + ", "
            + (f"read {n.get('code_read')} of {total} changed {'' if n.get('any_file') else 'code '}file{'s' if total != 1 else ''}"
               if isinstance(total, int) else "changed files unknown"))


def _review(notes):
    """The latest review note as one phrase: "<who>: <what>", "skipped: <why>", or None."""
    rv = [n for n in notes if n["kind"] == "review"]
    if not rv:
        return None
    n = rv[-1]
    if n.get("skipped"):
        return f"skipped: {n['text']}"
    if n.get("source") == "hook":
        same = "; same tier" if n.get("top") and n.get("tier") == n.get("builder_tier") else ""
        failed = _failed_rounds(notes)
        after = f", after {failed} round{'s' if failed != 1 else ''} without PASS" if failed else ""
        return (f"{n.get('by', 'reviewer')} ({n.get('tier') or 'unknown tier'}, builder on "
                f"{n.get('builder_tier') or 'an unknown tier'}{same}; {n.get('verdict', 'none')}{after}{_seen(n)}): "
                f"{_first_line(n['text'])}")
    return f"{n.get('by', 'reviewer')}: {n['text']}"


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
    if ev.get("human_corrected"):  # accepted without a note, shown for the human to confirm
        ids = ev["human_corrected"]
        out.append(f"{', '.join(ids)} corrected after the first verify to verbatim quotes of the request, keeping every "
                   f"earlier human quote: confirm the split; {'their checks' if len(ids) > 1 else 'its check'} may "
                   "not have been seen failing")
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
    if rv and rv[-1].get("bad_refs"):  # recorded, never refused: an old line number can be the diff's left side
        out.append("The review cites lines not in the repository now: " + "; ".join(rv[-1]["bad_refs"]))
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
    if ev.get("inputs"):
        lines.append(inputs_line(ev["inputs"]))
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
            text = " / ".join(x.strip() for x in n["text"].splitlines() if x.strip()) if n["kind"] == "review" else n["text"]
            lines.append(f"- {when}{n['kind']}: {text}")
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
    guarded = guard_line(notes)
    if guarded:
        gaps.append(f"- {guarded}: the agent tried these; check that nothing was done another way")
    review = _review(notes)
    if ev.get("route") != "quick" and (review is None or review.startswith("skipped:")):
        gaps.append(f"- The change is unreviewed: {review[len('skipped: '):] if review else 'no review recorded'}")
    if _failed_rounds(notes):
        gaps.append(f"- {_failed_rounds(notes)} review round{'s' if _failed_rounds(notes) != 1 else ''} found Blocker "
                    "or Major issues before the PASS: read them in the caveat log")
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
    if ev.get("inputs"):
        details.append(inputs_line(ev["inputs"]))
    if _attack_line(notes, ev.get("attacks")):
        details.append(_attack_line(notes, ev.get("attacks")))
    # the reviewer's view ends here; the rest is collapsed, nothing is dropped
    count = {k: sum(n["kind"] == k for n in notes) for k in NOTE_KINDS}
    lines += ["", "<details><summary>Run details and caveat log "
              f"({count['tried']} tried, {count['found']} found, {count['fixed']} fixed)</summary>", ""]
    lines += [f"- {d}" for d in details]
    # ponytail: output tails stay out of the PR (they can hold secrets); the reviewer re-runs the check instead
    if notes:
        shown = [n for n in notes if n["kind"] != "guard"][:MAX_PR_NOTES]  # the Guard line above sums them
        lines += ["", "Caveats logged during the run:", ""]
        lines += [f"- {fmt_duration(n['elapsed_s']) + ' ' if n.get('elapsed_s') is not None else ''}"
                  f"{n['kind']}: {_first_line(n['text'], 300) if n['kind'] == 'review' else n['text']}" for n in shown]
        rest = len([n for n in notes if n["kind"] != "guard"]) - len(shown)
        if rest > 0:
            lines.append(f"- and {rest} more: run `herd status {slug}`")
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
              (re.compile(r"^(test_budget|known_limits) is empty"), "add `{0}` to task.toml, then run `herd verify`"),
              (re.compile(r"^(?:no `inputs`|`inputs` must|inputs #\d+|\S+ has an `inputs` key)"),
               "add top-level `[[inputs]]` tables with `human` and `program` to task.toml, then run `herd verify`"),
              (re.compile(r"^coverage of human criterion (\S+) is empty"),
               "add `coverage` to human criterion {0}, then run `herd verify`"),
              (re.compile(r"^review missing.*?Spawn the herd-reviewer subagent with model ([\w.-]+)"),
               "spawn herd-reviewer with model {0}, then run `herd verify`"),
              (re.compile(r"^review missing"), "spawn herd-reviewer one tier above the builder, then run `herd verify`"),
              (re.compile(r"^adversarial pass incomplete"), "log each missing standard attack with `herd note --tried "
                                                            "--attack <name> --check \"<command>\"`, then run `herd verify`"))


def _escalations(root, slug):
    """Why the agent must ask the human now: criteria that failed ESCALATE_AFTER verifies in a row, and the
    review limit (MAX_REVIEW_ROUNDS reviews since the last PASS)."""
    try:
        out = [f"{cid} failed {ESCALATE_AFTER} times in a row" for cid in (load_evidence(root, slug) or {}).get("escalate") or []]
        limit = review_limit(load_notes(root, slug))
    except STATE_ERRORS:
        return []
    return out + ([f"review limit reached (limit {MAX_REVIEW_ROUNDS} reviews since the last PASS)"] if limit else [])


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
                review = {"needed": (review_need(root, slug)[0] or "one tier above the builder")
                          if review_needed(ev) else None,
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


# ---- guard hook -----------------------------------------------------------

# Herd's state files, written only by the herd CLI: the design's list (G3), plus `started` (the review window),
# `request.md` (the human's words) and `.herd/active` (removing it switches the gate off). task.toml is the agent's.
GUARD_STATE = ("evidence.json", "notes.jsonl", "start.json", "red.json", "frozen.json", "green.json", "fails.json",
               "stopped.json", "gate_blocks", "done_blocks", "cancelled", "started", "request.md", "base", "pr")
# the design's list, with .env and .env.* in every folder (a monorepo keeps apps/web/.env) and .git itself
GUARD_PATHS = ("**/.env", "**/.env.*", "**/*.pem", "**/*.key", "**/id_rsa*", ".git", ".git/**")  # herd.toml only adds
ENV_TEMPLATES = ("**/.env.example", "**/.env.sample", "**/.env.template", "**/.env.dist")  # committed, no secrets
# the design's list (A3), plus `git branch -d -f` (the same as -D), and other ways to discard work: `git checkout .`
# and `-f`, `git stash drop` and `clear`, `git switch -f` and `--discard-changes`
GUARD_COMMANDS = ("git push", "git reset --hard", "git clean -f", "git branch -D", "git branch -d -f",
                  "git checkout -- .", "git checkout .", "git checkout -f", "git restore .", "git commit --no-verify",
                  "git stash drop", "git stash clear", "git switch -f", "git switch --discard-changes",
                  "gh pr merge", "gh repo delete", "rm -rf /", "rm -rf ~", "rm -rf .")
UNSTAGE = ({"--staged", "-S"}, {"--worktree", "-W"})  # `git restore --staged .` only unstages: allowed
GUARD_WHY = {"git push": "Use `herd pr` to publish, or ask the human one question and stop.",
             "gh pr merge": "Herd never merges: a human merges after reading the evidence."}
GLOBAL_OPTS = {"git": ("-C", "-c", "--git-dir", "--work-tree", "--namespace"),  # options before the subcommand
               "gh": ("-R", "--repo", "--hostname")}                         # that take a value
FLAG_ALIAS = {"f": ("--force",), "r": ("--recursive",), "n": ("--no-verify",), "d": ("--delete",)}
SHORT = re.compile(r"-[A-Za-z]+")
# commands that run the command after them, with their options that take a value
WRAPPERS = {"env": ("-u", "-C", "-S", "--unset", "--chdir", "--split-string"),
            "sudo": ("-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "--user", "--group", "--chdir"),
            "command": (), "time": (), "nohup": (), "exec": ("-a",), "nice": ("-n",),
            "timeout": ("-s", "-k", "--signal", "--kill-after"),  # then a duration
            "xargs": ("-n", "-I", "-P", "-L", "-d", "-s", "-E", "-a")}
HOOK_COMMANDS = ("gate", "preinit", "guard", "review-hook")  # Claude Code runs these; the agent never needs to
SUBST = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")  # command substitution, which runs inside double quotes too
KEYWORDS = ("if", "then", "do", "else", "elif", "while", "until", "!", "{", "}")
SEPARATORS = {"&&", "||", ";", ";;", "|", "|&", "&", "(", ")"}
REDIRECT = re.compile(r"\d*(?:>|>>|>\||&>|&>>)")
INPUT = ("<", "<<", "<<<")  # the word after one of these is read, not written
VALUE_FLAGS = ("-m", "-F", "-C", "-c", "--message", "--file", "--author", "--date")  # their value is not a flag
DRY_RUN = {"--help", "-h", "--dry-run"}
HEREDOC = re.compile(r"(?<!<)<<-?\s*\\?(['\"]?)([A-Za-z_][\w.-]*)\1")


def guard_root(hook):
    """The folder of the active task the hook belongs to, as a Path, or None (see _active_root)."""
    found = _active_root(hook)
    return Path(found) if found else None


def guard_config(root):
    """(protected path globs, denied commands): the built-in ones plus herd.toml's `[guard]` additions."""
    try:
        cfg = tomllib.loads((Path(root) / "herd.toml").read_text()).get("guard")
    except (OSError, tomllib.TOMLDecodeError):
        cfg = None
    cfg = cfg if isinstance(cfg, dict) else {}

    def extra(key):
        v = cfg.get(key)
        return [x.strip() for x in v if isinstance(x, str) and x.strip()] if isinstance(v, list) else []
    return list(GUARD_PATHS) + extra("protected_paths"), list(GUARD_COMMANDS) + extra("deny_commands")


def _shell_text(command):
    """The command without what the shell never runs: `#` comments (a `#` that starts a word outside quotes and
    substitutions, to the end of its line) and heredoc bodies (text such as a commit message). One pass that keeps
    a stack of quotes, `$(...)` and parentheses, so quotes nested in "$(...)" and `<<` in arithmetic are not
    misread. It fails closed: a heredoc whose closing line never comes keeps its body, so the body is checked."""
    out, stack, pending, i, n, escaped = [], [], [], 0, len(command), -1
    while i < n:
        c, top = command[i], stack[-1] if stack else None
        if c == "\n" and top in (None, "$(") and pending:  # a line that started heredocs ends: skip their bodies
            out.append(c)
            i += 1
            for word in pending:
                end = re.search(r"^[ \t]*" + re.escape(word) + r"[ \t]*$", command[i:], re.M)
                if not end:  # never closed: keep the rest as commands
                    break
                i += end.end() + 1
            pending = []
            continue
        if c == "\\" and top != "'" and i + 1 < n:  # an escaped character is part of a word
            out.append(command[i:i + 2])
            i += 2
            escaped = i
            continue
        two = command[i:i + 2]
        if top in ("'", "$'"):
            if c == "'":
                stack.pop()
        elif top == '"':
            if c == '"':
                stack.pop()
            elif two == "$(":
                stack.append("$(")
                out.append(two)
                i += 2
                continue
        elif two in ("$(", "$'"):
            stack.append(two)
            out.append(two)
            i += 2
            continue
        elif c in "('\"":
            stack.append(c)
        elif c == ")" and top in ("(", "$("):
            stack.pop()
        elif c == "#" and top is None and (i == 0 or command[i - 1] in " \t\n;&|()") and escaped != i:
            end = command.find("\n", i)
            i = n if end < 0 else end
            continue
        elif c == "<" and top in (None, "$(") and (m := HEREDOC.match(command, i)):
            pending.append(m.group(2))
            out.append(m.group(0))
            i = m.end()
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _segments(command):
    """The simple commands of a shell line, as word lists: split at && || ; | & ( ) ` and newlines, outside quotes.
    Heredoc bodies are dropped; leading keywords (if, then, do, !, {), `VAR=x` and wrappers (env, sudo, command,
    time, nohup, exec, with their options) are seen through."""
    plain = _shell_text(command)
    text = plain.replace("\\\n", " ").replace("\n", " ; ").replace("`", " ; ")
    try:
        lex = shlex.shlex(text, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ""  # _shell_text took the comments out: a # left is inside a word or quotes
        words = list(lex)
    except ValueError:  # an unbalanced quote: split the raw text, best effort
        words = [w.strip("\"'") for w in re.sub(r"(&&|\|\||[;|&()])", r" \1 ", text).split()]
    out, cur = [], []
    for w in words + [";"]:
        if w not in SEPARATORS:
            cur.append(w)
            continue
        while cur:
            if cur[0] in KEYWORDS or re.fullmatch(r"[A-Za-z_]\w*=.*", cur[0]):
                cur = cur[1:]
            elif cur[0] in WRAPPERS:
                wrapper, takes = cur[0], WRAPPERS[cur[0]]
                cur = cur[1:]
                while cur and cur[0].startswith("-"):
                    cur = cur[2:] if cur[0] in takes else cur[1:]
                cur = cur[1:] if wrapper == "timeout" else cur
            else:
                break
        if cur:
            out.append(cur)
        cur = []
    return out + [seg for m in SUBST.finditer(plain) for seg in _segments(m.group(1) or m.group(2) or "")]


def _target_hit(token, arg, cwd):
    """An rm or git argument names / (token "/"), the home folder ("~"), or the folder the command runs in or one
    above it ("."), in any spelling: `/.`, `$HOME`, `~/`, `*`, `.*`, `..`, an absolute path."""
    if not arg:  # rm -rf '' removes nothing
        return False
    arg = re.sub(r"^\$\{?HOME\}?", "~", arg)
    arg = re.sub(r"(^|/)\.?\*/?$", r"\1", arg) or "."
    path = os.path.normpath(os.path.join(cwd, os.path.expanduser(arg)))
    if token == "/":
        return path == "/"
    if token == "~":
        return path == os.path.normpath(os.path.expanduser("~"))
    here = os.path.normpath(cwd)
    return path != "/" and (here == path or here.startswith(path.rstrip("/") + "/"))


def _has(token, args, cwd):
    """The rule token is among the arguments: exactly; as a short flag in any cluster (-xfd has f) or its long
    spelling (--force), including a unique prefix git accepts (--forc); for / ~ and ., in any spelling."""
    if token in (args[:args.index("--")] if "--" in args and token.startswith("-") and token != "--" else args):
        return True
    if token in ("/", "~", "."):
        return any(_target_hit(token, a, cwd) for a in args if not a.startswith("-"))
    if not token.startswith("-"):
        return False
    flags = args[:args.index("--")] if "--" in args else args  # after `--` come paths, not flags
    clusters = [a for a in flags if SHORT.fullmatch(a)]
    longs = [a.split("=", 1)[0] for a in flags if a.startswith("--") and len(a) > 4]

    def long_hit(name):
        return any(a == name or name.startswith(a) for a in longs)
    if SHORT.fullmatch(token) and len(token) <= 3:
        return all(any(c in a or (c == "r" and "R" in a) for a in clusters)
                   or any(long_hit(n) for n in FLAG_ALIAS.get(c, ())) for c in token[1:])
    letter = next((c for c, names in FLAG_ALIAS.items() if token in names), None)
    return long_hit(token) or bool(letter and any(letter in a for a in clusters))


def _rule_hit(rule, words, cwd):
    """A denied command (`git clean -f`) matches a simple command: same program, the same subcommands first
    (after git's or gh's global options), then each other rule token anywhere after them."""
    r = rule.split()
    if not r or not words:
        return False
    same = os.path.normpath(words[0]) == os.path.normpath(r[0]) if "/" in r[0] else Path(words[0]).name == r[0]
    if not same:
        return False
    args = [a for i, a in enumerate(words[1:]) if not (i and words[i] in VALUE_FLAGS + GLOBAL_OPTS.get(r[0], ()))]
    n = next((i for i, t in enumerate(r[1:]) if not re.fullmatch(r"[a-z][\w-]*", t)), len(r) - 1)
    places = [i for i, a in enumerate(args) if not a.startswith("-")][:n]  # the subcommands, between options
    if [args[i] for i in places] != r[1:1 + n]:
        return False
    rest = [a for i, a in enumerate(args) if i not in places]
    return all(_has(t, rest, cwd) for t in r[1 + n:])


def _written(words):
    """Paths a simple command writes, moves, deletes or makes read-only: redirection targets, the arguments of tee,
    mv, rm, touch, truncate, chmod, chown, chgrp, sed -i and git rm, the last argument of cp, ln, install and rsync,
    and dd of=. Words read from (< << <<<) are not written."""
    targets = {i + 1 for i, w in enumerate(words) if REDIRECT.fullmatch(w)}
    read = {i + 1 for i, w in enumerate(words) if w in INPUT}
    out = [words[i] for i in sorted(targets) if i < len(words)]
    args = [w for i, w in enumerate(words) if i and i not in targets | read and not w.startswith("-")
            and not REDIRECT.fullmatch(w) and w not in INPUT]
    name = Path(words[0]).name
    out += [w[3:] for w in words[1:] if w.startswith("of=")]  # dd
    if name in ("chmod", "chown", "chgrp"):  # a read-only state file would stop the CLI writing it
        out += args[1:]
    elif name in ("ln", "install", "rsync") and len(args) > 1:
        out.append(args[-1])
    elif name == "git" and args[:1] == ["rm"] and "--cached" not in words:  # --cached only untracks
        out += args[1:]
    in_place = any(w.startswith(("-i", "--in-place")) or SHORT.fullmatch(w) and "i" in w for w in words[1:])
    if name in ("tee", "mv", "rm", "touch", "truncate") or (name == "sed" and in_place):
        out += args
    elif name == "cp" and args:
        out.append(args[-1])
    return out


def _protected(root, cwd, path, globs):
    """(rule, reason) when path is one of Herd's state files or folders, or matches a protected glob. Symlinks are
    followed and case is ignored, since a case-insensitive disk writes `.ENV` to `.env`."""
    full = Path(os.path.realpath(os.path.join(cwd, os.path.expanduser(path))))
    parts = [p.lower() for p in full.parts]
    if ".herd" in parts:
        rest = full.parts[len(parts) - parts[::-1].index(".herd"):]
        low = [p.lower() for p in rest]
        state = (len(low) < 2 and (not low or fnmatch.fnmatchcase("active", low[0]) or low[0] == "tasks")
                 or low[0] == "tasks" and (len(low) == 2 or len(low) == 3 and any(
                     fnmatch.fnmatchcase(n.lower(), low[2]) for n in GUARD_STATE)))
        if state:
            name = "/".join((".herd",) + tuple(rest))
            return (rest[-1] if len(rest) == 3 else name,
                    f"Herd guard: `{name}` is Herd's own state, written only by the herd CLI: run `herd verify` or "
                    "`herd note`.")
    try:
        rel = full.relative_to(os.path.realpath(root)).as_posix()
    except ValueError:  # outside the project
        return None
    def match(g):
        try:
            return herd_triage.glob_match(rel, g) or herd_triage.glob_match(rel.lower(), g.lower())
        except (ValueError, re.error):  # a broken glob in herd.toml protects nothing and stops nothing
            return False
    template = any(match(t) for t in ENV_TEMPLATES)
    for g in globs:
        if match(g) and not (template and g in GUARD_PATHS):
            return g.removeprefix("**/"), (f"Herd guard: `{rel}` is protected (`{g}`, a Herd default or `[guard] protected_paths`). "
                       "Ask the human one question and stop.")
    return None


def guard(root, hook):
    """PreToolUse hook on Bash and the edit tools. None allows; a dict is the deny output. Only while a task is
    active; each denial is a `guard` note. It reads command text, so bash -c, scripts and aliases pass (a Non-Goal)."""
    if not isinstance(hook, dict):
        return None
    slug = active_slug(root)
    if not slug or not _dir(root, slug).exists() or cancelled(root, slug):
        return None
    if "agent_id" not in hook:  # a subagent's own call: the main session is what the review hook asks about
        # issue #40: `herd init` through $H or an alias is unreadable to the pre-init hook
        _see_session(root, slug, hook.get("transcript_path"))
    tool, inp = hook.get("tool_name"), hook.get("tool_input")
    inp, cwd = inp if isinstance(inp, dict) else {}, str(hook.get("cwd") or root)
    globs, commands = guard_config(root)
    logs = hook.get("transcript_path")
    logs = os.path.realpath(os.path.dirname(logs)) if isinstance(logs, str) and logs else None
    hit = None

    plugin = os.environ.get("CLAUDE_PLUGIN_ROOT")
    plugin = os.path.realpath(plugin) if plugin else None
    project = os.path.realpath(root)
    if plugin and (project == plugin or project.startswith(plugin + os.sep) or plugin.startswith(project + os.sep)):
        plugin = None  # developing Herd with Herd: the plugin is the project

    def _session_log(path):  # the session logs (*.jsonl, subagents/), which the review hook reads; memory/ stays free
        full = os.path.realpath(os.path.join(here if tool == "Bash" else cwd, os.path.expanduser(path)))
        if plugin and (full == plugin or full.startswith(plugin + os.sep)):
            return "Herd plugin", ("Herd guard: the installed Herd plugin (its hooks and the herd-reviewer agent) is "
                                   "not edited during a task. Ask the human one question and stop.")
        return logs and full.startswith(logs + os.sep) and (full.endswith(".jsonl") or f"{os.sep}subagents{os.sep}" in full) and (
            "session log", "Herd guard: Claude Code's session logs are read by the review hook and written only by "
            "Claude Code. Ask the human one question and stop.")
    here = cwd
    if tool in EDIT_TOOLS:
        path = inp.get("file_path") or inp.get("notebook_path")
        hit = (_session_log(path) or _protected(root, cwd, path, globs)) if isinstance(path, str) and path else None
    elif tool == "Bash" and isinstance(inp.get("command"), str):
        for words in _segments(inp["command"]):  # `here` follows `cd` and `pushd` along the chain
            if Path(words[0]).name in ("cd", "pushd") and len(words) > 1:
                here = os.path.normpath(os.path.join(here, os.path.expanduser(words[1])))
                continue
            hooked = next((words[i + 1] for i, w in enumerate(words[:-1])  # herd.py gate, -m herd, -mscripts.herd
                           if words[i + 1] in HOOK_COMMANDS and "herd" in w.lower()), None)
            if hooked:
                hit = f"herd {hooked}", (f"Herd guard: `herd {hooked}` runs only as a Claude Code hook, with Claude "
                                         "Code's own input. For a review, spawn the herd-reviewer subagent; the hook "
                                         "records it.")
                break
            unstage = UNSTAGE[0] & set(words) and not UNSTAGE[1] & set(words)
            dry = DRY_RUN & set(words[1:]) or ("clean" in words and any(SHORT.fullmatch(w) and "n" in w for w in words))
            rule = None if dry else next((r for r in commands if _rule_hit(r, words, here)
                                          and not (r == "git restore ." and unstage)), None)
            if rule:
                hit = rule, (f"Herd guard: `{rule}` is not allowed during a task. "
                             + GUARD_WHY.get(rule, "It is irreversible: ask the human one question and stop."))
                break
            hit = next((h for p in _written(words) if (h := _session_log(p) or _protected(root, here, p, globs))), None)
            if hit:
                break
    if not hit:
        return None
    try:
        add_note(root, slug, "guard", f"{tool}: {hit[0]}")
    except Exception as e:  # noqa: BLE001 - a log that cannot be written never turns a denial into an allow
        print(f"herd guard: denied, but the guard note could not be written: {e!r}"[:300], file=sys.stderr)
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": hit[1]}}


def guard_line(notes):
    """`Guard: N denied (git push x2, .env x1)`, or None when nothing was denied."""
    rules = [str(n.get("text") or "?").split(": ", 1)[-1] for n in notes if n.get("kind") == "guard"]
    return (f"Guard: {len(rules)} denied (" + ", ".join(f"{r} x{rules.count(r)}" for r in dict.fromkeys(rules)) + ")"
            if rules else None)


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
    out += [f"human criterion {cid} is not a verbatim quote of the request: copy the human's words into its `text` "
            "and put your own scenario in an agent-proposed criterion; if the human reworded it or wrote it elsewhere "
            f"(a file they named), record their words with `herd note --human-change \"{cid}: <their words>\"`"
            for cid in ev.get("human_not_verbatim") or []]  # None: no request recorded, so nothing to quote
    if review_needed(ev):  # the standard route at medium and high risk: only absence is refused, the words are yours
        out += [f"{key} is empty: add to task.toml `{key} = \"{what}\"`" for key, what in REQUIRED.items()
                if not str(ev.get(key) or "").strip()]
        out += [f"coverage of human criterion {r['id']} is empty: add `coverage = \"<what its check proves and what "
                "it does not>\"` to it" for r in ev["results"] if r["source"] == "human" and not str(r.get("coverage") or "").strip()]
        out += ev.get("inputs_left") or []  # structure only: missing, misplaced inside a criterion, or incomplete
    risk = (ev.get("risk") or {}).get("effective")
    ok, why = review_state(root, slug, ev, notes)
    if review_needed(ev) and not ok and review_limit(notes):
        out.append(review_limit(notes))  # at the limit: stop and ask, never "spawn another reviewer"
    elif review_needed(ev) and not ok:
        need, _ = review_need(root, slug)
        model = (re.search(r"Spawn herd-reviewer with model ([\w.-]+)", why or "") or [None, need])[1]
        out.append(f"review missing ({why}): risk is {risk}. Spawn the herd-reviewer subagent "
                   + (f"with model {model}" if model else "one tier above yours")
                   + ", giving it only what `herd review-brief` prints; the review hook records it")
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


def _see_session(root, slug, log):
    """Record a session log the Stop gate or the guard saw (from Claude Code's own hook input; `herd gate` and
    `herd guard` are denied to the agent): the review hook counts only reviews from sessions recorded here or by
    the pre-init hook, and `herd status` reads the latest."""
    start = _state(_dir(root, slug) / "start.json", None)
    if not (isinstance(log, str) and log and start is not None):
        return
    seen = [x for x in start.get("sessions") or [] if isinstance(x, str)]
    if start.get("transcript") != log or log not in seen:
        (_dir(root, slug) / "start.json").write_text(json.dumps(
            dict(start, transcript=log, sessions=[x for x in seen if x != log] + [log])) + "\n")


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
    _see_session(root, slug, hook.get("transcript_path") if isinstance(hook, dict) else None)
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
        if any(c.startswith("review limit") for c in causes):  # the agent must ask, not loop: release the stop
            return None
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
    "review": 'herd review --by "<reviewer>" "<what they found>"   (a note; at medium and high risk only the review hook counts)',
    "review-hook": "herd review-hook   (the SubagentStop hook for herd-reviewer: records its review from the session logs)",
    "review-brief": "herd review-brief [slug]   (the brief to pass to herd-reviewer as it is: criteria, request, "
                    "inputs, the files it must read, the diff command)",
    "detect": "herd detect",
    "lint": "herd lint [--suggest]   (without --suggest: the PostToolUse hook, reads hook JSON on stdin)",
    "verify": "herd verify [slug] [--verbose]",
    "status": "herd status [slug] [--json]   (--json: the stop record, or null)",
    "done": "herd done [slug] [--verbose]",
    "cancel": 'herd cancel [slug] [--reason "text"]',
    "pr": "herd pr [slug] [--yes]   (push the herd/* branch, open or update its PR with the evidence)",
    "gate": "herd gate   (the Stop hook, reads hook JSON on stdin)",
    "preinit": "herd preinit   (PreToolUse hook on Bash: before `herd init`, records files the session already edited)",
    "guard": "herd guard   (PreToolUse hook: denies edits to secrets and Herd's state, and irreversible commands)",
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
    try:
        root = find_root(Path.cwd())
    except FileNotFoundError:  # the folder was deleted under the process: a hook must still exit 0
        return 0 if argv[:1] in (["gate"], ["lint"], ["preinit"], ["guard"], ["review-hook"]) else 1
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
            for w in (check_warnings(task, req_path.read_text() if req_path.exists() else None, load_notes(root, slug))
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
            limit = review_limit(load_notes(root, ev["task"]))
            if limit:
                print(f"  {limit}")
            hint = pass_hint(root, ev["task"], ev, load_notes(root, ev["task"]))
            if hint:
                print(f"  {hint}")
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
            if ev and review_needed(ev):
                hint = pass_hint(root, slug, ev, load_notes(root, slug))
                need, builder = review_need(root, slug)
                print(hint if hint else f"Review: needs {need} or higher (builder on {builder})" if need
                      else f"Review: needs a reviewer one tier above the builder ({builder})")
            probs = problems(root, slug)
            print("not done: " + "; ".join(probs) if probs else "done: evidence is fresh and passing")
        elif cmd == "review":
            if "--skipped" in args:
                raise ValueError("`herd review --skipped` was removed in 0.7.0: a review is required at medium and "
                                 "high risk. Spawn the herd-reviewer subagent (`herd status` names its model); if no "
                                 "reviewer can run, say so and stop: Herd records why")
            by, args = _opt(args, "--by")
            if by is None or len(args) != 1:
                raise UsageError
            add_review(root, _slug_arg(root, []), by=by, text=args[0])
            print(f"review recorded by {by}: a note; at medium and high risk only a review the hook records counts")
        elif cmd == "review-brief":
            slug = _slug_arg(root, args)
            limit = review_limit(load_notes(root, slug))
            if limit:
                print(limit)
                return 1
            print(review_brief(root, slug), end="")
        elif cmd == "review-hook":  # SubagentStop hook: never blocks the session
            try:
                raw = sys.stdin.read() if not sys.stdin.isatty() else ""
                hook = json.loads(raw) if raw.strip() else {}
                if isinstance(hook, dict):  # the task, found as the guard finds it
                    review_hook(guard_root(hook) or find_root(Path(hook.get("cwd") or root)), hook)
            except Exception as e:  # noqa: BLE001 - a hook must never break the session
                print(f"herd review-hook: nothing recorded after an error: {e!r}"[:300].replace("\n", " "), file=sys.stderr)
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
        elif cmd == "guard":  # PreToolUse hook: an error allows the action, with one stderr line
            try:
                raw = globals().get("GUARD_RAW")
                raw = raw if raw is not None else (sys.stdin.read() if not sys.stdin.isatty() else "")
                hook = json.loads(raw) if raw.strip() else {}
                found = guard_root(hook)
                out = guard(found, hook) if found else None
                if out:
                    print(json.dumps(out))
            except Exception as e:  # noqa: BLE001 - a hook must never break the session
                print(f"herd guard: allowed after an error: {e!r}"[:300].replace("\n", " "), file=sys.stderr)
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
