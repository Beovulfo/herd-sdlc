"""Evidence stays fresh across a commit: freshness is decided by content, not by a hash of HEAD (Herd 0.12.6)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import herd
from tests import test_herd_cli as T

HERD = str(Path(herd.__file__))

ONE = '''goal = "Add a greeting"
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


class Fresh(T.Base):
    def setUp(self):
        super().setUp()
        T.git(self.root, "switch", "-q", "-c", "herd/t1")
        self.task(ONE, attacks=True)
        (self.root / "greet.txt").write_text("hello")

    def herd(self, *args):
        return T.run_herd(self.root, *args)

    def verify(self):
        p = self.herd("verify")
        self.assertNotIn("Traceback", p.stderr)

    def commit(self, *files):
        T.git(self.root, "add", *(files or ["-A", "--", ".", ":!.herd"]))
        T.git(self.root, "commit", "-q", "-m", "work")

    def sha(self):
        return herd._git(self.root, "rev-parse", "HEAD").decode().strip()

    def evidence(self):
        return json.loads((herd._dir(self.root, "t1") / "evidence.json").read_text())

    def stale(self):
        return any("stale" in p for p in herd.problems(self.root, "t1"))


class TestCommit(Fresh):
    def test_commit_alone_is_not_stale(self):
        self.verify()
        self.assertEqual(herd.problems(self.root, "t1"), [])
        self.commit()
        self.assertEqual(herd.problems(self.root, "t1"), [])
        self.assertEqual(self.herd("gate").returncode, 0)
        p = self.herd("done")
        self.assertEqual(p.returncode, 0, p.stderr)


class TestEdits(Fresh):
    def test_verify_edit_commit(self):
        self.verify()
        (self.root / "greet.txt").write_text("changed")
        self.commit()
        self.assertTrue(self.stale())

    def test_verify_commit_edit(self):
        self.verify()
        self.commit()
        (self.root / "greet.txt").write_text("changed")
        self.assertTrue(self.stale())

    def test_amend_to_other_content(self):
        self.verify()
        self.commit()
        (self.root / "greet.txt").write_text("other")
        T.git(self.root, "commit", "-q", "-a", "--amend", "-m", "work")
        self.assertTrue(self.stale())

    def test_reset_to_other_content(self):
        self.commit()
        self.verify()
        T.git(self.root, "reset", "-q", "--hard", "HEAD~1")
        self.assertTrue(self.stale())

    def test_task_toml_edit(self):
        self.verify()
        self.commit()
        path = herd._dir(self.root, "t1") / "task.toml"
        path.write_text(path.read_text() + "\n# edited\n")
        self.assertTrue(self.stale())


    def test_edit_back_to_start_content(self):
        (self.root / "greet.txt").write_text("hello")
        self.commit()
        self.verify()
        (self.root / "greet.txt").write_text("changed")
        self.verify()
        T.git(self.root, "checkout", "-q", "--", "greet.txt")
        self.assertTrue(self.stale())

    def test_delete_a_verified_file(self):
        self.verify()
        (self.root / "greet.txt").unlink()
        self.assertTrue(self.stale())

    def test_new_untracked_file(self):
        self.verify()
        (self.root / "extra.txt").write_text("x")
        self.assertTrue(self.stale())

    def test_second_commit_without_an_edit(self):
        self.verify()
        self.commit()
        T.git(self.root, "commit", "-q", "--allow-empty", "-m", "again")
        self.assertEqual(herd.problems(self.root, "t1"), [])


class TestFinalCommit(Fresh):
    def test_done_names_the_final_commit(self):
        self.verify()
        old = self.sha()
        self.assertTrue(self.evidence()["dirty"])
        self.commit()
        new = self.sha()
        p = self.herd("done")
        self.assertEqual(p.returncode, 0, p.stderr)
        ev = self.evidence()
        self.assertEqual(ev["head"], new)
        self.assertFalse(ev["dirty"])
        self.assertEqual(ev["verified_head"], old)
        self.assertIn(new[:7], p.stdout)
        self.assertIn(new[:12], (herd._dir(self.root, "t1") / "evidence.md").read_text())

    def test_verified_head_survives_a_refused_done(self):
        (self.root / "extra.txt").write_text("x")
        self.verify()
        old = self.sha()
        (herd._dir(self.root, "t1") / "pr").write_text("https://example.com/pr/1\n")
        self.commit("greet.txt")
        self.assertEqual(self.herd("done").returncode, 1)
        T.git(self.root, "add", "extra.txt")
        T.git(self.root, "commit", "-q", "-m", "rest")
        (herd._dir(self.root, "t1") / "pr").unlink()
        self.assertEqual(self.herd("done").returncode, 0)
        self.assertEqual(self.evidence()["verified_head"], old)
        self.assertEqual(self.evidence()["head"], self.sha())

    def test_partial_commit_with_prs_on_is_refused(self):
        (self.root / "extra.txt").write_text("x")
        self.verify()
        (herd._dir(self.root, "t1") / "pr").write_text("https://example.com/pr/1\n")
        self.commit("greet.txt")
        self.assertEqual(herd.problems(self.root, "t1"), [])
        p = self.herd("done")
        self.assertEqual(p.returncode, 1)
        self.assertIn("commit the work first", p.stderr)
        self.assertNotIn("(commit, `herd verify`", p.stderr)


class TestFallback(Fresh):
    def test_evidence_without_content_is_stale_after_a_commit(self):
        self.verify()
        path = herd._dir(self.root, "t1") / "evidence.json"
        ev = self.evidence()
        del ev["content"]
        path.write_text(json.dumps(ev))
        self.assertEqual(herd.problems(self.root, "t1"), [])
        self.commit()
        self.assertTrue(self.stale())

    def test_outside_git_a_task_edit_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            herd.init_task(root, "t1", "Add a greeting")
            (herd._dir(root, "t1") / "task.toml").write_text(ONE)
            (root / "greet.txt").write_text("hello")
            T.run_herd(root, "verify")
            self.assertIsNone(json.loads((herd._dir(root, "t1") / "evidence.json").read_text())["content"])
            self.assertFalse(any("stale" in p for p in herd.problems(root, "t1")))
            path = herd._dir(root, "t1") / "task.toml"
            path.write_text(path.read_text() + "\n# edited\n")
            self.assertTrue(any("stale" in p for p in herd.problems(root, "t1")))

    def test_verify_only_after_an_edit_leaves_the_gate_stale(self):
        self.verify()
        (self.root / "greet.txt").write_text("changed")
        before = (herd._dir(self.root, "t1") / "evidence.json").read_text()
        self.herd("verify", "--only", "C1")
        self.assertEqual((herd._dir(self.root, "t1") / "evidence.json").read_text(), before)
        self.assertTrue(self.stale())


class TestGitCalls(unittest.TestCase):
    """The freshness check reads git once for the status, and once more for the diff when HEAD moved."""

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
        for args in (("init", "-q"), ("config", "user.email", "t@example.com"), ("config", "user.name", "t")):
            T.git(self.root, *args)
        (self.root / "README.md").write_text("x")
        T.git(self.root, "add", "-A")
        T.git(self.root, "commit", "-q", "-m", "init")
        T.git(self.root, "switch", "-q", "-c", "herd/t1")
        self.herd("init", "t1", "Add a greeting")
        T.no_design(self.root)
        (self.root / ".herd/tasks/t1/task.toml").write_text(ONE)
        for a in herd.ATTACKS:
            herd.add_note(self.root, "t1", "tried", f"{a} attack", attack=a, check=T.OK, **T.PROGRAMS.get(a, {}))
        (self.root / "greet.txt").write_text("hello")
        self.herd("verify")

    def tearDown(self):
        self.tmp.cleanup()

    def herd(self, *args):
        self.log.write_text("") if self.log.exists() else None
        p = subprocess.run([sys.executable, HERD, *args], cwd=self.root, env=self.env, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertNotIn("Traceback", p.stderr)
        return p

    def calls(self, *args):
        p = self.herd(*args)
        return p, [c.split()[0] for c in self.log.read_text().splitlines()]

    def test_gate_after_a_commit_adds_only_the_diff(self):
        p, before = self.calls("gate")
        self.assertEqual(p.returncode, 0, p.stderr)
        T.git(self.root, "add", "greet.txt")
        T.git(self.root, "commit", "-q", "-m", "greet")
        p, after = self.calls("gate")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(after.count("status"), before.count("status"), (before, after))
        self.assertEqual(after.count("diff"), 1, after)

    def test_done_reads_git_status_once_for_freshness(self):
        T.git(self.root, "add", "greet.txt")
        T.git(self.root, "commit", "-q", "-m", "greet")
        p, calls = self.calls("done")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(calls.count("diff"), 1, calls)
        self.assertLessEqual(calls.count("status"), 2, calls)  # one for freshness, one for the work-outside-commit check


if __name__ == "__main__":
    unittest.main()
