#!/usr/bin/env python3
"""Design eval: do a fresh challenger's questions, answered before any code, fix design mistakes?

  python3 run_eval.py [--case TASK] [--runs 12] [--root DIR] [--dry-run]

Per case and run, two Herd sessions start in run_leg.py's isolation. One is stopped at its first `herd verify`
and forked twice (arms control and after-red); one is stopped before its first attack note is written (arm before-attacks).
Each arm resumes from that stop, answers, runs `herd verify` and is stopped again. Nothing is built.
Then: judge.py ROOT/results, and report.py ROOT/results.
"""
import argparse
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "supermarket-route" / "verifier")]
import judge  # noqa: E402
import leak_audit  # noqa: E402
import run_leg  # noqa: E402
from report import ARMS  # noqa: E402

REPO = run_leg.EXAMPLES.parent
MAX_QUESTIONS = 5
CHALLENGER = (
    "You are a challenger who has not seen any code. Read this request. First state in 2 or 3 lines the business "
    "context: who uses this program, in what real situation, and what a wrong answer costs them. Then write at most "
    f"{MAX_QUESTIONS} sharp questions the builder must answer before writing code. Each question must be framed in "
    "that business context, for example: 'For a picker in this store, what should happen when ...?' Cover "
    "ambiguities, input forms, edge cases, and what the program must accept and refuse. Numbered.")
WITH_QUESTIONS = (
    "A challenger who has not seen your work wrote the questions below. They are there to help you figure out the "
    "details: do not assume you already know everything. Use each question to challenge your own understanding of "
    "the request and its business context. Answer each one in ANSWERS.md, saying what you first assumed and what "
    "you decided after thinking it through.")
NO_QUESTIONS = (
    "Challenge your own understanding of the request and its business context: do not assume you already know "
    "everything. Write ANSWERS.md, saying what you first assumed and what you decided after thinking it through.")
THEN = {
    "red": " Then update your Herd task to match your decisions (the human's criteria stay word for word) and run "
           "herd verify. Do not build yet.",
    "attacks": " Then update your Herd task to match your decisions (the human's criteria stay word for word), write "
               "your attacks and run herd verify. Do not build yet.",
}


def builder_message(arm, questions=None):
    then = THEN["attacks" if arm == "before-attacks" else "red"]
    if arm == "control":
        return NO_QUESTIONS + then
    return f"{WITH_QUESTIONS}{then}\n\n{questions}"


def challenger_input(prompt):
    return f"{CHALLENGER}\n\nREQUEST:\n\n{prompt}"


def first_questions(reply):
    """The reply cut before a sixth numbered question, so no run gets more than MAX_QUESTIONS."""
    extra = re.search(rf"(?m)^[ \t#*]*{MAX_QUESTIONS + 1}[.)]", reply)
    return (reply[:extra.start()] if extra else reply).strip()


def session_command(ns, prompt, run_dir):
    return run_leg.build_command(ns, "/herd:run " + prompt, run_dir)


def resume_command(ns, message, run_dir, session_id):
    """Fork, so every arm that starts from one stop continues the same untouched conversation."""
    return run_leg.build_command(ns, message, run_dir) + ["--resume", session_id, "--fork-session"]


def case_prompt(case):
    path = Path(case["prompt"])
    path = path if path.is_absolute() else REPO / path
    try:
        text = path.read_text(encoding="utf-8").rstrip("\n")
    except (OSError, UnicodeError) as e:
        raise judge.Refused(f"cannot read the prompt file {path}: {getattr(e, 'strerror', None) or e}") from None
    if not text.strip():
        raise judge.Refused(f"the prompt file {path} is empty")
    return text


# ---- what a session has done so far

def _inside(work, path):
    """A regular file really inside the work folder: a run wrote it, so a link out of the sandbox is ignored."""
    return path.is_file() and os.path.realpath(path).startswith(os.path.realpath(work) + os.sep)


def task_dir(work):
    found = [p.parent for p in Path(work).glob(".herd/tasks/*/task.toml") if _inside(work, p)]
    return max(found, key=lambda d: (d / "task.toml").stat().st_mtime) if found else None


