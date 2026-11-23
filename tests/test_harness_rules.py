"""Rules the run skill used to state only in text, now enforced or recorded by the CLI (0.4.0)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import herd
from tests.test_herd_cli import late_review

OK = "python3 -c \"import json\""  # an attack command that passes and is not vacuous
REQUEST = "Add f() to app.py. It must return 1 for any call."
APP_CHECK = "python3 -c \"import app; assert app.f() == 1\""
TASK = f'''goal = "Add f() to app.py"
known_limits = "Repeated calls are not timed."

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
        git(self.root, "config", "core.excludesFile", "/dev/null")  # like CI: no global gitignore hides __pycache__
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
        late_review(self.root)


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


class TestOwnStateFiles(Base):
    def test_corrupt_or_old_state_files_never_stop_verify(self):
        self.start()
        self.red_then_build()
        d = self.root / ".herd/tasks/t1"
        (d / "red.json").write_text("{bad")
        self.assertEqual(self.cli("verify").returncode, 0)  # it still runs; problems() then blocks
        for name in ("fails.json", "start.json"):
            (d / name).write_text("{bad")
        (d / "red.json").write_text(json.dumps({"at": "2026-11-23T10:00:00Z", "failed": 2, "total": 2}))  # 0.3.x shape
        p = self.cli("verify")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        ev = json.loads((d / "evidence.json").read_text())
        self.assertIsNone(ev["red"]["code_before"])
        self.assertEqual(ev["risk"]["effective"], "medium")
        self.assertEqual(ev["human_changed"], [])

    def test_a_broken_herd_toml_makes_the_risk_high(self):
        self.start()
        self.red_then_build()
        (self.root / "herd.toml").write_text('floor = "oops')
        self.assertEqual(herd.verify(self.root, "t1")["risk"]["effective"], "high")


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

    def test_the_latest_of_several_reviews_is_the_one_reported(self):
        self.start()
        self.red_then_build()
        herd.add_review(self.root, "t1", skipped=True, text="no reviewer yet")
        herd.add_review(self.root, "t1", by="a fresh subagent", text="one Major, fixed")
        self.assertIn("Review: a fresh subagent: one Major, fixed", herd.report(herd.verify(self.root, "t1")))
        self.assertNotIn("unreviewed", herd.pr_body(self.root, "t1"))
        herd.add_review(self.root, "t1", skipped=True, text="the reviewer crashed on the second round")
        self.assertIn("unreviewed: the reviewer crashed", herd.pr_body(self.root, "t1"))

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
        self.assertIn("Limits: Repeated calls are not timed.", out)
        self.assertIn("Review: a fresh subagent: no Blocker or Major", out)
        self.assertIn("Not proven: nothing open", out)
        self.assertIn(".herd/tasks/t1/evidence.md", out)


    def test_final_report_numbers_match_an_independent_recount(self):
        self.start(TASK + '\n[[criteria]]\nid = "C3"\ntext = "Looks right"\nsource = "agent-proposed"\ncheck = ""\n')
        self.red_then_build()
        for i in range(3):
            herd.add_note(self.root, "t1", "found", f"finding {i}")
        herd.add_note(self.root, "t1", "fixed", "fix 0")
        self.attacks_and_review()
        herd.verify(self.root, "t1")
        ev = json.loads((self.root / ".herd/tasks/t1/evidence.json").read_text())
        notes = [json.loads(x) for x in (self.root / ".herd/tasks/t1/notes.jsonl").read_text().splitlines()]
        lines = herd.final_report(self.root, "t1", ev, notes)
        task = herd.load_task(self.root, "t1")  # recount by running each check again, apart from Herd
        proven = sum(bool(c["check"]) and subprocess.run(c["check"], shell=True, cwd=self.root,
                                                         capture_output=True).returncode == 0 for c in task["criteria"])
        self.assertEqual(proven, 2)
        self.assertEqual(lines[1].split(";")[0], f"Proven: {proven} of {len(ev['results'])} criteria")
        self.assertEqual(lines[3].count("found"), sum(n["kind"] == "found" for n in notes))
        self.assertEqual(lines[3].count("fixed"), sum(n["kind"] == "fixed" for n in notes))
        self.assertIn("C3 unchecked", lines[2])


class TestWarningsAndEscalation(Base):
    def test_verify_stores_the_check_warnings_every_time(self):
        self.start(TASK.replace('coverage = "Varies nothing: calls f() once; proves the return value, not repeated calls"\n', ""))
        ev = herd.verify(self.root, "t1")
        self.assertTrue(any("C1" in w for w in ev["warnings"]), ev["warnings"])
        self.assertIn("Warnings from herd check:", herd.report(ev))
        self.assertIn("herd check warning", self.cli("verify").stdout)  # one summary line

    def test_three_failures_in_a_row_say_escalate(self):
        self.start()
        for i in range(4):  # the first is the red run, which is not a failed attempt
            out = self.cli("verify").stdout
        self.assertIn("C1 failed 3 times in a row: ask the human one question", out)
        (self.root / "app.py").write_text("def f():\n    return 1\n")
        self.assertNotIn("in a row", self.cli("verify").stdout)
        (self.root / "app.py").write_text("def f():\n    return 1 + 1\n")  # another size, so no stale .pyc
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



class TestReviewFindings(Base):
    """The holes a fresh-context review found in the first version of these rules."""

    def test_files_dirty_before_init_are_not_the_agents_code(self):
        (self.root / "app.py").write_text("x = 1\n")  # the human's uncommitted work
        self.start()
        self.assertEqual(herd.verify(self.root, "t1")["red"]["code_before"], [])

    def test_config_dotfiles_and_extensionless_files_are_not_code(self):
        for f in ("pyproject.toml", "package.json", ".gitignore", "Makefile", "tests/test_x.py", ".herd/x.py",
                  "__pycache__/app.cpython-312.pyc", "node_modules/x/index.js"):
            self.assertFalse(herd.is_code(f), f)
        for f in ("src/app.py", "cmd/dist/main.go", "src/mypkg/build/core.py", "src/target/x86.rs"):
            self.assertTrue(herd.is_code(f), f)  # build/, dist/, target/ can hold source

    def test_code_moved_aside_for_the_first_verify_is_flagged(self):
        self.start()
        (self.root / "app.py").write_text("def f():\n    return 1\n")
        old = herd.datetime.now().timestamp() - 3600
        os.utime(self.root / "app.py", (old, old))
        (self.root / "app.py").rename(self.root / "aside.txt")  # hidden from the red run
        herd.verify(self.root, "t1")
        (self.root / "aside.txt").rename(self.root / "app.py")  # mv keeps the old mtime
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["red"]["code_hidden"], ["app.py"])
        self.assertIn("red first not proven", " ".join(herd.problems(self.root, "t1")))

    def test_a_review_before_all_checks_pass_does_not_count(self):
        self.start()
        self.red_then_build()
        for a in herd.ATTACKS:
            herd.add_note(self.root, "t1", "tried", f"{a} attack", attack=a, check=OK)
        herd.add_review(self.root, "t1", by="a fresh subagent", text="looked at the plan")
        herd.verify(self.root, "t1")  # all checks pass for the first time, after the review
        self.assertIn("recorded before all checks first passed", " ".join(herd.problems(self.root, "t1")))
        herd.add_review(self.root, "t1", by="a fresh subagent", text="no Blocker or Major")
        self.assertEqual(herd.problems(self.root, "t1"), [])

    def test_a_review_at_a_lower_risk_does_not_count_once_the_risk_rises(self):
        self.start()
        self.red_then_build()
        for a in herd.ATTACKS:
            herd.add_note(self.root, "t1", "tried", f"{a} attack", attack=a, check=OK)
        herd.verify(self.root, "t1")
        herd.add_review(self.root, "t1", by="a fresh subagent", text="no Blocker or Major")
        self.assertEqual(herd.problems(self.root, "t1"), [])
        (self.root / "auth").mkdir()
        (self.root / "auth/session.py").write_text("x = 1\n")  # a high-risk path
        herd.verify(self.root, "t1")
        self.assertIn("the risk rose to high after the review", " ".join(herd.problems(self.root, "t1")))

    def test_code_changed_after_the_review_is_reported(self):
        self.start()
        self.red_then_build()
        herd.verify(self.root, "t1")
        herd.add_review(self.root, "t1", by="a fresh subagent", text="no Blocker or Major")
        (self.root / "app.py").write_text("def f():\n    return 1  # tweak\n")
        self.assertIn("The code changed after the review", herd.report(herd.verify(self.root, "t1")))

    def test_the_humans_own_change_is_accepted_with_their_words_and_shown(self):
        self.start()
        self.red_then_build()
        self.attacks_and_review()
        narrowed = TASK.replace('text = "It must return 1 for any call"', 'text = "It must return 1 for one call"')
        (self.root / ".herd/tasks/t1/task.toml").write_text(narrowed)
        herd.verify(self.root, "t1")
        self.assertIn("--human-change", " ".join(herd.problems(self.root, "t1")))
        self.assertEqual(self.cli("note", "--human-change", "C1: the human said: It must return 1 for one call").returncode, 0)
        ev = herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])
        self.assertIn("the human said: It must return 1 for one call", herd.report(ev))
        self.assertIn("the human said: It must return 1 for one call", herd.pr_body(self.root, "t1"))

    def test_human_criteria_are_frozen_even_before_any_check_runs(self):
        self.start(TASK.replace(f"check = {json.dumps(APP_CHECK)}", 'check = ""'))
        herd.verify(self.root, "t1")  # nothing runnable yet, so no red run, but the human's words are frozen
        self.assertTrue((self.root / ".herd/tasks/t1/frozen.json").exists())
        narrowed = TASK.replace('text = "It must return 1 for any call"', 'text = "It must return 1 for one call"')
        (self.root / ".herd/tasks/t1/task.toml").write_text(narrowed)
        herd.verify(self.root, "t1")
        self.assertIn("C1 changed after the first verify", " ".join(herd.problems(self.root, "t1")))

    def test_an_unreadable_red_file_blocks_instead_of_switching_the_rules_off(self):
        self.start()
        self.red_then_build()
        self.attacks_and_review()
        (self.root / ".herd/tasks/t1/red.json").write_text("{broken")
        ev = herd.verify(self.root, "t1")
        self.assertTrue(ev["red_unreadable"])
        self.assertIn("red.json in", " ".join(herd.problems(self.root, "t1")))

    def test_the_red_run_does_not_count_toward_escalation(self):
        self.start()
        for _ in range(3):
            out = self.cli("verify").stdout
        self.assertNotIn("in a row", out)  # the red run plus two failed attempts


class TestSecondReview(Base):
    """The holes a second fresh-context review found."""

    def ready(self, text=TASK):
        self.start(text)
        self.red_then_build()
        self.attacks_and_review()
        herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])

    def test_deleting_start_json_blocks(self):
        self.start()
        (self.root / ".herd/tasks/t1/start.json").unlink()
        (self.root / "app.py").write_text("def f():\n    return 1\n")
        self.attacks_and_review()
        herd.verify(self.root, "t1")
        self.assertIn("start.json", " ".join(herd.problems(self.root, "t1")))

    def test_deleting_frozen_json_does_not_refreeze_an_edited_criterion(self):
        self.ready()
        narrowed = TASK.replace('text = "It must return 1 for any call"', 'text = "It must return 1 for one call"')
        (self.root / ".herd/tasks/t1/task.toml").write_text(narrowed)
        (self.root / ".herd/tasks/t1/frozen.json").unlink()
        herd.verify(self.root, "t1")
        self.assertFalse((self.root / ".herd/tasks/t1/frozen.json").exists())
        self.assertIn("frozen.json", " ".join(herd.problems(self.root, "t1")))

    def test_a_criterion_the_human_dropped_can_be_closed(self):
        self.ready()
        removed = TASK.split("[[criteria]]")[0] + "[[criteria]]" + TASK.split("[[criteria]]")[2]
        (self.root / ".herd/tasks/t1/task.toml").write_text(removed)
        herd.verify(self.root, "t1")
        self.assertIn("C1 was removed", " ".join(herd.problems(self.root, "t1")))
        herd.add_note(self.root, "t1", "human-change", "C1: drop it, said the human")
        herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])

    def test_a_weakened_check_on_a_human_criterion_blocks(self):
        self.ready()
        weak = TASK.replace(json.dumps(APP_CHECK), json.dumps("python3 -c \"import app; app.f()\""))
        self.assertNotEqual(weak, TASK)
        (self.root / ".herd/tasks/t1/task.toml").write_text(weak)
        herd.verify(self.root, "t1")
        self.assertIn("the check of human criterion C1 changed", " ".join(herd.problems(self.root, "t1")))
        herd.add_note(self.root, "t1", "human-change", "C1: It must return 1 for any call; any call is fine")
        herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])

    def test_a_human_change_note_must_quote_the_new_wording(self):
        self.ready()
        herd.add_note(self.root, "t1", "human-change", "C1: whatever")
        narrowed = TASK.replace('text = "It must return 1 for any call"', 'text = "It must return 1 for one call"')
        (self.root / ".herd/tasks/t1/task.toml").write_text(narrowed)
        herd.verify(self.root, "t1")
        self.assertIn("C1 changed", " ".join(herd.problems(self.root, "t1")))

    def test_code_stashed_for_the_red_run_is_flagged(self):
        git(self.root, "checkout", "-q", "-b", "herd/t1")
        self.start()
        (self.root / "app.py").write_text("def f():\n    return 1\n")
        git(self.root, "stash", "push", "-q", "-u", "--", "app.py")
        herd.verify(self.root, "t1")
        git(self.root, "stash", "pop", "-q")
        self.attacks_and_review()
        herd.verify(self.root, "t1")
        self.assertIn("a git stash was made", " ".join(herd.problems(self.root, "t1")))

    def test_an_agent_edit_to_a_file_dirty_at_init_counts(self):
        (self.root / "app.py").write_text("x = 1\n")
        self.start()
        (self.root / "app.py").write_text("def f():\n    return 1\n")
        self.assertEqual(herd.verify(self.root, "t1")["red"]["code_before"], ["app.py"])

    def test_an_executable_script_without_an_extension_is_code(self):
        (self.root / "bin").mkdir()
        (self.root / "bin/deploy").write_text("#!/bin/sh\necho hi\n")
        self.assertTrue(herd.is_code("bin/deploy", self.root))
        self.assertFalse(herd.is_code("Makefile", self.root))

    def test_at_high_risk_a_review_counts_only_for_the_code_it_saw(self):
        (self.root / "auth").mkdir()
        self.start()
        self.red_then_build()
        (self.root / "auth/session.py").write_text("x = 1\n")
        for a in herd.ATTACKS:
            herd.add_note(self.root, "t1", "tried", f"{a} attack", attack=a, check=OK)
        herd.verify(self.root, "t1")
        herd.add_review(self.root, "t1", by="a fresh subagent", text="no Blocker or Major")
        self.assertEqual(herd.problems(self.root, "t1"), [])
        (self.root / "auth/session.py").write_text("x = 2\n")
        herd.verify(self.root, "t1")
        self.assertIn("the code changed after the review", " ".join(herd.problems(self.root, "t1")))

    def test_a_task_verified_by_an_older_herd_is_not_blocked_after_the_upgrade(self):
        self.start()
        d = self.root / ".herd/tasks/t1"
        (d / "start.json").unlink()  # as 0.3.x left it: no start.json, no frozen.json, evidence without risk
        (d / "evidence.json").write_text(json.dumps({"task": "t1", "results": []}))
        (self.root / "app.py").write_text("def f():\n    return 1\n")
        self.attacks_and_review()
        herd.verify(self.root, "t1")
        self.assertIn("start.json is missing", " ".join(herd.problems(self.root, "t1")))  # say why, then go on
        herd.add_note(self.root, "t1", "late-red", "the task started with Herd 0.3.2")
        ev = herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])
        self.assertIn("Red first not checked: the task started before Herd 0.4.0", herd.report(ev))
        narrowed = TASK.replace('text = "It must return 1 for any call"', 'text = "It must return 1 for one call"')
        (d / "task.toml").write_text(narrowed)
        herd.verify(self.root, "t1")
        self.assertIn("C1 changed", " ".join(herd.problems(self.root, "t1")))  # frozen from the upgrade on

    def test_the_gate_reason_says_to_escalate(self):
        self.start()
        for _ in range(4):
            herd.verify(self.root, "t1")
        self.assertIn("failed 3 times in a row", herd.gate(self.root, {})["reason"])



class TestThirdReview(Base):
    """The holes a third fresh-context review found."""

    def test_a_faked_upgrade_keeps_the_risk_and_needs_a_reason(self):
        herd.init_task(self.root, "t1", "Change auth/session.py", request="Change auth/session.py")
        (self.root / ".herd/tasks/t1/task.toml").write_text(TASK)
        (self.root / "auth").mkdir()
        (self.root / "auth/session.py").write_text("x = 1\n")  # code before any verify
        d = self.root / ".herd/tasks/t1"
        (d / "start.json").unlink()
        (d / "evidence.json").write_text(json.dumps({"task": "t1", "results": []}))
        self.attacks_and_review()
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["risk"]["effective"], "high")
        self.assertIn("start.json is missing", " ".join(herd.problems(self.root, "t1")))

    def test_a_commit_after_a_high_risk_review_keeps_the_review(self):
        (self.root / "auth").mkdir()
        self.start()
        self.red_then_build()
        (self.root / "auth/session.py").write_text("x = 1\n")
        for a in herd.ATTACKS:
            herd.add_note(self.root, "t1", "tried", f"{a} attack", attack=a, check=OK)
        herd.verify(self.root, "t1")
        herd.add_review(self.root, "t1", by="a fresh subagent", text="no Blocker or Major")
        git(self.root, "add", "-A", "--", ".", ":!.herd")
        git(self.root, "commit", "-q", "-m", "the reviewed change")
        herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])

    def test_a_skipped_review_at_high_risk_also_goes_stale(self):
        (self.root / "auth").mkdir()
        self.start()
        self.red_then_build()
        (self.root / "auth/session.py").write_text("x = 1\n")
        for a in herd.ATTACKS:
            herd.add_note(self.root, "t1", "tried", f"{a} attack", attack=a, check=OK)
        herd.verify(self.root, "t1")
        herd.add_review(self.root, "t1", skipped=True, text="no subagent here")
        (self.root / "auth/session.py").write_text("x = 2\n")
        herd.verify(self.root, "t1")
        self.assertIn("the code changed after the review", " ".join(herd.problems(self.root, "t1")))

    def test_a_used_rewording_note_cannot_drop_the_criterion_later(self):
        self.start()
        self.red_then_build()
        self.attacks_and_review()
        narrowed = TASK.replace('text = "It must return 1 for any call"', 'text = "It must return 1 for one call"')
        (self.root / ".herd/tasks/t1/task.toml").write_text(narrowed)
        herd.add_note(self.root, "t1", "human-change", "C1: the human said: It must return 1 for one call")
        herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])
        removed = TASK.split("[[criteria]]")[0] + "[[criteria]]" + TASK.split("[[criteria]]")[2]
        (self.root / ".herd/tasks/t1/task.toml").write_text(removed)
        herd.verify(self.root, "t1")
        self.assertIn("C1 was removed", " ".join(herd.problems(self.root, "t1")))

    def stash_case(self, branch):
        if branch:
            git(self.root, "checkout", "-q", "-b", branch)
        else:
            git(self.root, "checkout", "-q", "--detach")
        self.start()
        (self.root / "app.py").write_text("def f():\n    return 1\n")
        git(self.root, "stash", "push", "-q", "-u", "--", "app.py")
        herd.verify(self.root, "t1")
        git(self.root, "stash", "pop", "-q")
        return herd.verify(self.root, "t1")["red"]["stashed"]

    def test_stash_is_found_on_an_uppercase_branch(self):
        self.assertTrue(self.stash_case("Feature/Login"))

    def test_stash_is_found_on_a_detached_head(self):
        self.assertTrue(self.stash_case(None))

    def test_a_stash_from_before_init_is_not_flagged(self):
        (self.root / "old.py").write_text("x = 1\n")
        git(self.root, "stash", "push", "-q", "-u", "--", "old.py")
        self.start()
        self.red_then_build()
        self.assertEqual(herd.verify(self.root, "t1")["red"]["stashed"], [])

    def test_passing_again_after_a_failure_reminds_about_herd_done_again(self):
        self.start()
        self.red_then_build()
        self.attacks_and_review()
        herd.verify(self.root, "t1")
        for _ in range(herd.MAX_BLOCKS):
            herd.gate(self.root, {})
        self.assertIsNone(herd.gate(self.root, {}))
        (self.root / "app.py").write_text("def f():\n    return 1 + 1\n")  # another size: a same-size edit in the
        self.assertEqual(herd.verify(self.root, "t1")["summary"]["failing"], 1)  # same second can reuse the old .pyc
        self.assertIn("C1 is failing", herd.gate(self.root, {})["reason"])
        (self.root / "app.py").write_text("def f():\n    return 1\n")
        herd.verify(self.root, "t1")
        self.assertIn("evidence passes", herd.gate(self.root, {})["reason"])

    def test_a_script_under_a_test_directory_is_not_code(self):
        (self.root / "tests").mkdir()
        (self.root / "tests/run").write_text("#!/bin/sh\n")
        self.assertFalse(herd.is_code("tests/run", self.root))



class TestNarrowedClaims(Base):
    """Lesson from 12 Haiku runs: a limit that narrows the human's any/every claim reaches the human."""

    def test_a_limit_that_narrows_an_any_claim_is_not_proven_and_warned(self):
        narrowed = TASK.replace('known_limits = "Repeated calls are not timed."',
                                'known_limits = "Repeated calls are not timed. Calls with arguments are rejected."')
        self.start(narrowed)
        self.red_then_build()
        self.attacks_and_review()
        herd.add_note(self.root, "t1", "open", "only the first call is cached")
        ev = herd.verify(self.root, "t1")
        line = "C1 says 'any', narrowed by: Calls with arguments are rejected."
        self.assertIn(line, herd.report(ev))
        self.assertIn(line, herd.pr_body(self.root, "t1"))
        self.assertIn("C1 says 'any', narrowed by: only the first call is cached", herd.report(ev))
        self.assertNotIn("narrowed by: Repeated calls are not timed", herd.report(ev))
        self.assertTrue(any("narrows it" in w for w in ev["warnings"]), ev["warnings"])
        self.assertEqual(herd.problems(self.root, "t1"), [])  # shown to the human, not blocked
        self.assertIn("narrowed by: Calls with arguments are rejected", self.cli("done").stdout)

    def test_no_narrowing_lines_without_a_human_any_claim(self):
        text = TASK.replace('"It must return 1 for any call"', '"It must return 1"').replace(
            'known_limits = "Repeated calls are not timed."', 'known_limits = "Only one call is checked."').replace(
            'text = "Given the module', 'text = "Given any module')  # an agent's "any" does not count
        self.start(text)
        self.red_then_build()
        ev = herd.verify(self.root, "t1")
        self.assertNotIn("narrowed by", herd.report(ev))
        self.assertFalse(any("narrows it" in w for w in ev["warnings"]))


if __name__ == "__main__":
    unittest.main()
