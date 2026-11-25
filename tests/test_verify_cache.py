"""`herd verify` skips an unchanged tree; attack notes are not "logged together" (issue #100)."""
import json
import os
import random
import re
from unittest import mock

from scripts import herd
from tests.test_harness_rules import Base
from tests.test_herd_cli import run_herd

# The check appends one line outside the repository per run, so a run is counted without touching the tree.
TASK = '''goal = "Count runs"
test_budget = "one check"
known_limits = "none shown"
inputs = []

[[criteria]]
id = "C1"
text = "the check runs"
source = "agent-proposed"
check = 'echo x >> "{count}"; test ! -f fail.txt'
'''


class Case(Base):
    def setUp(self):
        super().setUp()
        self.count = self.root / ".git" / "runs"
        self.task_text = TASK.format(count=self.count)
        self.start(self.task_text)
        (self.root / "app.py").write_text("x = 1\n")

    def runs(self):
        return len(self.count.read_text().splitlines()) if self.count.exists() else 0

    def verify(self, *args):
        before = self.runs()
        p = run_herd(self.root, "verify", *args)
        self.assertNotIn("Traceback", p.stderr)
        return self.runs() - before, p

    def ev_bytes(self):
        return (self.root / ".herd/tasks/t1/evidence.json").read_bytes()

    def attack(self, text="n/a: nothing", name="collision"):
        p = run_herd(self.root, "note", "--tried", "--attack", name, text)
        self.assertEqual(p.returncode, 0, p.stderr)


class TestSkip(Case):
    def test_unchanged_tree_runs_nothing(self):
        self.assertEqual(self.verify()[0], 1)
        kept, at = self.ev_bytes(), json.loads(self.ev_bytes())["at"]
        fails = (self.root / ".herd/tasks/t1/fails.json").read_bytes()
        for args in ((), ("--verbose",), ("t1",)):
            n, p = self.verify(*args)
            self.assertEqual((n, p.returncode), (0, 0), p.stderr)
            self.assertIn(f"unchanged since the verify at {at}", p.stdout)
            self.assertIn("1 passing, 0 failing", p.stdout)
        self.assertEqual(self.ev_bytes(), kept)
        self.assertEqual((self.root / ".herd/tasks/t1/fails.json").read_bytes(), fails)

    def test_unchanged_tree_runs_nothing_when_failing_and_keeps_the_exit_code(self):
        (self.root / "fail.txt").write_text("")
        self.assertEqual(self.verify()[1].returncode, 1)
        n, p = self.verify()
        self.assertEqual((n, p.returncode), (0, 1))
        self.assertIn("C1 failing", p.stdout)

    def test_unchanged_tree_runs_nothing_after_a_commit_or_another_note(self):
        self.verify()
        self.git("add", "-A", "--", "app.py")
        self.git("commit", "-q", "-m", "app")
        for kind in ("--found", "--fixed", "--open", "--decision", "--tried"):
            run_herd(self.root, "note", kind, "x")
        self.assertEqual(self.verify()[0], 0)

    def git(self, *args):
        import subprocess
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def test_any_change_reruns(self):
        self.verify()
        rng = random.Random(100)
        task = self.root / ".herd/tasks/t1/task.toml"
        changes = [
            lambda: (self.root / "app.py").write_text("x = 2\n"),  # untracked, edited
            lambda: (self.root / "README.md").write_text("changed"),  # tracked, edited
            lambda: (self.root / "README.md").write_text("x"),  # and put back
            lambda: (self.root / "README.md").unlink(),  # tracked, deleted
            lambda: os.chmod(self.root / "app.py", 0o755),
            lambda: (self.root / "app.py").rename(self.root / "main.py"),
            lambda: task.write_text(task.read_text() + "\n"),
            lambda: self.attack(),
            lambda: self.attack(),  # the same note again is one more note
            lambda: run_herd(self.root, "note", "--human-change", "C9: nothing"),
        ]
        for i in range(12):
            name = f"{'d/' * rng.randrange(3)}f{i}{rng.choice(['', '.py', '.md', ' space', 'é'])}"
            changes.append(lambda name=name, data=rng.randbytes(rng.randrange(50)): (
                (self.root / name).parent.mkdir(parents=True, exist_ok=True), (self.root / name).write_bytes(data)))
        for i, change in enumerate(changes):
            with self.subTest(i=i):
                change()
                self.assertEqual(self.verify()[0], 1)
                self.assertEqual(self.verify()[0], 0)

    def test_any_change_reruns_when_state_is_missing_old_or_corrupt(self):
        ev = self.root / ".herd/tasks/t1/evidence.json"
        self.verify()
        data = json.loads(ev.read_text())
        data.pop("verified_inputs")  # evidence from an older Herd
        ev.write_text(json.dumps(data))
        self.assertEqual(self.verify()[0], 1)
        for broken in ("{", "[]", "{}", ""):
            ev.write_text(broken)
            self.assertEqual(self.verify()[0], 1, broken)
        (self.root / ".herd/tasks/t1/pr").write_text("https://example.com/pull/1\n")  # `herd pr` opened one
        self.assertEqual(self.verify()[0], 1)
        (self.root / ".herd/tasks/t1/frozen.json").unlink()
        self.assertEqual(self.verify()[0], 1)

    def test_any_change_reruns_outside_git(self):
        self.verify()
        with mock.patch.object(herd, "git_state", return_value=None):
            self.assertEqual(self.verify()[0], 1)
            self.assertEqual(self.verify()[0], 1)

    def test_fresh_flag(self):
        self.verify()
        for args in (("--fresh",), ("--fresh", "t1"), ("t1", "--verbose", "--fresh")):
            n, p = self.verify(*args)
            self.assertEqual((n, p.returncode), (1, 0), p.stderr)
            self.assertNotIn("unchanged since", p.stdout)
        n, p = self.verify("--fresh", "--only", "C1")  # --only always runs its one check
        self.assertEqual((n, p.returncode), (1, 0), p.stderr)


