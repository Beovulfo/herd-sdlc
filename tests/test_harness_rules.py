"""Rules the run skill used to state only in text, now enforced or recorded by the CLI (0.4.0)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import herd

OK = "python3 -c \"import json\""  # an attack command that passes and is not vacuous
REQUEST = "Add f() to app.py. It must return 1 for any call."
APP_CHECK = "python3 -c \"import app; assert app.f() == 1\""
TASK = f'''goal = "Add f() to app.py"
known_limits = "Only the return value is checked."

[[criteria]]
id = "C1"
text = "It must return 1 for any call"
source = "human"
coverage = "Varies nothing: calls f() once; proves the return value, not repeated calls"
check = {json.dumps(APP_CHECK)}

[[criteria]]
id = "C2"
text = "Given the module, when imported, then it defines f"
source = "agent-proposed"
check = "python3 -c \\"import app; app.f\\""
'''


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "t")
        (self.root / "README.md").write_text("x")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "init")

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        return subprocess.run([sys.executable, str(Path(herd.__file__)), *args], cwd=self.root,
                              capture_output=True, text=True)

    def start(self, text=TASK, goal="Add f() to app.py"):
        herd.init_task(self.root, "t1", goal, request=REQUEST)
        (self.root / ".herd/tasks/t1/task.toml").write_text(text)

    def red_then_build(self):
        """Red first done right: a test file, the failing verify, then the code."""
        (self.root / "tests").mkdir(exist_ok=True)
        (self.root / "tests/test_app.py").write_text("import app\n")
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["summary"]["failing"], 2)
        (self.root / "app.py").write_text("def f():\n    return 1\n")

    def attacks_and_review(self):
        for a in herd.ATTACKS:
            herd.add_note(self.root, "t1", "tried", f"{a} attack", attack=a, check=OK)
        herd.add_review(self.root, "t1", by="a fresh subagent", text="no Blocker or Major")


class TestRedFirst(Base):
    def test_code_before_the_first_verify_is_flagged_and_needs_a_reason(self):
        self.start()
        (self.root / "app.py").write_text("def f():\n    return 1\n")  # code before any check ran
        (self.root / "tests").mkdir()
        (self.root / "tests/test_app.py").write_text("import app\n")  # tests do not count
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["red"]["code_before"], ["app.py"])
        self.assertIn("Red first not proven: app.py changed before the first verify", herd.report(ev))
        self.attacks_and_review()
        herd.verify(self.root, "t1")
        self.assertIn("red first not proven", " ".join(herd.problems(self.root, "t1")))
        self.assertEqual(self.cli("note", "--late-red", "wrote the code to explore the API first").returncode, 0)
        self.assertEqual(herd.problems(self.root, "t1"), [])
        self.assertIn("wrote the code to explore the API first", herd.report(herd.verify(self.root, "t1")))

    def test_checks_before_code_is_clean(self):
        self.start()
        self.red_then_build()
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["red"]["code_before"], [])
        self.assertNotIn("Red first not proven", herd.report(ev))

    def test_docs_and_herd_files_do_not_count_as_code(self):
        self.start()
        (self.root / "README.md").write_text("plan")
        (self.root / "docs").mkdir()
        (self.root / "docs/notes.md").write_text("plan")
        self.assertEqual(herd.verify(self.root, "t1")["red"]["code_before"], [])


class TestRiskAndReview(Base):
    def test_risk_is_stored_at_init_and_raised_by_changed_files(self):
        self.start()
        start = json.loads((self.root / ".herd/tasks/t1/start.json").read_text())
        self.assertEqual(start["risk"], "medium")
        self.assertTrue(start["head"])
        self.red_then_build()
        (self.root / "migrations").mkdir()
        (self.root / "migrations/0001_add.py").write_text("x = 1\n")
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["risk"]["effective"], "high")
        self.assertIn("migrations/**", ev["risk"]["rules"])
        self.assertIn("Risk: high", herd.report(ev))

    def test_done_needs_a_review_or_a_reason_to_skip(self):
        self.start()
        self.red_then_build()
        for a in herd.ATTACKS:
            herd.add_note(self.root, "t1", "tried", a, attack=a, check=OK)
        herd.verify(self.root, "t1")
        self.assertIn("review", " ".join(herd.problems(self.root, "t1")))
        self.assertEqual(self.cli("review", "a fresh subagent").returncode, 1)  # who reviewed, or --skipped
        p = self.cli("review", "--skipped", "no subagent can be spawned here")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(herd.problems(self.root, "t1"), [])
        text = herd.report(herd.verify(self.root, "t1"))
        self.assertIn("Review: skipped: no subagent can be spawned here", text)
        self.assertIn("unreviewed", herd.pr_body(self.root, "t1"))

    def test_review_by_a_named_reviewer_is_recorded(self):
        self.start()
        self.red_then_build()
        self.attacks_and_review()
        ev = herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])
        self.assertIn("Review: a fresh subagent: no Blocker or Major", herd.report(ev))

    def test_quick_route_needs_no_review(self):
        herd.init_task(self.root, "q1", "Fix typo", quick_check=APP_CHECK)
        (self.root / "app.py").write_text("def f():\n    return 1\n")
        herd.verify(self.root, "q1")
        self.assertEqual([p for p in herd.problems(self.root, "q1") if "review" in p], [])


class TestFrozenHumanCriteria(Base):
    def test_a_human_criterion_changed_or_removed_after_the_first_verify_blocks_done(self):
        self.start()
        self.red_then_build()
        self.attacks_and_review()
        narrowed = TASK.replace('text = "It must return 1 for any call"', 'text = "It must return 1 for one call"')
        (self.root / ".herd/tasks/t1/task.toml").write_text(narrowed)
        herd.verify(self.root, "t1")
        self.assertIn("C1 changed after the first verify", " ".join(herd.problems(self.root, "t1")))
        removed = TASK.split("[[criteria]]")[0] + "[[criteria]]" + TASK.split("[[criteria]]")[2]
        (self.root / ".herd/tasks/t1/task.toml").write_text(removed)
        herd.verify(self.root, "t1")
        self.assertIn("C1 was removed after the first verify", " ".join(herd.problems(self.root, "t1")))
        (self.root / ".herd/tasks/t1/task.toml").write_text(TASK)  # restored as the human wrote it
        herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])

    def test_a_changed_check_is_reported_not_blocked(self):
        self.start()
        self.red_then_build()
        self.attacks_and_review()
        changed = TASK.replace("app.f\\\"", "app.f()\\\"")
        self.assertNotEqual(changed, TASK)
        (self.root / ".herd/tasks/t1/task.toml").write_text(changed)
        ev = herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])
        self.assertIn("C2: check changed after the first verify", herd.report(ev))
        self.assertIn("C2: check changed after the first verify", herd.pr_body(self.root, "t1"))


class TestFinalReport(Base):
    def test_done_prints_the_final_report_from_evidence_and_notes(self):
        self.start()
        self.red_then_build()
        herd.add_note(self.root, "t1", "found", "f() returned None for no arguments")
        herd.add_note(self.root, "t1", "fixed", "f() now returns 1")
        self.assertEqual(self.cli("note", "--decision", "f takes no arguments; the request named none; "
                                  "add parameters in app.py").returncode, 0)
        self.attacks_and_review()
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "add f")
        herd.verify(self.root, "t1")
        p = self.cli("done")
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = p.stdout.splitlines()
        for start in ("Done:", "Proven:", "Not proven:", "Caveats:", "Decisions:", "Limits:", "Review:"):
            self.assertEqual(sum(line.startswith(start) for line in lines), 1, (start, p.stdout))
        out = p.stdout
        self.assertIn("Proven: 2 of 2 criteria", out)
        self.assertIn("f takes no arguments; the request named none; add parameters in app.py", out)
        self.assertIn("f() returned None for no arguments", out)
        self.assertIn("Limits: Only the return value is checked.", out)
        self.assertIn("Review: a fresh subagent: no Blocker or Major", out)
        self.assertIn("Not proven: nothing open", out)
        self.assertIn(".herd/tasks/t1/evidence.md", out)


class TestWarningsAndEscalation(Base):
    def test_verify_stores_the_check_warnings_every_time(self):
        self.start(TASK.replace('coverage = "Varies nothing: calls f() once; proves the return value, not repeated calls"\n', ""))
        ev = herd.verify(self.root, "t1")
        self.assertTrue(any("C1" in w for w in ev["warnings"]), ev["warnings"])
        self.assertIn("Warnings from herd check:", herd.report(ev))
        self.assertIn("herd check warning", self.cli("verify").stdout)  # one summary line

    def test_three_failures_in_a_row_say_escalate(self):
        self.start()
        for i in range(3):
            out = self.cli("verify").stdout
        self.assertIn("C1 failed 3 times in a row: ask the human one question", out)
        (self.root / "app.py").write_text("def f():\n    return 1\n")
        self.assertNotIn("in a row", self.cli("verify").stdout)
        (self.root / "app.py").write_text("def f():\n    return 2\n")
        self.assertNotIn("in a row", self.cli("verify").stdout)  # the count starts again after a pass


class TestCommitBeforeDone(Base):
    def ready(self):
        self.start()
        self.red_then_build()
        self.attacks_and_review()
        herd.verify(self.root, "t1")

    def test_uncommitted_work_is_refused_when_prs_are_on(self):
        (self.root / "herd.toml").write_text("[pr]\nopen = true\n")
        git(self.root, "add", "herd.toml")
        git(self.root, "commit", "-qm", "config")
        self.ready()
        p = self.cli("done")
        self.assertEqual(p.returncode, 1)
        self.assertIn("commit", p.stderr)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "add f")
        herd.verify(self.root, "t1")
        self.assertEqual(self.cli("done").returncode, 0)

    def test_uncommitted_work_only_warns_when_prs_are_off(self):
        self.ready()
        p = self.cli("done")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("uncommitted", p.stderr)


if __name__ == "__main__":
    unittest.main()