def has_red(work):
    return any(_inside(work, p) for p in Path(work).glob(".herd/tasks/*/red.json"))


def has_attack_note(work):
    for path in Path(work).glob(".herd/tasks/*/notes.jsonl"):
        for line in path.read_text(errors="replace").splitlines() if _inside(work, path) else []:
            try:
                note = json.loads(line)
            except ValueError:
                continue
            if isinstance(note, dict) and note.get("attack"):
                return True
    return False


HELD = "attack-held"  # the marker the hook leaves, beside (not inside) the work folder


def hold_hook(run_dir):
    """A PreToolUse hook that holds the first attack-note command before it runs, so not one note is written.
    A builder often logs all six in one command, which no look at the notes file can stop part way."""
    marker = shlex.quote(str(Path(run_dir) / HELD))
    command = f'case "$(cat)" in *note*--attack*) : > {marker}; sleep 3600 ;; esac'
    return {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": command, "timeout": 3600}]}]}


def has_answered(work, since):
    """True once a verify finished after both the resume and the last write of ANSWERS.md."""
    answers = Path(work) / "ANSWERS.md"
    if not _inside(work, answers):
        return False
    after = max(since, answers.stat().st_mtime)
    return any(_inside(work, p) and p.stat().st_mtime >= after
               for p in Path(work).glob(".herd/tasks/*/evidence.json"))


def snapshot(work, dest):
    """task.toml, notes.jsonl, ANSWERS.md and the project files, as they are now."""
    dest = Path(dest)
    dest.mkdir(parents=True)
    task = task_dir(work)
    sources = [Path(work) / "ANSWERS.md"] + ([task / "task.toml", task / "notes.jsonl"] if task else [])
    for src in sources:
        if _inside(work, src):
            shutil.copyfile(src, dest / src.name)
    shutil.copytree(work, dest / "files", symlinks=True, ignore=shutil.ignore_patterns(".git", ".herd"))


# ---- processes

def _descendants(pid):
    table = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True).stdout.split()
    children, out, todo = {}, [], [pid]
    for child, parent in zip(table[::2], table[1::2]):
        children.setdefault(int(parent), []).append(int(child))
    while todo:
        for child in children.get(todo.pop(), []):
            out.append(child)
            todo.append(child)
    return out


