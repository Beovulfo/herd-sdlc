"""Defaults: each task in its own worktree and a pull request, unless herd.toml turns them off."""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import herd
from tests import test_herd_cli as cli

REPO = Path(__file__).resolve().parent.parent
HERD = [sys.executable, str(Path(herd.__file__))]


def run(cwd, *args):
    return subprocess.run([*HERD, *args], cwd=cwd, capture_output=True, text=True)


class TestWorktreeDefault(cli.Base):
    def toml(self, text):
        (self.root / "herd.toml").write_text(text)
        cli.git(self.root, "add", "herd.toml")
        cli.git(self.root, "commit", "-q", "-m", "config")

    def tearDown(self):
        subprocess.run(["git", "worktree", "prune"], cwd=self.root, capture_output=True)
        super().tearDown()

    def refused(self, *args):
        p = run(self.root, *args)
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertIn("--worktree", p.stderr)
        self.assertIn("required = false", p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        self.assertFalse((self.root / ".herd/tasks/t1").exists())

    def test_plain_and_quick_init_need_a_worktree_by_default(self):
        self.refused("init", "t1", "Write out.txt")
        self.refused("init", "t1", "Write out.txt", "--quick", "test -f out.txt")

    def test_broken_herd_toml_keeps_the_default(self):
        self.toml("[[[ not toml")
        self.refused("init", "t1", "Write out.txt")

    def test_worktree_init_works_by_default(self):
        p = run(self.root, "init", "t1", "Write out.txt", "--worktree")
        self.assertEqual(p.returncode, 0, p.stderr)
        wt = self.root / ".claude/worktrees/herd-t1"
        self.assertTrue((wt / ".herd/tasks/t1/task.toml").exists())
        self.assertEqual(run(wt, "status").returncode, 0)  # a plain herd command in the worktree is not refused

    def test_required_false_turns_it_off(self):
        self.toml("[worktree]\nrequired = false\n")
        p = run(self.root, "init", "t1", "Write out.txt")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse((self.root / ".claude").exists())

    def test_a_setting_that_is_not_true_or_false_is_refused(self):
        for text in ('[worktree]\nrequired = "false"\n', "[worktree]\nrequired = 0\n", '[pr]\nopen = "no"\n'):
            with self.subTest(text=text):
                self.toml(text)
                p = run(self.root, "init", "t1", "Write out.txt", "--worktree")
                self.assertEqual(p.returncode, 1, p.stdout)
                self.assertIn("true or false", p.stderr)
                self.assertNotIn("Traceback", p.stderr)

    def test_a_broken_table_elsewhere_does_not_hide_the_opt_out(self):
        self.toml("[floor]\nhigh = 3\n[worktree]\nrequired = false\n")
        p = run(self.root, "init", "t1", "Write out.txt")
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_opt_out_still_allows_a_worktree(self):
        self.toml("[worktree]\nrequired = false\n")
        p = run(self.root, "init", "t1", "Write out.txt", "--worktree")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue((self.root / ".claude/worktrees/herd-t1/.herd/tasks/t1").exists())

    def test_explicit_true_still_refuses(self):
        self.toml("[worktree]\nrequired = true\n")
        self.refused("init", "t1", "Write out.txt")


class TestWorktreeDefaultWithoutGit(unittest.TestCase):
    """A worktree needs git and a commit; without them the default steps aside and says so."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def plain_init_works_with_a_note(self):
        p = run(self.root, "init", "t1", "Write out.txt")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue((self.root / ".herd/tasks/t1/task.toml").exists())
        self.assertRegex(p.stderr, r"no worktree: .*(not a git repository|no commit)")

    def test_outside_git(self):
        self.plain_init_works_with_a_note()

    def test_repository_with_no_commit(self):
        cli.git(self.root, "init", "-q")
        self.plain_init_works_with_a_note()

    def test_explicit_true_outside_git_refuses(self):
        (self.root / "herd.toml").write_text("[worktree]\nrequired = true\n")
        p = run(self.root, "init", "t1", "Write out.txt")
        self.assertEqual(p.returncode, 1)
        self.assertIn("--worktree", p.stderr)


class TestSkillsAndDocs(unittest.TestCase):
    def test_skills_follow_the_defaults(self):
        run_skill = (REPO / "skills/run/SKILL.md").read_text()
        intake = re.search(r"1\. \*\*Intake\.\*\*(.*)", run_skill).group(1)
        self.assertIn("--worktree", intake)
        self.assertIn("required = false", intake)
        finish = re.search(r"10\. \*\*Finish\.\*\*(.*)", run_skill).group(1)
        self.assertIn("open = false", finish)
        quick = (REPO / "skills/run/quick.md").read_text()
        self.assertIn("--worktree", quick)
        pr = (REPO / "skills/run/pr.md").read_text()
        self.assertIn("open = false", pr)
        self.assertIn("never block", pr)
        self.assertNotIn("opt-in", pr)

    def test_readme_settings_table_and_badges(self):
        readme = (REPO / "README.md").read_text()
        table = readme.split("### Project settings", 1)[1].split("\n\n**", 1)[0]
        rows = {r.split("|")[1].strip(): r.split("|")[2].strip() for r in table.splitlines()
                if r.startswith("| `")}
        self.assertEqual(rows["`[worktree] required = false`"], "on")
        self.assertEqual(rows["`[pr] open = false`"], "on")
        floor = [v for k, v in rows.items() if k.startswith("`[floor]`")][0]
        self.assertIn("`api/**` is medium", floor)
        badges = readme.split("<p align=\"center\">", 3)[2].split("</p>", 1)[0]
        for name in ("Codex", "open%20models"):
            link = re.search(rf'<a href="([^"]+)"><img alt="[^"]*" src="https://img\.shields\.io/badge/[^"]*{name}', badges)
            self.assertTrue(link, name)
            self.assertEqual(link.group(1), "#other-agents")


if __name__ == "__main__":
    unittest.main()
