import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import herd
from tests import fastgit


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


class TestFastGit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "t")
        (self.root / "a.txt").write_text("1")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "init")

    def tearDown(self):
        self.tmp.cleanup()

    def test_same_state_is_answered_from_the_cache(self):
        herd._git(self.root, "rev-parse", "HEAD")
        with mock.patch("subprocess.run", side_effect=AssertionError("git started")):
            self.assertTrue(herd._git(self.root, "rev-parse", "HEAD"))

    def test_edit_untracked_commit_and_ignore_change_the_answer(self):
        self.assertEqual(herd._git(self.root, "diff", "HEAD", "--"), b"")
        (self.root / "a.txt").write_text("2")
        self.assertIn(b"+2", herd._git(self.root, "diff", "HEAD", "--"))
        self.assertEqual(herd._git(self.root, "ls-files", "--others", "--exclude-standard"), b"")
        (self.root / "new.txt").write_text("x")
        self.assertIn(b"new.txt", herd._git(self.root, "ls-files", "--others", "--exclude-standard"))
        (self.root / ".gitignore").write_text("new.txt\n")
        self.assertNotIn(b"new.txt", herd._git(self.root, "ls-files", "--others", "--exclude-standard"))
        before = herd._git(self.root, "rev-parse", "HEAD")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "two")
        self.assertNotEqual(herd._git(self.root, "rev-parse", "HEAD"), before)

    def test_writing_commands_are_never_cached_and_outside_a_repo_is_not_cached(self):
        self.assertIsNone(fastgit.state(tempfile.gettempdir() + "/nowhere-xyz"))
        self.assertEqual(herd._git(self.root, "stash", "list"), b"")
        (self.root / "a.txt").write_text("3")
        git(self.root, "stash", "push", "-q")
        self.assertIn(b"WIP", herd._git(self.root, "stash", "list"))
