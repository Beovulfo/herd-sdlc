"""Rules the run skill used to state only in text, now enforced or recorded by the CLI (0.4.0)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import herd
from tests.test_herd_cli import hook_review, intake_review, late_review

OK = "python3 -c \"import json\""  # an attack command that passes and is not vacuous
REQUEST = "Add f() to app.py. It must return 1 for any call."
APP_CHECK = "python3 -c \"import app; assert app.f() == 1\""
TASK = f'''goal = "Add f() to app.py"
test_budget = "Two import probes; no unit tests"
known_limits = "Repeated calls are not timed."
inputs = []

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

NO_INPUTS = TASK.replace("inputs = []\n", "")

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
        try:  # most tests are not about the intake review (0.11.0): it passed before the code
            intake_review(self.root)
        except (OSError, ValueError):  # a test of a broken task.toml
            pass

    def red_then_build(self):
        """Red first done right: a test file, the failing verify, then the code."""
        (self.root / "tests").mkdir(exist_ok=True)
        (self.root / "tests/test_app.py").write_text("import app\n")
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["summary"]["failing"], 2)
        (self.root / "app.py").write_text("def f():\n    return 1\n")
        return ev  # the first verify

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

    def test_done_needs_a_review_the_hook_recorded(self):  # 0.7.0: no skip, no hand-recorded review
        self.start()
        self.red_then_build()
        for a in herd.ATTACKS:
            herd.add_note(self.root, "t1", "tried", a, attack=a, check=OK)
        herd.verify(self.root, "t1")
        self.assertIn("review", " ".join(herd.problems(self.root, "t1")))
        self.assertEqual(self.cli("review", "a fresh subagent").returncode, 1)  # --by names who reviewed
        self.assertEqual(self.cli("review", "--skipped", "no subagent can be spawned here").returncode, 1)
        self.assertIn("unreviewed", herd.pr_body(self.root, "t1"))
        hook_review(self.root, builder="haiku", reviewer="sonnet")
        self.assertEqual(herd.problems(self.root, "t1"), [])
        self.assertIn("Review: claude-sonnet-5-5 (sonnet, builder on haiku; PASS; ran git diff or git show, read 0 of 1 changed code file)", herd.report(herd.verify(self.root, "t1")))

    def test_review_by_a_named_reviewer_is_recorded(self):
        self.start()
        self.red_then_build()
        self.attacks_and_review()
        ev = herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])
        self.assertIn("Review: a fresh subagent (opus, builder on opus; same tier; PASS; ran git diff or git show, read 0 of 0 changed code files): no Blocker or Major",
                      herd.report(ev))

    def test_the_latest_of_several_reviews_is_the_one_reported(self):
        self.start()
        self.red_then_build()
        herd.add_review(self.root, "t1", by="me", text="a note, not a review that counts")
        hook_review(self.root, text="One Major, fixed.\nHERD-REVIEW: PASS")
        self.assertIn("(opus, builder on opus; same tier; PASS; ran git diff or git show, read 0 of 1 changed code file): One Major, fixed.",
                      herd.report(herd.verify(self.root, "t1")))
        self.assertNotIn("unreviewed", herd.pr_body(self.root, "t1"))
        with open(self.root / ".herd/tasks/t1/notes.jsonl", "a") as f:  # a skipped review from before 0.7.0
            f.write(json.dumps({"at": herd.now(), "kind": "review", "text": "the reviewer crashed", "skipped": True}) + "\n")
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
        intake_review(self.root)  # the criteria changed: the intake review is needed again (0.11.0)
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
        self.assertIn("Review: a fresh subagent (opus, builder on opus; same tier; PASS; ran git diff or git show, read 0 of 0 changed code files): no Blocker or Major", out)
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
        hook_review(self.root, text="Looked at the plan.\nHERD-REVIEW: PASS")
        herd.verify(self.root, "t1")  # all checks pass for the first time, after the review
        self.assertIn("recorded before all checks first passed", " ".join(herd.problems(self.root, "t1")))
        hook_review(self.root)
        self.assertEqual(herd.problems(self.root, "t1"), [])

    def test_a_review_at_a_lower_risk_does_not_count_once_the_risk_rises(self):
        self.start()
        self.red_then_build()
        for a in herd.ATTACKS:
            herd.add_note(self.root, "t1", "tried", f"{a} attack", attack=a, check=OK)
        herd.verify(self.root, "t1")
        hook_review(self.root)
        self.assertEqual(herd.problems(self.root, "t1"), [])
        (self.root / "auth").mkdir()
        (self.root / "auth/session.py").write_text("x = 1\n")  # a high-risk path
        herd.verify(self.root, "t1")
        self.assertIn("the risk rose to high after the review", " ".join(herd.problems(self.root, "t1")))

    def test_code_changed_after_the_review_is_reported(self):
        self.start()
        self.red_then_build()
        herd.verify(self.root, "t1")
        hook_review(self.root)
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
        intake_review(self.root)  # the criteria changed: the intake review is needed again (0.11.0)
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
        intake_review(self.root)  # the criteria changed: the intake review is needed again (0.11.0)
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
        intake_review(self.root)  # the criteria changed: the intake review is needed again (0.11.0)
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
        hook_review(self.root)
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
        hook_review(self.root)
        git(self.root, "add", "-A", "--", ".", ":!.herd")
        git(self.root, "commit", "-q", "-m", "the reviewed change")
        herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])

    def test_a_used_rewording_note_cannot_drop_the_criterion_later(self):
        self.start()
        self.red_then_build()
        self.attacks_and_review()
        narrowed = TASK.replace('text = "It must return 1 for any call"', 'text = "It must return 1 for one call"')
        (self.root / ".herd/tasks/t1/task.toml").write_text(narrowed)
        herd.add_note(self.root, "t1", "human-change", "C1: the human said: It must return 1 for one call")
        intake_review(self.root)  # the criteria changed: the intake review is needed again (0.11.0)
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
        line = "C1 says 'any'; narrowed by: Calls with arguments are rejected."
        self.assertIn(line, herd.report(ev))
        self.assertIn(line, herd.pr_body(self.root, "t1"))
        self.assertNotIn("narrowed by: only the first call", herd.report(ev))  # open notes are listed already
        self.assertIn("only the first call is cached", herd.report(ev))
        self.assertNotIn("narrowed by: Repeated calls are not timed", herd.report(ev))
        self.assertTrue(any("narrows it" in w for w in ev["warnings"]), ev["warnings"])
        self.assertEqual(herd.problems(self.root, "t1"), [])  # shown to the human, not blocked
        self.assertIn("narrowed by: Calls with arguments are rejected", self.cli("done").stdout)

    def test_an_any_claim_without_random_inputs_in_its_coverage_is_warned(self):
        task = {"criteria": [{"id": "C1", "source": "human", "text": "works whatever its layout",
                              "coverage": "Proves valid routes on generated aisle, hall and maze layouts"}],
                "known_limits": "x"}
        self.assertTrue(any("names no random inputs" in w for w in herd.coverage_warnings(task)))
        task["criteria"][0]["coverage"] += ", plus 50 random-obstacle stores from fixed seeds"
        self.assertFalse(any("names no random inputs" in w for w in herd.coverage_warnings(task)))
        task["criteria"][0].update(source="agent-proposed", coverage="Proves aisle layouts")
        self.assertFalse(any("random" in w for w in herd.coverage_warnings(task)))  # only the human's claim

    def test_empty_or_odd_evidence_gives_no_lines_and_no_error(self):
        human_any = [{"id": "C1", "source": "human", "text": "works for any layout"}]
        for ev in ({}, {"results": []}, {"results": human_any, "known_limits": None},
                   {"results": human_any, "known_limits": ""}, {"results": [{"id": "C1"}], "known_limits": "only x"}):
            self.assertEqual(herd.narrowed_claims(ev, []), [], ev)
        self.assertEqual(herd.narrowed_claims({"results": human_any, "known_limits": "Only small maps."}, []),
                         ["C1 says 'any'; narrowed by: Only small maps."])

    def test_sentences_split_only_at_sentence_ends(self):
        human_any = [{"id": "C1", "source": "human", "text": "works whatever its layout"}]
        lim = ("Random-wall layouts can cut products off; they are rejected. Speed is 1.5 cells per s. "
               "Uses e.g. BFS. Unreachable products are dropped.")
        self.assertEqual(herd.narrowed_claims({"results": human_any, "known_limits": lim}),
                         ["C1 says 'whatever'; narrowed by: Random-wall layouts can cut products off; they are rejected.",
                          "C1 says 'whatever'; narrowed by: Unreachable products are dropped."])

    def test_several_claims_share_one_line_per_limit_and_the_list_is_capped(self):
        claims = [{"id": f"C{i}", "source": "human", "text": "for all stores"} for i in (1, 2)]
        lim = " ".join(f"Layout {i} is skipped." for i in range(7)) + " Layout 0 is skipped."
        out = herd.narrowed_claims({"results": claims, "known_limits": lim})
        self.assertEqual(out[0], "C1 says 'all', C2 says 'all'; narrowed by: Layout 0 is skipped.")
        self.assertEqual(len(out), herd.MAX_NARROWED + 1)  # duplicates once, five lines, then the count
        self.assertEqual(out[-1], "and 2 more narrowing limits in known_limits")
        warn = [w for w in herd.coverage_warnings({"criteria": claims, "known_limits": lim}) if "narrow" in w]
        self.assertEqual(len(warn), 1)
        self.assertIn("C1 says 'all', C2 says 'all', but 7 known limits narrow it", warn[0])

    def test_no_narrowing_lines_without_a_human_any_claim(self):
        text = TASK.replace('"It must return 1 for any call"', '"It must return 1"').replace(
            'known_limits = "Repeated calls are not timed."', 'known_limits = "Only one call is checked."').replace(
            'text = "Given the module', 'text = "Given any module')  # an agent's "any" does not count
        self.start(text)
        self.red_then_build()
        ev = herd.verify(self.root, "t1")
        self.assertNotIn("narrowed by", herd.report(ev))
        self.assertFalse(any("narrows it" in w for w in ev["warnings"]))


class TestPreInitEdits(Base):
    """An agent that edits code and only then runs `herd init` is flagged: the PreToolUse hook reads the session log."""

    def session_log(self, *paths, tools=("Edit", "Write"), log=None):
        """A Claude Code session log (JSONL) in which the agent edited these files with these tools, in turn."""
        log = log or self.root.parent / f"{self.root.name}-session.jsonl"
        lines = [{"type": "user", "message": {"role": "user", "content": "build it"}}]
        for i, path in enumerate(paths):
            tool = tools[i % len(tools)]
            key = "notebook_path" if tool == "NotebookEdit" else "file_path"
            lines.append({"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "editing"},
                {"type": "tool_use", "id": f"t{i}", "name": tool, "input": {key: str(path)}}]}})
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
        return log

    def hook(self, command, log=None, raw=None):
        """Run the hook the way Claude Code does: hook JSON on stdin, from the project folder."""
        data = raw if raw is not None else json.dumps({
            "hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.root),
            "transcript_path": str(log) if log else "", "tool_input": {"command": command}})
        return subprocess.run([sys.executable, str(Path(herd.__file__)), "preinit"], cwd=self.root, input=data,
                              capture_output=True, text=True)

    INIT = f'python3 "{Path(herd.__file__)}" init t1 "Add f() to app.py" --request "{REQUEST}"'

    def test_code_the_session_edited_before_init_is_flagged(self):
        (self.root / "app.py").write_text("def f():\n    return 1\n")  # written by the agent with Write
        p = self.hook(self.INIT, self.session_log(self.root / "app.py", "app.py"))  # Edit, then Write by relative path
        self.assertEqual((p.returncode, p.stdout), (0, ""), p.stderr)
        self.start()
        self.assertEqual(json.loads((self.root / ".herd/tasks/t1/start.json").read_text())["agent_edits"], ["app.py"])
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["red"]["code_before"], ["app.py"])
        self.assertIn("red first not proven", " ".join(herd.problems(self.root, "t1")))

    def test_the_humans_own_uncommitted_file_stays_theirs(self):
        (self.root / "notes.py").write_text("x = 1\n")  # the human's, never touched by the session
        (self.root / "app.py").write_text("def f():\n    return 1\n")
        outside = self.root.parent / "elsewhere.py"  # an edit outside the project does not count
        self.hook(self.INIT, self.session_log(self.root / "app.py", outside))
        self.start()
        self.assertEqual(herd.verify(self.root, "t1")["red"]["code_before"], ["app.py"])

    def test_other_commands_and_bad_input_do_nothing(self):
        (self.root / "app.py").write_text("x = 1\n")
        log = self.session_log(self.root / "app.py")
        for p in (self.hook("ls -la", log), self.hook("echo herd init is great", log), self.hook(self.INIT, None),
                  self.hook(self.INIT, self.root / "missing.jsonl"), self.hook("", raw="{not json"),
                  self.hook("", raw=""), self.hook("", raw='["a list"]')):
            self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))
        self.start()  # nothing was recorded, so the uncommitted file counts as the human's, as before
        self.assertNotIn("agent_edits", json.loads((self.root / ".herd/tasks/t1/start.json").read_text()))
        self.assertEqual(herd.verify(self.root, "t1")["red"]["code_before"], [])

    def test_a_record_from_another_checkout_or_an_old_one_is_not_used(self):
        (self.root / "app.py").write_text("def f():\n    return 1\n")
        self.hook(self.INIT, self.session_log(self.root / "app.py"))
        rec = herd._preinit_path(self.root, "t1")
        data = json.loads(rec.read_text())
        rec.write_text(json.dumps(dict(data, at=data["at"] - herd.PREINIT_MAX_AGE - 60)))  # another run's
        self.start()
        self.assertFalse(rec.exists())  # init always consumes it
        self.assertEqual(herd.verify(self.root, "t1")["red"]["code_before"], [])

    def test_a_refused_or_mentioned_init_never_leaks_into_another_task(self):
        (self.root / "human.py").write_text("x = 1\n")  # the human's
        log = self.session_log(self.root / "human.py")  # session A touched it, then its init for task a is refused
        self.hook(f'python3 "{Path(herd.__file__)}" init a "goal"', log)
        self.hook('grep "herd.py init" README.md', log)  # only mentions it
        self.start()  # task t1, by the human or another session with no record of its own
        self.assertNotIn("agent_edits", json.loads((self.root / ".herd/tasks/t1/start.json").read_text()))
        self.assertTrue(herd._preinit_path(self.root, "a").exists())  # left for task a alone, and it expires

    def test_an_init_with_no_edits_overwrites_an_older_record(self):
        (self.root / "app.py").write_text("x = 1\n")
        self.hook(self.INIT, self.session_log(self.root / "app.py"))
        self.hook(self.INIT, self.session_log())  # a later session for the same task edited nothing
        self.start()
        self.assertNotIn("agent_edits", json.loads((self.root / ".herd/tasks/t1/start.json").read_text()))

    def test_subagent_edits_and_every_edit_tool_count(self):
        for f in ("a.py", "b.py", "c.ipynb", "d.py"):
            (self.root / f).write_text("x = 1\n")
        log = self.session_log(self.root / "a.py", self.root / "b.py", self.root / "c.ipynb",
                               tools=("MultiEdit", "Edit", "NotebookEdit"))
        self.session_log(self.root / "d.py", log=log.parent / log.stem / "subagents" / "agent-1.jsonl")
        self.hook(self.INIT, log)
        self.start()
        edits = json.loads((self.root / ".herd/tasks/t1/start.json").read_text())["agent_edits"]
        self.assertEqual(edits, ["a.py", "b.py", "c.ipynb", "d.py"])

    def test_cd_before_init_is_followed(self):
        sub = self.root / "proj"
        sub.mkdir()
        (sub / "app.py").write_text("x = 1\n")
        elsewhere = self.root.parent / f"{self.root.name}-cwd"
        elsewhere.mkdir()
        hook = json.dumps({"cwd": str(elsewhere), "transcript_path": str(self.session_log(sub / "app.py")),
                           "tool_input": {"command": f'cd {self.root} && python3 "{Path(herd.__file__)}" init t1 "g"'}})
        p = subprocess.run([sys.executable, str(Path(herd.__file__)), "preinit"], cwd=elsewhere, input=hook,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(herd._preinit_path(self.root, "t1").exists())

    def test_a_corrupt_record_never_stops_init(self):
        (self.root / "app.py").write_text("x = 1\n")
        for bad in ('["a list"]', '{"at": "soon", "files": ["app.py"]}', '{"at": 1e12, "files": [3, null]}', "{x"):
            herd._preinit_path(self.root, "t1").write_text(bad)
            herd.init_task(self.root, "t1", "g")
            self.assertFalse(herd._preinit_path(self.root, "t1").exists(), bad)
            herd.cancel_task(self.root, "t1")
            shutil.rmtree(self.root / ".herd/tasks/t1")

    def test_the_hook_is_registered_and_safe_on_old_python(self):
        hooks = json.loads((Path(herd.__file__).parent.parent / "hooks/hooks.json").read_text())["hooks"]
        pre = [h for g in hooks["PreToolUse"] if g.get("matcher") == "Bash" for h in g["hooks"]]
        self.assertEqual(len(pre), 1)
        self.assertIn('herd.py\" preinit', pre[0]["command"])
        src = Path(herd.__file__).read_text()
        self.assertIn('sys.argv[1:2] in (["gate"], ["lint"], ["preinit"], ["guard"], ["review-hook"])', src)  # exits 0 before 3.11 code runs


class TestStopRecord(Base):
    """Part C of docs/designs/herd-guardrails.md: stopped.json for every stop without `herd done`."""
    FIELDS = {"at", "reason", "detail", "problems", "evidence", "review", "elapsed_s", "gate_blocks", "resumable", "next"}

    def record(self):
        return json.loads((self.root / ".herd/tasks/t1/stopped.json").read_text())

    def release(self):
        for _ in range(herd.MAX_BLOCKS):
            self.assertIsNotNone(herd.gate(self.root, {}))
        self.assertIsNone(herd.gate(self.root, {}))
        return self.record()

    def ready(self):
        self.start()
        self.red_then_build()
        self.attacks_and_review()
        herd.verify(self.root, "t1")

    def test_stop_record_on_release(self):
        self.start()
        herd.verify(self.root, "t1")  # red: C1 and C2 fail
        self.assertFalse((self.root / ".herd/tasks/t1/stopped.json").exists())
        rec = self.release()
        self.assertEqual(set(rec), self.FIELDS)
        self.assertEqual(rec["reason"], "released")
        self.assertEqual(rec["problems"], herd.problems(self.root, "t1"))
        self.assertEqual(rec["gate_blocks"], herd.MAX_BLOCKS)
        self.assertEqual(set(rec["evidence"]), {"verified_at", "sha", "stale"})
        self.assertFalse(rec["evidence"]["stale"])
        self.assertEqual(set(rec["review"]), {"needed", "latest"})
        self.assertTrue(rec["review"]["needed"])  # medium risk
        self.assertIsInstance(rec["elapsed_s"], int)
        self.assertTrue(rec["resumable"])
        self.assertEqual(rec["next"], "fix C1, then run `herd verify`")
        out = self.cli("status").stdout.splitlines()
        self.assertEqual(out[0], f"Stopped {rec['at']}: released. Next: fix C1, then run `herd verify`")

    def test_stop_record_on_release_when_done_keeps_refusing(self):
        self.ready()
        rec = self.release()
        self.assertEqual(set(rec), self.FIELDS)
        self.assertEqual(rec["reason"], "done_refused")
        self.assertEqual(rec["problems"], [])
        self.assertTrue(rec["resumable"])
        self.assertEqual(rec["next"], "commit the work, run `herd verify`, then run `herd done`")  # app.py is uncommitted
        self.assertTrue(self.cli("status").stdout.startswith(f"Stopped {rec['at']}: done_refused. Next: "))

    def test_stop_record_on_cancel(self):
        self.start()
        herd.verify(self.root, "t1")
        herd.gate(self.root, {})
        self.assertEqual(self.cli("cancel", "--reason", "the human dropped it").returncode, 0)
        rec = self.record()
        self.assertEqual(set(rec), self.FIELDS)
        self.assertEqual((rec["reason"], rec["detail"]), ("cancelled", "the human dropped it"))
        self.assertEqual(rec["gate_blocks"], 1)  # read before cancel clears the counter
        self.assertEqual((rec["resumable"], rec["next"]), (False, "start a new task"))
        self.assertTrue(self.cli("status", "t1").stdout.startswith(f"Stopped {rec['at']}: cancelled. Next: start a new task"))

    def test_stop_record_on_escalation(self):
        self.start()
        for _ in range(1 + herd.ESCALATE_AFTER):  # the red run, then three failed attempts
            herd.verify(self.root, "t1")
        out = herd.gate(self.root, {})
        self.assertEqual(out["decision"], "block")  # the agent is told to ask; the record says why it stops
        self.assertIn("ask the human one question", out["reason"])
        rec = self.record()
        self.assertEqual(set(rec), self.FIELDS)
        self.assertEqual(rec["reason"], "escalated")
        self.assertEqual(rec["detail"], "C1 failed 3 times in a row; C2 failed 3 times in a row")
        self.assertFalse(rec["resumable"])
        self.assertEqual(rec["next"], "the human answers one question about: C1 failed 3 times in a row; "
                                      "C2 failed 3 times in a row")
        self.assertTrue(self.cli("status").stdout.startswith(f"Stopped {rec['at']}: escalated. Next: the human answers"))

    def test_resumable_is_computed(self):
        self.start()
        rec = herd.write_stop(self.root, "t1", "released")  # no evidence yet
        self.assertEqual((rec["resumable"], rec["next"]), (True, "run `herd verify`"))
        self.assertEqual((rec["evidence"], rec["review"]), (None, None))
        self.red_then_build()
        herd.verify(self.root, "t1")  # all pass; no review and no attacks yet
        probs = herd.problems(self.root, "t1")
        self.assertTrue(probs[0].startswith("review missing"), probs)
        rec = herd.write_stop(self.root, "t1", "released")
        self.assertEqual(rec["problems"], probs)
        self.assertTrue(rec["resumable"])
        self.assertIn("spawn herd-reviewer", rec["next"])
        self.assertEqual(rec["review"], {"needed": "one tier above the builder", "latest": None})
        late_review(self.root)
        herd.verify(self.root, "t1")
        rec = herd.write_stop(self.root, "t1", "released")
        self.assertTrue(rec["problems"][0].startswith("adversarial pass incomplete"))
        self.assertIn("herd note --tried --attack", rec["next"])
        (self.root / "app.py").write_text("def f():\n    return 1  # changed\n")  # stale evidence
        rec = herd.write_stop(self.root, "t1", "released")
        self.assertTrue(rec["evidence"]["stale"])
        self.assertEqual(rec["next"], "run `herd verify`")
        self.assertEqual(rec["problems"], herd.problems(self.root, "t1"))
        # an agent that writes its own record is overwritten at the next stop
        path = self.root / ".herd/tasks/t1/stopped.json"
        path.write_text(json.dumps({"reason": "released", "resumable": False, "next": "nothing to do"}))
        for _ in range(herd.MAX_BLOCKS + 1):
            herd.gate(self.root, {})
        self.assertEqual((self.record()["resumable"], self.record()["next"]), (True, "run `herd verify`"))
        # lost state files: not resumable by the agent
        (self.root / ".herd/tasks/t1/red.json").write_text("{not json")
        herd.verify(self.root, "t1")
        rec = herd.write_stop(self.root, "t1", "released")
        self.assertEqual((rec["resumable"], rec["next"]), (False, "a human restores the state files, or cancels"))
        (self.root / ".herd/tasks/t1/evidence.json").write_text("{not json")
        rec = herd.write_stop(self.root, "t1", "released")
        self.assertEqual((rec["resumable"], rec["evidence"]), (False, None))
        with self.assertRaises(ValueError):
            herd.write_stop(self.root, "t1", "finished")

    def test_unknown_problem_gets_a_generic_next_step(self):
        self.assertEqual(herd.next_step(["something new"]), "fix this, then run `herd verify`: something new")
        self.assertEqual(herd.next_step([]), "run `herd done`")
        self.assertEqual(herd.next_step(["the check of human criterion C3 changed after the first verify"])[:27],
                         "restore human criterion C3 ")

    def test_stop_record_resolved(self):
        self.start()
        herd.verify(self.root, "t1")
        first = self.release()
        (self.root / "app.py").write_text("def f():\n    return 1\n")  # the code comes after the red run
        herd.verify(self.root, "t1")
        self.attacks_and_review()
        herd.verify(self.root, "t1")
        p = self.cli("done")
        self.assertEqual(p.returncode, 0, p.stderr)
        rec = self.record()
        self.assertEqual({k: v for k, v in rec.items() if k != "resolved_at"}, first)
        self.assertRegex(rec["resolved_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertIn(f"Stopped before: released at {first['at']}, resolved at {rec['resolved_at']}", p.stdout)
        self.assertTrue(self.cli("status", "t1").stdout.startswith(
            f"Stopped {first['at']}: released. Resolved at {rec['resolved_at']} by herd done."))

    def test_stop_record_readers(self):
        self.start()
        herd.verify(self.root, "t1")
        rec = self.release()
        p = self.cli("status", "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout), rec)
        ev, notes = herd.load_evidence(self.root, "t1"), herd.load_notes(self.root, "t1")
        self.assertIn(f"Stopped before: released at {rec['at']}", "\n".join(herd.final_report(self.root, "t1", ev, notes)))
        self.assertIn(f"Stopped before: released at {rec['at']}.", herd.pr_body(self.root, "t1"))
        (self.root / ".herd/tasks/t1/stopped.json").unlink()
        self.assertEqual(self.cli("status", "--json").stdout.strip(), "null")
        self.assertNotIn("Stopped", herd.pr_body(self.root, "t1") + self.cli("status").stdout)

    def test_stop_record_not_written_without_a_stop(self):
        self.assertIsNone(herd.gate(self.root, {}))  # no task at all
        self.assertFalse((self.root / ".herd").exists())
        self.ready()
        path = self.root / ".herd/tasks/t1/stopped.json"
        self.assertEqual(herd.gate(self.root, {})["decision"], "block")  # passing: a reminder, not a stop
        self.assertFalse(path.exists())
        (self.root / "app.py").write_text("def f():\n    return 1 + 1\n")  # another size: no stale .pyc
        herd.verify(self.root, "t1")
        self.assertEqual(herd.gate(self.root, {})["decision"], "block")  # one blocked attempt is not a stop
        self.assertFalse(path.exists())
        herd.cancel_task(self.root, "t1", "dropped")
        before = path.read_text()
        self.assertIsNone(herd.gate(self.root, {}))  # a cancelled task: the gate writes nothing more
        self.assertEqual(path.read_text(), before)


class TestStopRecordAttacks(Base):
    """The adversarial pass on the stop record (skills/run/adversarial.md)."""

    def record(self):
        return json.loads((self.root / ".herd/tasks/t1/stopped.json").read_text())

    def test_bad_input_never_breaks_a_stop_or_a_reader(self):
        self.start()
        herd.verify(self.root, "t1")
        d = self.root / ".herd/tasks/t1"
        for bad in ("{not json", "[1, 2]", "", "null"):  # a hand-edited stop record
            (d / "stopped.json").write_text(bad)
            self.assertIsNone(herd.load_stop(self.root, "t1"))
            p = self.cli("status", "--json")
            self.assertEqual((p.returncode, p.stdout.strip()), (0, "null"), p.stderr)
            p = self.cli("status")
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertNotIn("Traceback", p.stderr)
        (d / "gate_blocks").write_text("lots")  # a hand-edited counter
        self.assertEqual(herd.gate(self.root, {})["decision"], "block")
        (d / "started").write_text("yesterday")  # a hand-edited start time
        rec = herd.write_stop(self.root, "t1", "released")
        self.assertIsNone(rec["elapsed_s"])
        (d / "notes.jsonl").write_text("{broken\n")  # a hand-edited log
        rec = herd.write_stop(self.root, "t1", "released")
        self.assertFalse(rec["resumable"])
        self.assertIn("notes.jsonl", " ".join(rec["problems"]))
        self.assertEqual(self.cli("status", "nosuchtask", "--json").returncode, 0)  # no task: no record
        for reason in ("", "done", "RELEASED"):
            with self.assertRaises(ValueError):
                herd.write_stop(self.root, "t1", reason)

    def test_collision_a_later_stop_replaces_the_earlier_one(self):
        self.start()
        for _ in range(1 + herd.ESCALATE_AFTER):
            herd.verify(self.root, "t1")
        herd.gate(self.root, {})
        self.assertEqual(self.record()["reason"], "escalated")
        for _ in range(herd.MAX_BLOCKS):
            herd.gate(self.root, {})
        rec = self.record()  # released while escalated: still the human's call
        self.assertEqual((rec["reason"], rec["resumable"]), ("released", False))
        herd.cancel_task(self.root, "t1", "dropped")
        rec = self.record()
        self.assertEqual((rec["reason"], rec["next"]), ("cancelled", "start a new task"))
        self.assertTrue(self.cli("status", "t1").stdout.startswith(f"Stopped {rec['at']}: cancelled."))
        herd.init_task(self.root, "t2", "another task", request="another task")  # each task keeps its own record
        self.assertFalse((self.root / ".herd/tasks/t2/stopped.json").exists())
        self.assertEqual(self.record()["reason"], "cancelled")

    def test_one_bad_part_still_writes_the_rest_of_the_record(self):
        self.start()
        herd.verify(self.root, "t1")
        d = self.root / ".herd/tasks/t1"
        (d / "evidence.json").write_text("{not json")
        self.assertEqual(herd.gate(self.root, {})["decision"], "block")  # blocks and names the file, no crash
        self.assertIn("unreadable", herd.gate(self.root, {})["reason"])
        herd.gate(self.root, {})
        self.assertIsNone(herd.gate(self.root, {}))  # released after 3 blocks
        rec = self.record()
        self.assertEqual(rec["reason"], "released")
        self.assertEqual((rec["evidence"], rec["resumable"], rec["gate_blocks"]), (None, False, 3))
        self.assertIsInstance(rec["elapsed_s"], int)
        (d / "started").unlink()
        rec = herd.write_stop(self.root, "t1", "released")
        self.assertIsNone(rec["elapsed_s"])
        self.assertEqual(rec["reason"], "released")

    def test_recount_the_record_numbers_with_separate_code(self):
        from datetime import datetime
        self.start()
        herd.verify(self.root, "t1")
        blocked = 0
        while herd.gate(self.root, {}) is not None:
            blocked += 1
        rec = self.record()
        self.assertEqual(rec["gate_blocks"], blocked)
        started = (self.root / ".herd/tasks/t1/started").read_text().strip()
        secs = (datetime.fromisoformat(rec["at"].replace("Z", "+00:00"))
                - datetime.fromisoformat(started.replace("Z", "+00:00"))).total_seconds()
        self.assertEqual(rec["elapsed_s"], int(secs))
        failing = [r["id"] for r in json.loads((self.root / ".herd/tasks/t1/evidence.json").read_text())["results"]
                   if r["exit_code"] not in (0, None)]
        self.assertEqual([p.split(" ", 1)[0] for p in rec["problems"] if " is failing: " in p], failing)
        self.assertEqual(rec["evidence"]["sha"],
                         subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, capture_output=True,
                                        text=True).stdout.strip())

    def test_wrong_shaped_state_files_still_give_a_record_and_never_crash_the_gate(self):
        d = self.root / ".herd/tasks/t1"
        for name, bad in (("evidence.json", "{}"), ("evidence.json", "[]"), ("evidence.json", '{"results": "x"}'),
                          ("notes.jsonl", "[1]\n"), ("task.toml", None)):
            with self.subTest(name=name, bad=bad):
                if d.exists():
                    shutil.rmtree(self.root / ".herd")
                self.start()
                herd.verify(self.root, "t1")
                (d / name).unlink() if bad is None else (d / name).write_text(bad)
                for _ in range(herd.MAX_BLOCKS + 1):
                    out = herd.gate(self.root, {})  # never raises
                self.assertIsNone(out)
                rec = self.record()
                self.assertEqual((rec["reason"], rec["resumable"]), ("released", False))
                self.assertEqual(rec["next"], "a human restores the state files, or cancels")
                if name == "notes.jsonl":  # only the log is bad: the evidence part stays
                    self.assertEqual(rec["evidence"]["sha"], herd.load_evidence(self.root, "t1")["head"])
                herd.cancel_task(self.root, "t1", "x") if bad is not None else None
                if bad is not None:
                    self.assertEqual((self.record()["reason"], self.record()["resumable"]), ("cancelled", False))

    def test_cancel_after_done_keeps_the_resolved_record(self):
        self.start()
        herd.verify(self.root, "t1")
        for _ in range(herd.MAX_BLOCKS + 1):
            herd.gate(self.root, {})
        (self.root / "app.py").write_text("def f():\n    return 1\n")
        herd.verify(self.root, "t1")
        self.attacks_and_review()
        herd.verify(self.root, "t1")
        self.assertEqual(self.cli("done").returncode, 0)
        before = self.record()
        self.assertIn("resolved_at", before)
        herd.cancel_task(self.root, "t1", "oops")
        self.assertEqual(self.record(), before)
        herd.init_task(self.root, "t2", "a done task without a stop", request="x")
        (self.root / ".herd/active").unlink()  # as `herd done` leaves it
        herd.cancel_task(self.root, "t2", "later")
        self.assertFalse((self.root / ".herd/tasks/t2/stopped.json").exists())

    def test_criterion_wording_cannot_steer_next(self):
        task = TASK.replace('id = "C1"', 'id = "red first not proven"')
        self.start(task.replace('text = "Given the module', 'text = "Given an unreadable module'))
        herd.verify(self.root, "t1")
        rec = herd.write_stop(self.root, "t1", "released")
        self.assertEqual((rec["resumable"], rec["next"]), (True, "fix red first not proven, then run `herd verify`"))

    def test_done_refused_counts_its_blocks_and_a_release_keeps_the_escalation(self):
        self.start()
        self.red_then_build()
        self.attacks_and_review()
        herd.verify(self.root, "t1")
        for _ in range(herd.MAX_BLOCKS + 1):
            herd.gate(self.root, {})
        self.assertEqual((self.record()["reason"], self.record()["gate_blocks"]), ("done_refused", herd.MAX_BLOCKS))
        (self.root / "app.py").write_text("def f():\n    return 1 + 1\n")  # another size: no stale .pyc
        for _ in range(herd.ESCALATE_AFTER):
            herd.verify(self.root, "t1")
        for _ in range(herd.MAX_BLOCKS + 1):
            herd.gate(self.root, {})
        rec = self.record()
        self.assertEqual((rec["reason"], rec["detail"], rec["resumable"]),
                         ("released", "C1 failed 3 times in a row", False))


    def test_status_says_when_the_task_went_on_after_the_stop(self):
        import time
        self.start()
        for _ in range(1 + herd.ESCALATE_AFTER):
            herd.verify(self.root, "t1")
        herd.gate(self.root, {})
        rec = self.record()
        self.assertTrue(self.cli("status").stdout.startswith(f"Stopped {rec['at']}: escalated. Next: "))
        time.sleep(1.1)  # times are to the second
        (self.root / "app.py").write_text("def f():\n    return 1\n")
        herd.verify(self.root, "t1")  # the human answered; the agent went on
        self.assertEqual(self.cli("status").stdout.splitlines()[0],
                         f"Stopped {rec['at']}: escalated. The task went on after it (newer evidence): see below.")


class TestRefusalAttack(Base):
    def built(self):
        self.start()
        self.red_then_build()

    def attacks(self, refusal_note="refusal attack", check=OK):
        for a in herd.ATTACKS:
            if a != "refusal":
                herd.add_note(self.root, "t1", "tried", f"{a} attack", attack=a, check=OK)
        herd.add_note(self.root, "t1", "tried", refusal_note, attack="refusal", check=check)

    def test_the_refusal_attack_is_one_of_the_standard_attacks(self):
        self.assertIn("refusal", herd.ATTACKS)
        self.built()
        for a in herd.ATTACKS:
            if a != "refusal":
                herd.add_note(self.root, "t1", "tried", f"{a} attack", attack=a, check=OK)
        late_review(self.root)
        herd.verify(self.root, "t1")
        self.assertIn("refusal (no passing command)", " ".join(herd.problems(self.root, "t1")))

    def test_the_default_reviewer_tier_is_one_above_the_builders(self):  # 0.10.0; 0 in 0.8.0 and 0.9.0
        self.assertEqual(herd.review_tiers(self.root), (list(herd.DEFAULT_TIERS), 1))



class TestInputsAndRefusalFirst(Base):
    """These tests start from TASK without its `inputs = []` (NO_INPUTS)."""
    IN = '\n[[inputs]]\nhuman = "a call"\nprogram = "{}"\n'

    @staticmethod
    def about_inputs(w):
        return w.startswith(("no `inputs`", "inputs #", "`inputs`"))

    def warnings(self, text):
        self.start(text)
        return self.red_then_build()["warnings"]

    def test_no_inputs_is_questioned_and_an_empty_list_is_not(self):
        self.assertTrue([w for w in self.warnings(NO_INPUTS) if w.startswith("no `inputs`")])

    def test_empty_inputs_and_the_quick_route_are_not_questioned(self):
        self.assertFalse([w for w in self.warnings(TASK) if self.about_inputs(w)])

    def test_an_input_without_both_forms_is_questioned(self):
        w = self.warnings(NO_INPUTS + '\n[[inputs]]\nhuman = "a call"\n')
        self.assertTrue([x for x in w if x.startswith("inputs #1")], w)

    def test_the_inputs_are_shown_for_the_human_to_compare(self):
        text = NO_INPUTS + self.IN.format("a call, as typed")
        self.warnings(text)
        ev = herd.verify(self.root, "t1")
        line = "Inputs (as you described them -> as the program receives them): a call -> a call, as typed"
        self.assertIn(line, herd.report(ev))
        self.assertIn(line, herd.pr_body(self.root, "t1"))

    def test_the_first_verify_asks_for_the_refusal_attack(self):
        self.start()
        self.assertIn(herd.REFUSAL_FIRST, self.red_then_build()["warnings"])
        self.assertNotIn(herd.REFUSAL_FIRST, herd.verify(self.root, "t1")["warnings"])  # only the first verify asks

    def test_a_refusal_attack_logged_before_the_first_verify_stops_the_question(self):
        self.start()
        herd.add_note(self.root, "t1", "tried", "refusals", attack="refusal", check=OK)
        self.assertNotIn(herd.REFUSAL_FIRST, self.red_then_build()["warnings"])

    def test_a_refusal_attack_logged_after_the_first_verify_is_warned_about(self):
        self.start()
        self.red_then_build()
        herd.add_note(self.root, "t1", "tried", "refusals", attack="refusal", check=OK)
        w = herd.verify(self.root, "t1")["warnings"]
        self.assertTrue([x for x in w if x.startswith("refusal attack was logged after the first verify")], w)

    def test_a_refusal_attack_logged_before_the_first_verify_is_not_late(self):
        self.start()
        herd.add_note(self.root, "t1", "tried", "refusals", attack="refusal", check=OK)
        self.red_then_build()
        w = herd.verify(self.root, "t1")["warnings"]
        self.assertFalse([x for x in w if x.startswith("refusal attack was logged after")], w)


if __name__ == "__main__":
    unittest.main()
