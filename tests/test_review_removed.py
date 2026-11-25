"""0.13.0 removed the review. These tests build their tasks through the CLI and hand-written JSON, with no
Herd function, and run `herd` as a subprocess. `python3 -m tests.test_review_removed example` runs `herd done`
on a task that holds 0.12.x review notes."""
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HERD = REPO / "plugin" / "scripts" / "herd.py"
REMOVED = ("review", "review-brief", "review-hook")
CHECK = "python3 -m unittest tests.test_app"
GOAL = "Add a greeting; old tasks that hold review notes still finish"
TASK = f"""goal = "Add a greeting"
test_budget = "one unit test"
known_limits = "none known"
inputs = []

[[criteria]]
id = "C1"
text = "the greeting is hello"
source = "agent-proposed"
check = "{CHECK}"
"""


def run(root, *args, stdin=""):
    return subprocess.run([sys.executable, str(HERD), *args], cwd=root, input=stdin, capture_output=True, text=True)


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def ok(p):
    if p.returncode:
        raise AssertionError(f"exit {p.returncode}: {p.stdout}{p.stderr}")
    return p


def build(root, risk="medium", toml=""):
    """A task whose checks and attacks pass, with no review."""
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    (root / "herd.toml").write_text(f'[floor]\n{risk} = ["app.py"]\n{toml}')
    (root / ".gitignore").write_text("__pycache__/\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    ok(run(root, "init", "t1", GOAL + " in app.py", "--request", GOAL + " in app.py"))
    (root / ".herd/tasks/t1/task.toml").write_text(TASK)
    (root / "tests").mkdir()
    (root / "tests/__init__.py").write_text("")
    (root / "tests/test_app.py").write_text(
        "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_hello(self):\n"
        "        import app\n        self.assertEqual(app.hello(), 'hello')\n")
    for name in ("refusal", "other-reading"):
        ok(run(root, "note", "--tried", "--attack", name, "n/a: no inputs"))
    run(root, "verify")  # red
    (root / "app.py").write_text("def hello():\n    return 'hello'\n")
    for name in ("bad-input", "collision", "recount", "one-bad-part"):
        refuses = {"collision": "n/a: the app takes no input",
                   "one-bad-part": "python3 -c 'import app,sys; sys.exit(\"no\")'"}.get(name)
        extra = ["--refuses", refuses] if refuses else []
        ok(run(root, "note", "--tried", "--attack", name, "--check", CHECK, *extra, name))
    ok(run(root, "verify"))


def old_review(rng):
    """A review note as 0.12.x wrote it: by the hook, or by hand with `herd review --by`."""
    note = {"at": "2026-01-01T00:00:00Z", "kind": "review", "text": f"finding {rng.randrange(1000)}",
            "by": "a subagent", "risk": rng.choice(["medium", "high"])}
    if rng.random() < 0.7:
        note.update({"source": "hook", "tier": "sonnet", "verdict": rng.choice(["PASS", "FINDINGS", None]),
                     "saw": rng.choice([True, False])})
    return note


def make_old(root, rng, count):
    """Turn a task into one that 0.12.x left behind, writing the files by hand."""
    d = root / ".herd/tasks/t1"
    with (d / "notes.jsonl").open("a") as f:
        for _ in range(count):
            f.write(json.dumps(old_review(rng)) + "\n")
    start = json.loads((d / "start.json").read_text())
    with (d / "notes.jsonl").open("a") as f:  # the 0.11.0 intake reviewer's leftovers
        f.write(json.dumps({"at": "2026-01-01T00:00:00Z", "kind": "intake", "text": "HERD-INTAKE: FAIL"}) + "\n")
    start.update({"intake": True, "review": {"tiers": ["haiku", "sonnet", "opus"], "step": rng.choice([0, 1])},
                  "sessions": ["/nowhere/session.jsonl"]})
    (d / "start.json").write_text(json.dumps(start) + "\n")
    (d / "green.json").write_text(json.dumps({"at": "2026-01-01T00:00:00Z", "notes": 0}) + "\n")


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def sub(self, name):
        (self.root / name).mkdir()
        return self.root / name


class TestOtherReading(Tmp):
    """Each reading of "old tasks that hold review notes" finishes: no choosing, converting or cleaning up first."""

    def test_old_tasks_in_every_reading_finish(self):
        rng = random.Random(87)
        for i, (risk, count, toml) in enumerate([
                ("medium", 1, ""), ("high", 5, ""), ("medium", 3, '[review]\ntiers = ["a"]\nstep = 9\n'),
                ("high", 2, '[review]\nstep = "bad"\n')]):
            with self.subTest(risk=risk, count=count, toml=toml):
                root = self.sub(f"r{i}")
                build(root, risk, toml)
                make_old(root, rng, count)
                p = ok(run(root, "done"))
                self.assertNotIn("Review:", p.stdout)


class TestRefusal(Tmp):
    """Refused: the three removed commands. Never refused: a finished task for want of a review."""

    def test_removed_commands_are_refused(self):
        build(self.root)
        listed = run(self.root, "help").stdout
        rng = random.Random(1)
        for cmd in REMOVED:
            self.assertNotIn(f"herd {cmd}", listed)
            for args in ([], ["--by", "me", "fine"], [str(rng.randrange(100))], ["--skipped", "x"]):
                with self.subTest(cmd=cmd, args=args):
                    p = run(self.root, cmd, *args)
                    self.assertEqual(p.returncode, 2, p.stdout)
                    self.assertIn("unknown command", p.stderr)

    def test_done_never_refuses_for_a_missing_review(self):
        rng = random.Random(2)
        for i in range(4):
            risk, broken = rng.choice(["medium", "high"]), i % 2 == 1
            with self.subTest(risk=risk, broken=broken):
                root = self.sub(f"r{i}")
                build(root, risk)
                if broken:
                    (root / "app.py").write_text("def hello():\n    return 'no'\n")
                    run(root, "verify")
                p = run(root, "done")
                self.assertEqual(p.returncode == 0, not broken, p.stdout + p.stderr)
                self.assertNotIn("review", (p.stdout + p.stderr).lower())


class TestBadInput(Tmp):
    def test_removed_commands_and_odd_review_data_never_traceback(self):
        build(self.root)
        calls = [run(self.root, cmd, stdin=raw) for cmd in REMOVED for raw in ("", "{not json", "[1]", "{}")]
        with (self.root / ".herd/tasks/t1/notes.jsonl").open("a") as f:
            f.write(json.dumps({"at": "2026-01-01T00:00:00Z", "kind": "review", "text": ""}) + "\n")
        (self.root / "herd.toml").write_text('review = 5\n[floor]\nmedium = ["app.py"]\n')
        calls += [run(self.root, c) for c in ("status", "verify", "done")]
        for p in calls:
            self.assertNotIn("Traceback", p.stdout + p.stderr)
        self.assertEqual([p.returncode for p in calls[-3:]], [0, 0, 0], calls[-1].stderr)


class TestCollision(Tmp):
    def test_many_identical_review_notes_never_block(self):
        build(self.root, "high")
        note = {"at": "2026-01-01T00:00:00Z", "kind": "review", "text": "same", "source": "hook",
                "verdict": "FINDINGS", "risk": "high"}
        with (self.root / ".herd/tasks/t1/notes.jsonl").open("a") as f:
            f.write((json.dumps(note) + "\n") * 9)
        ok(run(self.root, "done"))


class TestOneBadPart(Tmp):
    def test_one_malformed_review_note_does_not_stop_the_task(self):
        build(self.root)
        with (self.root / ".herd/tasks/t1/notes.jsonl").open("a") as f:
            f.write(json.dumps({"at": "2026-01-01T00:00:00Z", "kind": "review", "text": "x", "verdict": 7,
                                "tier": None}) + "\n")
        ok(run(self.root, "done"))


class TestRecount(Tmp):
    def test_report_counts_match_the_files(self):
        build(self.root)
        rng = random.Random(3)
        make_old(self.root, rng, 4)
        for kind in ["found"] * 3 + ["fixed"] * 2:
            ok(run(self.root, "note", f"--{kind}", f"item {rng.randrange(1000)}"))
        out = ok(run(self.root, "done")).stdout
        lines = (self.root / ".herd/tasks/t1/notes.jsonl").read_text().splitlines()
        want = sum(json.loads(line)["kind"] in ("found", "fixed") for line in lines)
        caveats = next(line for line in out.splitlines() if line.startswith("Caveats:"))
        self.assertEqual(caveats.count("found at ") + caveats.count("fixed at "), want)
        self.assertEqual(TASK.count("[[criteria]]"), 1)
        self.assertIn("Proven: 1 of 1 criteria", out)


def example():
    """`herd done` on a task as 0.12.x left it: hook and hand review notes, and the old start.json keys."""
    with tempfile.TemporaryDirectory() as tmp:
        build(Path(tmp), "high")
        make_old(Path(tmp), random.Random(0), 3)
        p = run(tmp, "done")
        print(p.stdout + p.stderr)
        return p.returncode


def refused(bad):
    """`herd verify` on a 0.12.x task whose task.toml holds `bad`: it must refuse."""
    with tempfile.TemporaryDirectory() as tmp:
        build(Path(tmp))
        make_old(Path(tmp), random.Random(0), 2)
        with (Path(tmp) / ".herd/tasks/t1/task.toml").open("a") as f:
            f.write(bad)
        p = run(tmp, "verify")
        sys.stdout.write(p.stdout)
        sys.stderr.write(p.stderr)
        return p.returncode


BAD = {"collision": '\n[[criteria]]\nid = "C1"\ntext = "other"\nsource = "agent-proposed"\ncheck = "false"\n',
       "broken": '\n[[criteria]]\nid = "C2"\nsource = "agent-proposed"\ncheck = "python3 app.py"\n'}

if __name__ == "__main__":
    if sys.argv[1:] == ["example"]:
        sys.exit(example())
    if len(sys.argv) == 2 and sys.argv[1] in BAD:
        sys.exit(refused(BAD[sys.argv[1]]))
    unittest.main()