def _signal(send, pid, sig):
    try:
        send(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def stop_process(proc):
    """Stop a session this eval started, with its process group and its descendants."""
    tree = _descendants(proc.pid)
    _signal(os.killpg, proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass
    _signal(os.killpg, proc.pid, signal.SIGKILL)
    for pid in tree:
        _signal(os.kill, pid, signal.SIGKILL)
    proc.wait()


def wait_for(proc, done, timeout, poll=0.2):
    """"reached" when done() is true, else "exited" or "timeout"."""
    end = time.monotonic() + timeout
    while True:
        exited = proc.poll() is not None
        try:
            if done():
                return "reached"
        except OSError:  # the session replaced a file while it was being looked at: look again
            pass
        if exited:
            return "exited"
        if time.monotonic() >= end:
            return "timeout"
        time.sleep(poll)


def session_id(log):
    for line in Path(log).read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("session_id"):
            return event["session_id"]
    return None


# ---- the eval

class Eval:
    def __init__(self, ns, env, root, start=run_leg.start, stop=stop_process, call=None):
        self.ns, self.env, self.root, self.start, self.stop = ns, env, Path(root), start, stop
        self.results, self.logs = self.root / "results", self.root / "logs"
        self.call = call or (lambda prompt: judge.ask(ns.challenger_model, prompt))

    def create_session(self, index, total):
        run_dir = run_leg.create_run(self.root, total, index, self.ns, self.env)
        denied = run_leg.outside_home_repo(self.env) + [str(self.results), str(self.logs)]  # earlier runs' output
        settings = run_leg.build_settings(self.root, total, index, denied)
        (run_dir / "settings.json").write_text(json.dumps(settings, indent=2) + "\n")
        return run_dir

    def drive(self, cmd, run_dir, log, done):
        """Run one command until done() or its end; always leave no process behind."""
        proc = self.start(cmd, run_dir, log, log.with_suffix(".err"), self.env)
        try:
            return wait_for(proc, done, self.ns.timeout, self.ns.poll)
        finally:
            self.stop(proc)

    def first_leg(self, prompt, run_dir, log, early):
        """Run the session to its stop point. Returns (session id, None) or (None, why it cannot be used)."""
        work, held = run_dir / "work", run_dir / HELD
        settings = run_dir / "settings.json"
        plain = settings.read_text()
        if early:
            settings.write_text(json.dumps({**json.loads(plain), "hooks": hold_hook(run_dir)}, indent=2) + "\n")
            done = lambda: held.exists() or has_attack_note(work) or has_red(work)  # noqa: E731
        else:
            done = lambda: has_red(work)  # noqa: E731
        how = self.drive(session_command(self.ns, prompt, run_dir), run_dir, log, done)
        settings.write_text(plain)  # the resume is not held
        sid = session_id(log)
        if how != "reached" or not sid:
            return None, "no-start"
        if early and (has_red(work) or has_attack_note(work)):  # an attack got written before the stop
            return None, "missed-stop"
        return sid, None

    def arm(self, arm, prompt, run_dir, sid, logs, out):
        """Resume the stopped session for one arm. Returns the run's status and its audit findings."""
        questions = None
        if arm != "control":
            try:
                questions = first_questions(self.call(challenger_input(prompt)))
            except judge.Refused as e:
                print(f"challenger: {e}", file=sys.stderr)
                return "challenger-failed", []
            (out / "questions.md").write_text(questions + "\n")
        work, log = run_dir / "work", logs[0].with_name(f"{logs[0].stem}.{arm}.jsonl")
        since = time.time()
        cmd = resume_command(self.ns, builder_message(arm, questions), run_dir, sid)
        how = self.drive(cmd, run_dir, log, lambda: has_answered(work, since))
        snapshot(work, out / "after")
        findings = [f for path in (*logs, log)
                    for f in leak_audit.audit(path, work, settings=run_dir / "settings.json")]
        found = [f"{f.tool}: {f.detail}" for f in findings if not f.blocked]
        if found:
            return "leak", found
        return ("ok" if how == "reached" else "no-verify"), []

    def session(self, task, n, arms, prompt, run_dir):
        """One first leg, then each of its arms from an identical copy of the work folder."""
        early = arms == ("before-attacks",)
        log = self.logs / f"{run_dir.name}.jsonl"
        outs = {arm: self.results / task / arm / f"run-{n}" for arm in arms}
        for arm, out in outs.items():
            out.mkdir(parents=True)
            _record(out, task, arm, n, "incomplete", [])
        sid, why = self.first_leg(prompt, run_dir, log, early)
        if why:
            for arm, out in outs.items():
                _record(out, task, arm, n, why, [])
                print(f"{task} {arm} run {n}: {why}", flush=True)
            return
        work, saved = run_dir / "work", self.logs / f"{run_dir.name}.start-work"
        shutil.copytree(work, saved, symlinks=True)
        for arm, out in outs.items():
            shutil.rmtree(work)
            shutil.copytree(saved, work, symlinks=True)
            snapshot(work, out / "before")
            status, found = self.arm(arm, prompt, run_dir, sid, (log,), out)
            _record(out, task, arm, n, status, found)
            print(f"{task} {arm} run {n}: {status}", flush=True)

    def run(self, prompts):
        plan = sessions(prompts, self.ns.runs)
        self.root.parent.mkdir(parents=True, exist_ok=True)
        self.root.mkdir()
        self.results.mkdir()
        self.logs.mkdir()
        settings = {k: getattr(self.ns, k) for k in ("model", "challenger_model", "herd_tag", "budget", "runs")}
        (self.results / "manifest.json").write_text(json.dumps(settings, indent=2) + "\n")
        for index, (task, n, arms) in enumerate(plan, 1):
            run_dir = self.create_session(index, len(plan))
            self.session(task, n, arms, prompts[task], run_dir)


def _record(out, task, arm, n, status, findings):
    data = {"case": task, "arm": arm, "run": n, "status": status, "findings": findings}
    (out / "run.json").write_text(json.dumps(data, indent=2) + "\n")


def sessions(prompts, runs):
    """(case, run number, arms) for every first leg."""
    return [(task, n, arms) for task in prompts for n in range(1, runs + 1)
            for arms in (ARMS[:2], ARMS[2:])]  # control and after-red share a start


def dry_run(ns, prompts, root):
    plan = sessions(prompts, ns.runs)
    for index, (task, n, arms) in enumerate(plan, 1):
        run_dir = root / f"run-{index}"
        where = f"cd {shlex.quote(str(run_dir / 'work'))} &&"
        stop = "first attack-note command (held before it runs)" if arms == ("before-attacks",) else "first herd verify"
        print(f"\n# {task} run {n}: session for {', '.join(arms)}, stopped at the {stop}")
        print(f"{where} {shlex.join(session_command(ns, prompts[task], run_dir))}")
        for arm in arms:
            if arm != "control":
                print(f"# {arm} challenger, prompt on stdin, from an empty folder:")
                print(shlex.join(judge.model_command(ns.challenger_model)))
            print(f"# {arm} resume, stopped at the verify after ANSWERS.md:")
            message = builder_message(arm, "<the challenger's questions>").replace("\n\n", " ")
            print(f"{where} {shlex.join(resume_command(ns, message, run_dir, '<session id>'))}")
    print("\ndry run: nothing started")


def parse(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case", action="append", help="task name; repeat for more (default: every case)")
    ap.add_argument("--cases", default=str(judge.CASES), help="folder of case files")
    ap.add_argument("--runs", type=int, default=12, help="runs per arm per case")
    ap.add_argument("--model", default="claude-haiku-5-5", help="the builder")
    ap.add_argument("--challenger-model", help="default: the builder's model")
    ap.add_argument("--herd-tag", default="v0.13.1")
    ap.add_argument("--budget", type=float, default=3, help="USD cap of each session and each resume")
    ap.add_argument("--timeout", type=float, default=900, help="seconds for each session and each resume")
    ap.add_argument("--poll", type=float, default=0.2, help="seconds between looks at the work folder")
    ap.add_argument("--root", help="a new folder outside HOME (default: under TMPDIR)")
    ap.add_argument("--dry-run", action="store_true")
    ns = ap.parse_args(argv)
    if ns.runs < 1 or ns.budget <= 0 or ns.timeout <= 0 or ns.poll < 0:
        ap.error("--runs, --budget and --timeout must be positive, and --poll not negative")
    ns.challenger_model = ns.challenger_model or ns.model
    return ns


def refusal(ns, env, root, scan_dirs):
    """Why a real run must not start, or None. The same checks as run_leg.py."""
    home = Path(os.path.realpath(env.get("HOME", os.path.expanduser("~"))))
    if root == home or home in root.parents:
        return f"root {root} is inside HOME ({home}); a run could read it through ~"
    if root.exists():
        return f"root {root} already exists"
    if not run_leg.tag_exists(ns.herd_tag):
        return f"{ns.herd_tag} is not a tag or commit of this repository"
    scan = scan_dirs if scan_dirs is not None else ["/tmp", "/private/tmp", env.get("TMPDIR") or "/tmp"]
    bad = run_leg.preflight(scan, run_leg.denied_paths(root, 0, 0))
    if bad:
        return "the hidden verifier or a probe is readable by a run:\n  " + "\n  ".join(bad)
    return None


def main(argv=None, env=None, scan_dirs=None):
    env = dict(os.environ if env is None else env)
    ns = parse(argv)
    default = os.path.join(env.get("TMPDIR") or "/tmp", "design-eval", f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}")
    root = Path(os.path.realpath(ns.root or default))
    try:
        prompts = {task: case_prompt(case) for task, case in judge.load_cases(ns.cases, ns.case).items()}
        if ns.dry_run:
            dry_run(ns, prompts, root)
            return 0
        why = refusal(ns, env, root, scan_dirs)
        if why:
            raise judge.Refused(why)
        print(f"root: {root}", flush=True)
        Eval(ns, env, root).run(prompts)
    except (judge.Refused, OSError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    print(f"next: python3 {HERE / 'judge.py'} {root / 'results'} && python3 {HERE / 'report.py'} {root / 'results'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
