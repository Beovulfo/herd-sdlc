"""Attacks on the one-status-call git state (issue #46): generated repositories, checked against plain git commands."""
import json
import os
import random
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import herd

NAMES = ["a.py", "dir sub/b file.txt", "unicöde.md", "x/y/z.py", "r.txt", "same1.txt", "same2.txt", "tab\tname.txt"]


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def make_repo(base, seed, sub="", edits=True):  # noqa: C901
    """A repository with committed files (under `sub`), then random edits: modify, delete, rename, add, stage, ignore,
    chmod, commit. Returns (project root, start commit)."""
    rnd = random.Random(seed)
    git(base, "init", "-q")
    git(base, "config", "user.email", "t@example.com")
    git(base, "config", "user.name", "t")
    root = Path(base) / sub
    root.mkdir(parents=True, exist_ok=True)
    (Path(base) / ".gitignore").write_text("*.log\n")
    for n in NAMES:
        (root / n).parent.mkdir(parents=True, exist_ok=True)
        (root / n).write_text("same" if n.startswith("same") else f"v1 {n}")
    git(base, "add", "-A")
    git(base, "commit", "-q", "-m", "init")
    start = git(base, "rev-parse", "HEAD").strip()
    for step in range(rnd.randint(1, 8) if edits else 0):
        pick = rnd.choice(NAMES)
        op = rnd.choice(["modify", "delete", "rename", "add", "log", "stage", "chmod", "commit", "undo"])
        p = root / pick
        if op == "modify" and p.exists():
            p.write_text(f"v{step + 2}")
        elif op == "delete" and p.exists():
            p.unlink()
        elif op == "rename" and p.exists():
            git(base, "mv", str(p), str(p) + ".moved")
        elif op == "add":
            (root / f"new{step}.txt").write_text("n")
        elif op == "log":
            (root / f"x{step}.log").write_text("ignored")
        elif op == "stage":
            git(base, "add", "-A")
        elif op == "chmod" and p.exists():
            p.chmod(0o755)
        elif op == "commit":
            git(base, "add", "-A")
            subprocess.run(["git", "commit", "-q", "-m", f"s{step}", "--allow-empty"], cwd=base, check=True, capture_output=True)
        elif op == "undo" and p.exists():
            p.write_text("same" if pick.startswith("same") else f"v1 {pick}")
    return root, start


def plain_changed(root, start):
    """Separate, simpler code: what changed since start, from plain git commands run in root."""
    names = git(root, "diff", "-z", "--name-only", "--relative", "--diff-filter=d", start).split("\0")
    names += git(root, "ls-files", "-z", "--others", "--exclude-standard").split("\0")
    return sorted({n for n in names if n and not n.startswith(".herd/")})


class Generated(unittest.TestCase):
    def check_seeds(self, sub):
        for seed in range(25):
            with tempfile.TemporaryDirectory() as base:
                root, start = make_repo(base, seed, sub)
                with self.subTest(seed=seed, sub=sub):
                    snap = herd._read_status(root)
                    self.assertEqual(herd.changed_since(root, start, snap), plain_changed(root, start))
                    self.assertEqual(snap["oid"], git(root, "rev-parse", "HEAD").strip())
                    self.assertEqual(snap["branch"], git(root, "rev-parse", "--abbrev-ref", "HEAD").strip())
                    self.assertEqual(bool(snap["entries"]), bool(git(root, "status", "--porcelain", "--", ".").strip()))


class TestRecount(Generated):
    def test_changed_files_dirty_flag_head_and_branch_match_plain_git(self):
        self.check_seeds("")

    def test_the_same_in_a_project_subfolder(self):
        self.check_seeds("pkg")


class TestCollision(unittest.TestCase):
    def test_two_files_with_equal_content_each_count(self):
        with tempfile.TemporaryDirectory() as base:
            root, start = make_repo(base, 0)
            (root / "same1.txt").write_text("same")
            (root / "same2.txt").write_text("same")
            before = (herd.fingerprint(root), herd.content_id(root, start))
            (root / "same1.txt").write_text("changed")
            self.assertNotEqual(herd.fingerprint(root), before[0])
            self.assertNotEqual(herd.content_id(root, start), before[1])
            (root / "same1.txt").write_text("same")
            (root / "same2.txt").write_text("changed")
            self.assertNotEqual(herd.content_id(root, start), before[1])

    def test_staged_and_unstaged_edits_of_one_path_and_a_rename_are_all_seen(self):
        with tempfile.TemporaryDirectory() as base:
            root, start = make_repo(base, 0, edits=False)
            (root / "a.py").write_text("staged")
            git(root, "add", "a.py")
            (root / "a.py").write_text("unstaged")
            git(root, "mv", "r.txt", "renamed.txt")
            snap = herd._read_status(root)
            self.assertEqual(herd.changed_since(root, start, snap), ["a.py", "renamed.txt"])
            self.assertIn("r.txt", herd._since(root, start, snap))  # the old name is a change for the content id

    def test_equal_edits_in_two_directories_do_not_hide_each_other(self):
        with tempfile.TemporaryDirectory() as base:
            root, start = make_repo(base, 0)
            (root / "dir sub/b file.txt").write_text("e")
            one = herd.content_id(root, start)
            (root / "x/y/z.py").write_text("e")
            self.assertNotEqual(herd.content_id(root, start), one)


