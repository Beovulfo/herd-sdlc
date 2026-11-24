"""`herd verify` reads git state once: count the git processes it starts, with a PATH shim that logs each call."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERD = str(Path(__file__).resolve().parent.parent / "plugin" / "scripts" / "herd.py")
TASK = '''goal = "Add a greeting"
test_budget = "One file check"
known_limits = "Only the file is checked"
inputs = []

[[criteria]]
id = "C1"
text = "Given a name, when greet runs, then greet.txt exists"
source = "human"
coverage = "Proves greet.txt exists; not what it says"
check = "test -f greet.txt"
'''


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


class TestOneGitCall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root, shim, self.log = base / "repo", base / "shim", base / "calls.log"
        self.root.mkdir()
        shim.mkdir()
        real = shutil.which("git")
        (shim / "git").write_text(f'#!/bin/sh\necho "$*" >> "{self.log}"\nexec "{real}" "$@"\n')
        (shim / "git").chmod(0o755)
        self.env = dict(os.environ, PATH=f"{shim}{os.pathsep}{os.environ['PATH']}")
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "t")
        (self.root / "README.md").write_text("x")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "init")
        self.herd("init", "t1", "Add a greeting")
        (self.root / ".herd/tasks/t1/task.toml").write_text(TASK)

    def tearDown(self):
        self.tmp.cleanup()

    def herd(self, *args):
        return subprocess.run([sys.executable, HERD, *args], cwd=self.root, env=self.env, capture_output=True, text=True)

    def git_calls(self, *args):
        """The git commands one herd command started."""
        self.log.write_text("")
        p = self.herd(*args)
        self.assertNotIn("Traceback", p.stderr)
        self.assertIn(p.returncode, (0, 1), p.stderr)
        return self.log.read_text().splitlines()

    def test_verify_with_uncommitted_work_makes_one_git_call(self):
        (self.root / "greet.txt").write_text("hello")
        (self.root / "notes.md").write_text("an untracked file")
        (self.root / "README.md").write_text("changed")
        self.herd("verify")  # the red run also lists stashes (once per task)
        calls = self.git_calls("verify")
        self.assertEqual(len(calls), 1, calls)
        self.assertTrue(calls[0].startswith("status --porcelain=v2 --branch -z --untracked-files=all"), calls)

    def test_first_verify_adds_only_the_stash_list(self):
        calls = self.git_calls("verify")
        self.assertEqual(len(calls), 2, calls)
        self.assertTrue(calls[1].startswith("stash list"), calls)

    def test_verify_after_a_commit_adds_one_diff_against_the_start_commit(self):
        self.herd("verify")
        (self.root / "greet.txt").write_text("hello")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "greet")
        calls = self.git_calls("verify")
        self.assertEqual(len(calls), 2, calls)
        self.assertTrue(calls[0].startswith("status --porcelain=v2"), calls)
        self.assertTrue(calls[1].startswith("diff -z --name-only"), calls)

    def test_a_commit_does_not_change_the_content_id(self):
        self.herd("verify")
        (self.root / "greet.txt").write_text("hello")
        (self.root / "new.md").write_text("n")
        self.herd("verify")
        before = json.loads((self.root / ".herd/tasks/t1/evidence.json").read_text())["content"]
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "greet")
        self.herd("verify")
        after = json.loads((self.root / ".herd/tasks/t1/evidence.json").read_text())["content"]
        self.assertTrue(before)
        self.assertEqual(before, after)
        (self.root / "greet.txt").write_text("changed")
        self.herd("verify")
        self.assertNotEqual(after, json.loads((self.root / ".herd/tasks/t1/evidence.json").read_text())["content"])


if __name__ == "__main__":
    unittest.main()
