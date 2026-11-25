"""The run loop with fake sessions: stop points, forks from one start, snapshots, statuses. No model call."""
import contextlib
import io
import json
import os
import shlex
import tempfile
import unittest
from pathlib import Path

import judge
import report
import run_eval

PROMPT = "build a thing\nwith \"two\" lines and $HOME `ticks`"


class Proc:
    def __init__(self, code=None):
        self.code = code

    def poll(self):
        return self.code


class FakeClaude:
    """Plays a session: writes what the real one would, into the work folder and the log."""

    def __init__(self, skip=()):
        self.commands, self.seen_work, self.stopped, self.skip = [], [], 0, set(skip)
        self.hooked = []

    def start(self, cmd, run_dir, log, err, env):
        self.commands.append(cmd)
        work = Path(run_dir) / "work"
        task = work / ".herd" / "tasks" / "t"
        resumed = "--resume" in cmd
        arm = log.stem.split(".")[-1] if resumed else None
        log.write_text(json.dumps({"type": "system", "session_id": "forked" if resumed else "first"}) + "\n")
        self.seen_work.append(sorted(p.name for p in work.iterdir() if p.name != ".git"))
        if "session" in self.skip and not resumed:
            return Proc(1)
        task.mkdir(parents=True, exist_ok=True)
        if not resumed:
            early = log.stem == "run-2"
            settings = json.loads((Path(run_dir) / "settings.json").read_text())
            self.hooked.append("hooks" in settings)
            (task / "task.toml").write_text("goal = 'before'\n")
            (work / "main.py").write_text("start\n")
            written = early and "late-hold" in self.skip
            note = {"kind": "tried", "attack": "collision", "text": "x"} if written else {"kind": "decision", "text": "x"}
            if early:
                (Path(run_dir) / run_eval.HELD).touch()
            (task / "notes.jsonl").write_text(json.dumps(note) + "\n")
            if not early or "early" in self.skip:
                (task / "red.json").write_text("{}")
        else:
            self.hooked.append("hooks" in json.loads((Path(run_dir) / "settings.json").read_text()))
            (task / "task.toml").write_text(f"goal = 'after {arm}'\n")
            (work / f"{arm}.txt").write_text("made by this arm\n")
            (work / "ANSWERS.md").write_text(f"answers of {arm}\n")
            if "verify" in self.skip:
                return Proc(0)
            (task / "evidence.json").write_text("{}")
        return Proc()

    def stop(self, proc):
        self.stopped += 1


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.asked = []

    def ask(self, prompt):
        self.asked.append(prompt)
        return "Context.\n" + "".join(f"{i}. question {i}\n" for i in range(1, 9))

    def run_eval(self, fake, runs=1):
        ns = run_eval.parse(["--runs", str(runs), "--herd-tag", "HEAD", "--poll", "0", "--timeout", "5"])
        env = {"HOME": str(self.tmp / "home"), "PATH": os.environ["PATH"]}
        ev = run_eval.Eval(ns, env, self.tmp / "root", start=fake.start, stop=fake.stop, call=self.ask)
        with contextlib.redirect_stdout(io.StringIO()):
            ev.run({"supermarket-route": PROMPT})
        return ev.results / "supermarket-route"

    def status(self, out, arm):
        return json.loads((out / arm / "run-1" / "run.json").read_text())["status"]


