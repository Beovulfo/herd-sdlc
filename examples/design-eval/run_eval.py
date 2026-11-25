#!/usr/bin/env python3
"""Design eval: do a fresh challenger's questions, answered before any code, fix design mistakes?

  python3 run_eval.py [--case TASK] [--arm NAME] [--runs 12] [--parallel 1] [--root DIR] [--dry-run]

Arms are files in arms/ (see armfile.py). Per case and run, Herd sessions start in run_leg.py's isolation: one
is stopped at its first `herd verify` for the arms that ask after red or not at all, and one is stopped before its
first attack note for the arms that ask before the attacks. Each arm resumes from a copy of that stop, answers,
runs `herd verify` and is stopped again. Nothing is built. Then: judge.py ROOT/results, report.py ROOT/results.
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
import tempfile
import threading
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "supermarket-route" / "verifier")]
import armfile  # noqa: E402
import judge  # noqa: E402
import leak_audit  # noqa: E402
import money  # noqa: E402
import run_leg  # noqa: E402

REPO = run_leg.EXAMPLES.parent
MAX_QUESTIONS = 5
MAX_PARALLEL = 3  # the machine allows 4 sessions in all
MARKER = "QUESTIONS:"  # a challenger that reasons first puts its questions after this line
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


def builder_message(when, questions=None):
    then = THEN["attacks" if when == "before-attacks" else "red"]
    if when == "none":
        return NO_QUESTIONS + then
    return f"{WITH_QUESTIONS}{then}\n\n{questions}"


def _stated(task, field):
    """One `sees` field of a task.toml, as text."""
    def tables(key):
        value = task.get(key)
        return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []

    if field == "inputs_program":
        lines = [f"- {x['program']}" for x in tables("inputs") if x.get("program")]
    elif field == "criteria":
        lines = [f"- {x['text']}" for x in tables("criteria") if x.get("text")]
    else:
        value = task.get("known_limits")
        lines = [str(x) for x in (value if isinstance(value, list) else [value]) if x]
    return "\n".join(lines) or "(none stated)"


HEADINGS = {"request": "REQUEST", "inputs_program": "HOW THE PROGRAM GETS EACH INPUT, as the builder stated it",
            "known_limits": "KNOWN LIMITS, as the builder stated them", "criteria": "SUCCESS CRITERIA"}


def challenger_input(arm, prompt, task_toml):
    """The instruction and what the arm sees. All but the request is read from the stopped session's task.toml."""
    task = {}
    if set(arm["sees"]) - {"request"}:
        try:
            task = tomllib.loads(Path(task_toml).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise judge.Refused(f"cannot read the stopped session's task.toml: {e}") from None
    parts = [f"{HEADINGS[x]}:\n\n{prompt if x == 'request' else _stated(task, x)}" for x in arm["sees"]]
    return "\n\n".join([arm["instruction"], *parts])


def challenger_command(model, arm, budget):
    """judge.py's fresh call; an arm with tools gets only those, and a stream that shows which skills it used."""
    cmd = judge.model_command(model)
    tools = arm.get("tools", "")
    cmd[cmd.index("--tools") + 1] = tools
    cmd[cmd.index("--output-format") + 1] = "stream-json"
    cmd += ["--verbose", "--permission-mode", "dontAsk", "--max-budget-usd", f"{budget:g}"]
    return cmd + (["--allowedTools", tools] if tools else [])


def challenger_reply(stream, skills):
    """(reply, USD) from the stream. The last result is the final one; its cost counts every subagent."""
    results, used = [], set()
    for line in stream.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "result":
            results.append(event)
        content = (event.get("message") or {}).get("content") if event.get("type") == "assistant" else None
        for block in content if isinstance(content, list) else []:
            if block.get("type") == "tool_use" and block.get("name") == "Skill":
                used.add(str((block.get("input") or {}).get("skill")))
    last = results[-1] if results else {}
    cost = last.get("total_cost_usd")
    if last.get("is_error") or not isinstance(last.get("result"), str):
        raise judge.Refused(f"claude call failed: {str(last.get('result') or last.get('subtype'))[:300]}")
    unused = sorted(set(skills) - used)
    if unused:
        raise judge.Refused(f"the challenger never used the skill {', '.join(unused)}")
    return last["result"], cost


def ask_challenger(model, arm, prompt, env, budget, timeout):
    """One fresh call from a temporary project that holds only the arm's skills."""
    found, missing = armfile.skill_files(arm, env)
    if missing:
        raise judge.Refused(f"no skill file at {', '.join(missing)}")
    with tempfile.TemporaryDirectory() as project:
        for name, path in found:
            dest = Path(project) / ".claude" / "skills" / name
            dest.mkdir(parents=True)
            shutil.copyfile(path, dest / "SKILL.md")
        try:
            r = subprocess.run(challenger_command(model, arm, budget), input=prompt, cwd=project, env=env,
                               capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise judge.Refused(f"claude call failed: {e}") from None
    return challenger_reply(r.stdout, [name for name, _ in found])


def first_questions(reply):
    """The reply after its QUESTIONS: line, if any, cut before a sixth numbered question."""
    reply = re.split(rf"(?m)^[ \t#*]*{MARKER}[ \t*]*$", reply)[-1]
    extra = re.search(rf"(?m)^[ \t#*]*{MAX_QUESTIONS + 1}[.)]", reply)
    return (reply[:extra.start()] if extra else reply).strip()


def session_command(ns, prompt, run_dir):
    return run_leg.build_command(ns, "/herd:run " + prompt, run_dir) + ["--include-partial-messages"]


def resume_command(ns, message, run_dir, session_id):
    """Fork, so every arm that starts from one stop continues the same untouched conversation."""
    return run_leg.build_command(ns, message, run_dir) + ["--include-partial-messages", "--resume", session_id,
                                                       "--fork-session"]


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
    def __init__(self, ns, env, root, arms, start=run_leg.start, stop=stop_process, call=None):
        self.ns, self.env, self.root, self.start, self.stop = ns, env, Path(root), start, stop
        self.arms = arms
        self.results, self.logs = self.root / "results", self.root / "logs"
        self.call = call or (lambda arm, prompt: ask_challenger(ns.challenger_model, arm, prompt, env, ns.budget,
                                                                ns.timeout))
        self.live, self.cancelled, self.lock = [], False, threading.Lock()

    def create_session(self, index, total):
        run_dir = run_leg.create_run(self.root, total, index, self.ns, self.env)
        denied = run_leg.outside_home_repo(self.env) + [str(self.results), str(self.logs)]  # earlier runs' output
        settings = run_leg.build_settings(self.root, total, index, denied)
        (run_dir / "settings.json").write_text(json.dumps(settings, indent=2) + "\n")
        return run_dir

    def drive(self, cmd, run_dir, log, done):
        """Run one command until done() or its end; always leave no process behind."""
        with self.lock:
            if self.cancelled:
                raise judge.Refused("the eval was stopped")
            proc = self.start(cmd, run_dir, log, log.with_suffix(".err"), self.env)
            self.live.append(proc)
        try:
            return wait_for(proc, done, self.ns.timeout, self.ns.poll)
        finally:
            self.stop(proc)
            with self.lock:
                self.live.remove(proc)

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

    def arm(self, name, prompt, run_dir, sid, log, out, used):
        """Resume the stopped session for one arm. Adds to `used`; returns the status and its audit findings."""
        arm, questions = self.arms[name], None
        if arm["when"] != "none":
            began = time.monotonic()
            try:
                asked = challenger_input(arm, prompt, out / "before" / "task.toml")
                (out / "challenger_input.md").write_text(asked + "\n")
                reply, used["cost"]["challenger"] = self.call(arm, asked)
            except judge.Refused as e:
                print(f"challenger of {name}: {e}", file=sys.stderr)
                return "challenger-failed", []
            used["seconds"]["challenger"] = time.monotonic() - began
            questions = first_questions(reply)
            (out / "questions.md").write_text(questions + "\n")
        work, resumed = run_dir / "work", log.with_name(f"{log.stem}.{name}.jsonl")
        since, began = time.time(), time.monotonic()
        cmd = resume_command(self.ns, builder_message(arm["when"], questions), run_dir, sid)
        how = self.drive(cmd, run_dir, resumed, lambda: has_answered(work, since))
        used["seconds"]["resume"] = time.monotonic() - began
        used["cost"]["resume"] = money.log_cost(resumed)
        snapshot(work, out / "after")
        findings = [f for path in (log, resumed)
                    for f in leak_audit.audit(path, work, settings=run_dir / "settings.json")]
        found = [f"{f.tool}: {f.detail}" for f in findings if not f.blocked]
        if found:
            return "leak", found
        return ("ok" if how == "reached" else "no-verify"), []

    def session(self, task, n, arms, prompt, run_dir):
        """One first leg, then each of its arms from an identical copy of the work folder."""
        early = self.arms[arms[0]]["when"] == "before-attacks"
        log = self.logs / f"{run_dir.name}.jsonl"
        outs = {arm: self.results / task / arm / f"run-{n}" for arm in arms}
        for arm, out in outs.items():
            out.mkdir(parents=True)
            _record(out, task, arm, n, "incomplete", [])
        began = time.monotonic()
        sid, why = self.first_leg(prompt, run_dir, log, early)
        if why:
            for arm, out in outs.items():
                _record(out, task, arm, n, why, [])
                print(f"{task} {arm} run {n}: {why}", flush=True)
            return
        first = {"seconds": time.monotonic() - began, "cost": money.log_cost(log)}
        work, saved = run_dir / "work", self.logs / f"{run_dir.name}.start-work"
        shutil.copytree(work, saved, symlinks=True)
        for arm, out in outs.items():
            shutil.rmtree(work)
            shutil.copytree(saved, work, symlinks=True)
            snapshot(work, out / "before")
            used = {k: {"first": first[k], "challenger": 0} for k in ("seconds", "cost")}  # each arm bears the start
            status, found = self.arm(arm, prompt, run_dir, sid, log, out, used)
            _record(out, task, arm, n, status, found, used)
            print(f"{task} {arm} run {n}: {status}", flush=True)

    def run(self, prompts):
        plan = sessions(prompts, self.ns.runs, self.arms)
        self.root.parent.mkdir(parents=True, exist_ok=True)
        self.root.mkdir()
        self.results.mkdir()
        self.logs.mkdir()
        settings = {k: getattr(self.ns, k) for k in ("model", "challenger_model", "herd_tag", "budget", "runs",
                                                     "parallel")}
        (self.results / "manifest.json").write_text(json.dumps({**settings, "arms": self.arms}, indent=2) + "\n")

        def one(index, task, n, arms):
            self.session(task, n, arms, prompts[task], self.create_session(index, len(plan)))

        pool = ThreadPoolExecutor(max_workers=min(self.ns.parallel, MAX_PARALLEL))
        try:
            for future in [pool.submit(one, i, *entry) for i, entry in enumerate(plan, 1)]:
                future.result()
        except BaseException:  # also Ctrl-C: sessions have their own process groups, so stop them here
            with self.lock:
                self.cancelled = True
            pool.shutdown(wait=False, cancel_futures=True)
            for proc in list(self.live):
                self.stop(proc)
            raise
        finally:
            pool.shutdown()


def _record(out, task, arm, n, status, findings, used=None):
    data = {"case": task, "arm": arm, "run": n, "status": status, "findings": findings, **(used or {})}
    (out / "run.json").write_text(json.dumps(data, indent=2) + "\n")


def sessions(prompts, runs, arms):
    """(case, run number, arm names) for every first leg: arms that stop at the same point share one."""
    groups = [tuple(n for n, a in arms.items() if (a["when"] == "before-attacks") == early) for early in (False, True)]
    return [(task, n, group) for task in prompts for n in range(1, runs + 1) for group in groups if group]


def dry_run(ns, prompts, root, arms):
    plan = sessions(prompts, ns.runs, arms)
    for index, (task, n, names) in enumerate(plan, 1):
        run_dir = root / f"run-{index}"
        where = f"cd {shlex.quote(str(run_dir / 'work'))} &&"
        early = arms[names[0]]["when"] == "before-attacks"
        stop = "first attack-note command (held before it runs)" if early else "first herd verify"
        print(f"\n# {task} run {n}: session for {', '.join(names)}, stopped at the {stop}")
        print(f"{where} {shlex.join(session_command(ns, prompts[task], run_dir))}")
        for name in names:
            arm = arms[name]
            if arm["when"] != "none":
                skills = "".join(f", with {x} copied in" for x in arm.get("skills", []))
                print(f"# {name} challenger, prompt on stdin, from a temporary project{skills}; "
                      f"sees {', '.join(arm['sees'])}:")
                print(shlex.join(challenger_command(ns.challenger_model, arm, ns.budget)))
            print(f"# {name} resume, stopped at the verify after ANSWERS.md:")
            message = builder_message(arm["when"], "<the challenger's questions>").replace("\n\n", " ")
            print(f"{where} {shlex.join(resume_command(ns, message, run_dir, '<session id>'))}")
    print("\ndry run: nothing started")


def parse(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case", action="append", help="task name; repeat for more (default: every case)")
    ap.add_argument("--cases", default=str(judge.CASES), help="folder of case files")
    ap.add_argument("--arm", action="append", help="arm name; repeat for more (default: every arm)")
    ap.add_argument("--arms", default=str(armfile.ARMS_DIR), help="folder of arm files")
    ap.add_argument("--runs", type=int, default=12, help="runs per arm per case")
    ap.add_argument("--parallel", type=int, default=1, help=f"sessions at once, at most {MAX_PARALLEL}")
    ap.add_argument("--model", default="claude-haiku-5-5", help="the builder")
    ap.add_argument("--challenger-model", help="default: the builder's model")
    ap.add_argument("--herd-tag", default="v0.13.1")
    ap.add_argument("--budget", type=float, default=3, help="USD cap of each session and each resume")
    ap.add_argument("--timeout", type=float, default=900, help="seconds for each session and each resume")
    ap.add_argument("--poll", type=float, default=0.2, help="seconds between looks at the work folder")
    ap.add_argument("--root", help="a new folder outside HOME (default: under TMPDIR)")
    ap.add_argument("--dry-run", action="store_true")
    ns = ap.parse_args(argv)
    if ns.runs < 1 or ns.parallel < 1 or ns.budget <= 0 or ns.timeout <= 0 or ns.poll < 0:
        ap.error("--runs, --parallel, --budget and --timeout must be positive, and --poll not negative")
    if ns.parallel > MAX_PARALLEL:
        print(f"--parallel {ns.parallel} capped at {MAX_PARALLEL}", file=sys.stderr, flush=True)
        ns.parallel = MAX_PARALLEL
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


def usable_arms(ns, env):
    """The asked arms, without those whose skill file is not on this machine: never run an arm without its skill."""
    arms = armfile.load_arms(ns.arms, ns.arm)
    for name, arm in list(arms.items()):
        missing = armfile.skill_files(arm, env)[1]
        if missing:
            print(f"arm {name} skipped: no skill file at {', '.join(missing)}", file=sys.stderr, flush=True)
            del arms[name]
    if not arms:
        raise judge.Refused("no arm left to run")
    return arms


def main(argv=None, env=None, scan_dirs=None):
    env = dict(os.environ if env is None else env)
    ns = parse(argv)
    default = os.path.join(env.get("TMPDIR") or "/tmp", "design-eval", f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}")
    root = Path(os.path.realpath(ns.root or default))
    try:
        prompts = {task: case_prompt(case) for task, case in judge.load_cases(ns.cases, ns.case).items()}
        arms = usable_arms(ns, env)
        if ns.dry_run:
            dry_run(ns, prompts, root, arms)
            return 0
        why = refusal(ns, env, root, scan_dirs)
        if why:
            raise judge.Refused(why)
        print(f"root: {root}", flush=True)
        Eval(ns, env, root, arms).run(prompts)
    except (judge.Refused, OSError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    print(f"next: python3 {HERE / 'judge.py'} {root / 'results'} && python3 {HERE / 'report.py'} {root / 'results'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