class TestBadInput(unittest.TestCase):
    def test_no_repository_gives_no_state_and_no_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(herd._read_status(d))
            self.assertIsNone(herd.changed_since(d, "abc"))
            self.assertIsNone(herd.content_id(d))
            self.assertEqual(herd.fingerprint(d), herd.fingerprint(d))

    def test_a_start_commit_that_does_not_exist_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as base:
            root, start = make_repo(base, 1)
            snap = herd._read_status(root)
            self.assertIsNone(herd.changed_since(root, "0" * 40, snap))
            self.assertTrue(herd.content_id(root, "0" * 40, snap))
            self.assertTrue(herd.content_id(root, None, snap))

    def test_a_repository_with_no_commit_still_has_state(self):
        with tempfile.TemporaryDirectory() as base:
            git(base, "init", "-q")
            (Path(base) / "f.txt").write_text("x")
            snap = herd._read_status(base)
            self.assertEqual((snap["oid"], [e[4] for e in snap["entries"]]), (None, ["f.txt"]))
            self.assertIsNone(herd.changed_since(base, None, snap))
            self.assertTrue(herd.content_id(base, None, snap))

    def test_verify_with_a_bogus_start_commit_ends_with_evidence(self):
        with tempfile.TemporaryDirectory() as base:
            root, start = make_repo(base, 2)
            herd.init_task(root, "t1", "goal")
            d = root / ".herd/tasks/t1"
            d.joinpath("task.toml").write_text('goal = "g"\n[[criteria]]\nid = "C1"\ntext = "t"\nsource = "agent-proposed"\ncheck = "test -d ."\n')
            d.joinpath("start.json").write_text(json.dumps({"head": "f" * 40, "risk": "low"}))
            ev = herd.verify(root, "t1")
            self.assertEqual(ev["head"], git(root, "rev-parse", "HEAD").strip())
            self.assertTrue(ev["content"])


class TestOneBadPart(unittest.TestCase):
    def test_a_broken_link_an_unreadable_file_and_a_deleted_file_do_not_stop_the_state(self):
        with tempfile.TemporaryDirectory() as base:
            root, start = make_repo(base, 3)
            os.symlink("nowhere", root / "dangling")
            (root / "locked.txt").write_text("secret")
            (root / "locked.txt").chmod(0)
            (root / "a.py").unlink(missing_ok=True)
            try:
                snap = herd._read_status(root)
                self.assertTrue(herd.fingerprint(root, snap))
                self.assertTrue(herd.content_id(root, start, snap))
                got = herd.changed_since(root, start, snap)
                self.assertIn("dangling", got)
                self.assertNotIn("a.py", got)
            finally:
                (root / "locked.txt").chmod(0o644)


class TestRefusal(Generated):
    def test_changes_cannot_be_told_exactly_when_the_start_commit_is_missing_or_not_a_commit(self):
        for seed in range(10):
            with tempfile.TemporaryDirectory() as base:
                root, start = make_repo(base, seed)
                for head in (start, "0" * 40, None, "not-a-sha"):
                    ok = bool(head) and subprocess.run(["git", "rev-parse", "--verify", "-q", f"{head}^{{commit}}"],
                                                       cwd=root, capture_output=True).returncode == 0
                    with self.subTest(seed=seed, head=head):
                        self.assertEqual(herd.changed_since(root, head) is not None, ok)

    def test_ignored_files_are_never_a_change(self):
        with tempfile.TemporaryDirectory() as base:
            root, start = make_repo(base, 4)
            (root / "build.log").write_text("x")
            self.assertNotIn("build.log", herd.changed_since(root, start))
            self.assertNotIn("build.log", [e[4] for e in herd._read_status(root)["entries"]])


if __name__ == "__main__":
    unittest.main()