class TestRunLoop(Base):
    def test_three_arms_save_before_and_after(self):
        fake = FakeClaude()
        out = self.run_eval(fake)
        for arm in run_eval.ARMS:
            run = out / arm / "run-1"
            self.assertEqual(self.status(out, arm), "ok")
            self.assertEqual((run / "before" / "task.toml").read_text(), "goal = 'before'\n")
            self.assertEqual((run / "after" / "task.toml").read_text(), f"goal = 'after {arm}'\n")
            self.assertEqual((run / "after" / "ANSWERS.md").read_text(), f"answers of {arm}\n")
            self.assertFalse((run / "before" / "ANSWERS.md").exists())
            self.assertTrue((run / "after" / "files" / "main.py").exists())
            self.assertFalse((run / "after" / "files" / ".herd").exists())
        self.assertEqual(fake.stopped, len(fake.commands), "every started process is stopped")

    def test_arms_fork_from_the_same_start(self):
        fake = FakeClaude()
        out = self.run_eval(fake)
        resumes = [c for c in fake.commands if "--resume" in c]
        self.assertEqual(len(resumes), 3)
        for cmd in resumes:
            self.assertEqual(cmd[cmd.index("--resume") + 1], "first")
            self.assertIn("--fork-session", cmd)
        # the second arm does not see the first arm's files
        self.assertFalse((out / "after-red" / "run-1" / "after" / "files" / "control.txt").exists())
        self.assertEqual(fake.seen_work[1], fake.seen_work[2])

    def test_questions_only_in_the_question_arms_and_at_most_five(self):
        fake = FakeClaude()
        out = self.run_eval(fake)
        control, after_red, early = [c[2] for c in fake.commands if "--resume" in c]
        self.assertNotIn("question 1", control)
        self.assertNotIn("challenger", control)
        for message in (after_red, early):
            self.assertIn("5. question 5", message)
            self.assertNotIn("question 6", message)
        self.assertIn("write your attacks", early)
        self.assertNotIn("write your attacks", after_red)
        self.assertEqual(len(self.asked), 2)
        self.assertTrue(all(PROMPT in a for a in self.asked))
        self.assertFalse((out / "control" / "run-1" / "questions.md").exists())

    def test_isolation_is_run_legs(self):
        fake = FakeClaude()
        self.run_eval(fake)
        run_dir = self.tmp / "root" / "run-1"
        settings = json.loads((run_dir / "settings.json").read_text())
        self.assertTrue(settings["sandbox"]["enabled"])
        for name in ("results", "logs"):
            self.assertIn(str(self.tmp / "root" / name), settings["sandbox"]["filesystem"]["denyRead"])
        self.assertIn(str(self.tmp / "root" / "run-2"), settings["sandbox"]["filesystem"]["denyRead"])
        self.assertTrue((run_dir / "plugin" / "scripts" / "herd.py").is_file())
        self.assertEqual(fake.commands[0], run_eval.run_leg.build_command(
            run_eval.parse(["--herd-tag", "HEAD"]), "/herd:run " + PROMPT, run_dir))

    def test_a_session_that_never_stops_where_asked_is_recorded(self):
        out = self.run_eval(FakeClaude(skip={"session"}))
        self.assertEqual([self.status(out, a) for a in run_eval.ARMS], ["no-start"] * 3)
        self.assertEqual(self.asked, [])

    def test_attacks_already_verified_is_a_missed_stop(self):
        out = self.run_eval(FakeClaude(skip={"early"}))
        self.assertEqual(self.status(out, "before-attacks"), "missed-stop")
        self.assertEqual(self.status(out, "control"), "ok")

    def test_only_the_early_first_leg_holds_attack_notes(self):
        fake = FakeClaude()
        self.run_eval(fake)
        # session A, control, after-red, session B, before-attacks
        self.assertEqual(fake.hooked, [False, False, False, True, False])

    def test_an_attack_note_written_before_the_stop_is_a_missed_stop(self):
        out = self.run_eval(FakeClaude(skip={"late-hold"}))
        self.assertEqual(self.status(out, "before-attacks"), "missed-stop")

    def test_resume_without_a_verify_is_not_ok(self):
        out = self.run_eval(FakeClaude(skip={"verify"}))
        self.assertEqual([self.status(out, a) for a in run_eval.ARMS], ["no-verify"] * 3)

    def test_failed_challenger_is_recorded(self):
        def broken(prompt):
            raise judge.Refused("claude call failed")
        self.ask = broken
        with contextlib.redirect_stderr(io.StringIO()):
            out = self.run_eval(FakeClaude())
        self.assertEqual(self.status(out, "after-red"), "challenger-failed")
        self.assertEqual(self.status(out, "control"), "ok")