class TestNotes(Case):
    def logged(self, *notes):
        (self.root / ".herd/tasks/t1/notes.jsonl").write_text("".join(
            json.dumps({"at": "2026-11-22T10:00:01Z", "elapsed_s": 1, "text": "n/a: x", **n}) + "\n" for n in notes))
        self.verify("--fresh")
        return "logged within" in run_herd(self.root, "status").stdout

    def test_attack_notes_together_not_flagged(self):
        six = [{"kind": "tried", "attack": a} for a in herd.ATTACKS]
        self.assertFalse(self.logged(*six))
        self.assertFalse(self.logged(*six, {"kind": "found"}, {"kind": "fixed"}))
        for kind in ("found", "fixed", "open"):
            self.assertTrue(self.logged(*six, *[{"kind": kind}] * 3), kind)
        self.assertTrue(self.logged({"kind": "found"}, {"kind": "fixed"}, {"kind": "open"}))


class TestUsage(Case):
    def test_bad_flag_prints_usage(self):
        for args, named in (
                (["--tried", "--atack", "collision", "x"], "--atack"),
                (["--tried", "--attack=collision", "x"], "--attack=collision"),
                (["--found", "--severity", "x"], "--severity"),
                (["--found", "--fixed", "x"], "--fixed"),
                (["--tried", "x", "--check"], "--check"),
                (["--tried", "--attack", "collision", "--check", "true", "--timeout", "soon", "x"], "--timeout"),
                (["--found", "--check", "true", "x"], "--check"),
                (["--tried", "--attack", "nope", "x"], "--attack"),
                (["--tried", "--attack", "recount", "--refuses", "true", "--check", "true", "x"], "--refuses"),
                (["x"], "--found"),
                (["--found", "x", "y"], "y")):
            with self.subTest(args=args):
                p = run_herd(self.root, "note", *args)
                self.assertEqual(p.returncode, 1)
                self.assertIn(f"usage: {herd.USAGE['note']}", p.stderr)
                self.assertTrue(re.search(re.escape(named), p.stderr.split("usage:")[0]), p.stderr)
        self.assertEqual(herd.load_notes(self.root, "t1"), [])
