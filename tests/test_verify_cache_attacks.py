"""The standard attacks on issue #100, with code that does not reuse the skip rule.

`python3 -m tests.test_verify_cache_attacks twice` verifies a tiny task twice and prints how often its check ran."""
import hashlib
import os
import random
import sys
import unittest

from tests.test_herd_cli import run_herd
from tests.test_verify_cache import Case


def snapshot(root):
    """Everything the human calls the tree, task.toml and the attack notes, read from disk with no project code."""
    files = {}
    for d, dirs, names in os.walk(root):
        dirs[:] = [x for x in dirs if x not in (".git", ".herd")]
        for n in names:
            p = os.path.join(d, n)
            with open(p, "rb") as f:
                files[os.path.relpath(p, root)] = (os.stat(p).st_mode & 0o111, hashlib.sha256(f.read()).hexdigest())
    task = root / ".herd/tasks/t1"
    notes = (task / "notes.jsonl").read_text().splitlines() if (task / "notes.jsonl").exists() else []
    return files, (task / "task.toml").read_bytes(), [x for x in notes if '"attack"' in x]


class TestRecount(Case):
    def test_check_runs_exactly_when_the_snapshot_changed(self):
        """recount and refusal: random edits, no-ops and touches; runs are counted from the check's own file."""
        rng, last = random.Random(7), None
        for step in range(50):
            f = self.root / f"f{rng.randrange(4)}.txt"
            op = rng.choice(["write", "delete", "touch", "nothing", "nothing", "note", "attack", "toml"])
            if op == "write":
                f.write_text(rng.choice("ab"))  # often the same bytes again: not a change
            elif op == "delete":
                f.unlink(missing_ok=True)
            elif op == "touch" and f.exists():
                os.utime(f, (1, 1))
            elif op == "note":
                run_herd(self.root, "note", "--found", f"n{step}")
            elif op == "attack":
                self.attack()
            elif op == "toml":
                t = self.root / ".herd/tasks/t1/task.toml"
                t.write_text(self.task_text + rng.choice(["", "\n"]))
            now = snapshot(self.root)
            with self.subTest(step=step, op=op):
                self.assertEqual(self.verify()[0], int(now != last))
            last = now


class TestBadInput(Case):
    def test_every_bad_argument_ends_in_a_message(self):
        self.verify()
        for args in (["verify", "nope"], ["verify", "--fresh", "nope"], ["verify", "--fresh=1"], ["note"],
                     ["note", "--found"], ["note", "--bogus"], ["note", "--tried", "--attack"], ["note", "--found", ""]):
            with self.subTest(args=args):
                p = run_herd(self.root, *args)
                self.assertNotEqual(p.returncode, 0, p.stdout)
                self.assertTrue(p.stderr.strip())
                self.assertNotIn("Traceback", p.stderr)
        (self.root / ".herd/tasks/t1/task.toml").write_text("goal = ")
        p = run_herd(self.root, "verify")
        self.assertEqual(p.returncode, 1)
        self.assertNotIn("Traceback", p.stderr)


class TestCollision(Case):
    def test_same_bytes_under_two_names_and_equal_notes_each_count(self):
        (self.root / "a.txt").write_text("same")
        self.verify()
        (self.root / "b.txt").write_text("same")
        self.assertEqual(self.verify()[0], 1)
        (self.root / "a.txt").rename(self.root / "c.txt")
        self.assertEqual(self.verify()[0], 1)
        self.attack()
        self.attack()
        self.assertEqual(self.verify()[0], 1)
        self.attack()
        self.assertEqual(self.verify()[0], 1)


class TestOneBadPart(Case):
    def test_a_corrupt_state_file_never_reuses_old_results(self):
        d = self.root / ".herd/tasks/t1"
        for name in ("evidence.json", "start.json", "red.json", "frozen.json"):
            self.verify("--fresh")
            (d / name).write_text("{broken")
            with self.subTest(name=name):
                n, p = self.verify()
                self.assertEqual(n, 1, p.stdout)


def twice():
    Case.setUpClass()
    case = Case()
    case.refuses_first = False
    case.setUp()
    try:
        for _ in range(2):
            run_herd(case.root, "verify")
        print(f"checks run: {case.runs()}")
    finally:
        case.tearDown()
        Case.tearDownClass()


if __name__ == "__main__":
    if sys.argv[1:] == ["twice"]:
        twice()
    else:
        unittest.main()