class TestWholeChain(Base):
    def test_a_runs_results_go_straight_to_the_judge_and_the_report(self):
        results = self.run_eval(FakeClaude()).parent
        cases = judge.load_cases()
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            self.assertEqual(judge.label_results(results, cases, lambda p: '{"label": "shelf", "quote": ""}'), 0)
            self.assertEqual(report.main([str(results)]), 0, out.getvalue())
        self.assertIn("shelf→shelf: 1", out.getvalue())


class TestStopPoints(Base):
    def write(self, rel, text="{}", at=None):
        path = self.tmp / "work" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        if at is not None:
            os.utime(path, (at, at))
        return path

    def test_attack_note_and_red(self):
        work = self.tmp / "work"
        self.write(".herd/tasks/t/notes.jsonl", '{"kind": "decision"}\nnot json\n')
        self.assertFalse(run_eval.has_attack_note(work))
        self.assertFalse(run_eval.has_red(work))
        self.write(".herd/tasks/t/notes.jsonl", '{"kind": "tried", "attack": "recount"}\n')
        self.write(".herd/tasks/t/red.json")
        self.assertTrue(run_eval.has_attack_note(work))
        self.assertTrue(run_eval.has_red(work))

    def test_answered_needs_a_verify_after_the_answers_and_the_resume(self):
        work = self.tmp / "work"
        self.write(".herd/tasks/t/evidence.json", at=100)
        self.assertFalse(run_eval.has_answered(work, 50))
        self.write("ANSWERS.md", "a", at=200)
        self.assertFalse(run_eval.has_answered(work, 50), "the verify is older than the answers")
        self.write(".herd/tasks/t/evidence.json", at=300)
        self.assertTrue(run_eval.has_answered(work, 50))
        self.assertFalse(run_eval.has_answered(work, 400), "the verify is older than the resume")

    def test_a_link_out_of_the_work_folder_is_not_read(self):
        secret = self.tmp / "secret"
        secret.write_text("private")
        self.write("main.py", "x")
        (self.tmp / "work" / "ANSWERS.md").symlink_to(secret)
        run_eval.snapshot(self.tmp / "work", self.tmp / "snap")
        self.assertFalse((self.tmp / "snap" / "ANSWERS.md").exists())
        self.assertTrue((self.tmp / "snap" / "files" / "ANSWERS.md").is_symlink())
        self.assertNotIn("private", judge.material(self.tmp / "snap"))

    def test_wait_for(self):
        self.assertEqual(run_eval.wait_for(Proc(), lambda: True, 5, 0), "reached")
        self.assertEqual(run_eval.wait_for(Proc(0), lambda: False, 5, 0), "exited")
        self.assertEqual(run_eval.wait_for(Proc(), lambda: False, 0, 0), "timeout")


class TestHook(Base):
    def test_hook_matches_attack_notes_only(self):
        command = run_eval.hold_hook(self.tmp)["PreToolUse"][0]["hooks"][0]["command"]
        self.assertIn("*note*--attack*", command)
        self.assertIn(str(self.tmp / run_eval.HELD), command)


class TestRace(Base):
    def test_a_file_that_vanishes_mid_look_does_not_abort_the_eval(self):
        looks = []

        def done():
            looks.append(1)
            if len(looks) == 1:
                raise FileNotFoundError("ANSWERS.md")
            return True

        self.assertEqual(run_eval.wait_for(Proc(), done, 5, 0), "reached")


class TestDryRun(Base):
    def test_prints_every_arm_and_creates_nothing(self):
        out = io.StringIO()
        root = self.tmp / "never"
        with contextlib.redirect_stdout(out):
            code = run_eval.main(["--case", "supermarket-route", "--runs", "1", "--dry-run", "--root", str(root)])
        text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertEqual(sum("--resume" in line for line in text.splitlines()), 3)
        self.assertEqual(sum("/herd:run" in line for line in text.splitlines()), 2)
        challengers = [line for line in text.splitlines() if line.startswith("claude -p")]
        self.assertEqual(len(challengers), 2)
        self.assertEqual(shlex.split(challengers[0])[shlex.split(challengers[0]).index("--tools") + 1], "")
        self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
