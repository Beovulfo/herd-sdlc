import json
import re
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import herd

TASK = '''goal = "Add a greeting"

[[criteria]]
id = "C1"
text = "Given a name, when greet runs, then it prints hello"
source = "human"
check = "test -f greet.txt"

[[criteria]]
id = "C2"
text = "The greeting reads well"
source = "agent-proposed"
check = ""
'''


OK = "python3 -c \"import json\""  # an attack command that passes and is not vacuous


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)



def late_review(root, slug="t1"):
    """A review that counts whatever comes next: for tests that are not about when the review happens.

    A real review counts only after all checks first passed and at the risk it saw (see TestReviewFindings);
    this one is placed as if the checks had passed before it, at the highest risk."""
    d = herd._dir(root, slug)
    (d / "green.json").write_text(json.dumps({"at": herd.now(), "notes": 0}))
    with (d / "notes.jsonl").open("a") as f:
        f.write(json.dumps({"at": herd.now(), "kind": "review", "text": "no Blocker or Major",
                            "by": "a fresh subagent", "risk": "high"}) + "\n")


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

    def task(self, text=TASK, attacks=False):
        herd.init_task(self.root, "t1", "Add a greeting")
        (self.root / ".herd/tasks/t1/task.toml").write_text(text)
        if attacks:
            self.attacks()

    def attacks(self, slug="t1", root=None):
        """Record the standard attacks and a review, which `herd done` needs on the standard route."""
        for a in herd.ATTACKS:
            herd.add_note(root or self.root, slug, "tried", f"{a} attack", attack=a, check=OK)
        late_review(root or self.root, slug)


class TestTask(Base):
    def test_init_creates_task_and_active(self):
        herd.init_task(self.root, "t1", "Add a greeting")
        self.assertEqual((self.root / ".herd/active").read_text().strip(), "t1")
        t = herd.load_task(self.root, "t1")
        self.assertEqual(t["goal"], "Add a greeting")
        self.assertEqual(t.get("criteria", []), [])

    def test_init_rejects_bad_slug_and_existing(self):
        with self.assertRaises(ValueError):
            herd.init_task(self.root, "../x", "g")
        herd.init_task(self.root, "t1", "g")
        with self.assertRaises(ValueError):
            herd.init_task(self.root, "t1", "g")

    def test_validate(self):
        self.task()
        self.assertEqual(herd.validate_task(herd.load_task(self.root, "t1")), [])
        bad = {"goal": "", "criteria": [{"id": "C1", "text": "a", "source": "x", "check": "true"},
                                        {"id": "C1", "text": "b", "source": "human"}]}
        errs = " | ".join(herd.validate_task(bad))
        for needle in ("goal", "source", "duplicate", "check"):
            self.assertIn(needle, errs)
        self.assertIn("no criteria", " ".join(herd.validate_task({"goal": "g", "criteria": []})))


class TestVerify(Base):
    def test_verify_records_evidence(self):
        self.task()
        ev = herd.verify(self.root, "t1")
        by = {r["id"]: r for r in ev["results"]}
        self.assertEqual(by["C1"]["status"], "failing")
        self.assertEqual(by["C2"]["status"], "unchecked")
        self.assertEqual(ev["summary"], {"passing": 0, "failing": 1, "unchecked": 1})
        (self.root / "greet.txt").write_text("hello")
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["summary"], {"passing": 1, "failing": 0, "unchecked": 1})
        r = ev["results"][0]
        self.assertEqual((r["exit_code"], r["check"]), (0, "test -f greet.txt"))
        saved = json.loads((self.root / ".herd/tasks/t1/evidence.json").read_text())
        self.assertEqual(saved["summary"], ev["summary"])
        self.assertTrue(saved["head"] and saved["at"] and saved["fingerprint"])

    def test_timeout_is_failing(self):
        self.task(TASK.replace('check = "test -f greet.txt"', 'check = "sleep 5"\ntimeout_s = 1'))
        r = herd.verify(self.root, "t1")["results"][0]
        self.assertEqual(r["status"], "failing")
        self.assertIn("timeout", r["output_tail"])

    def test_output_tail_is_cut(self):
        self.task(TASK.replace('test -f greet.txt', "python3 -c 'print(5000*chr(120))'"))
        r = herd.verify(self.root, "t1")["results"][0]
        self.assertLessEqual(len(r["output_tail"]), herd.TAIL_CHARS)

    def test_dirty_flag_in_evidence_and_report(self):
        self.task()
        ev = herd.verify(self.root, "t1")
        self.assertFalse(ev["dirty"])  # only .herd/ exists, and it is ignored
        self.assertNotIn("uncommitted", herd.report(ev))
        (self.root / "greet.txt").write_text("hello")  # new untracked file counts as uncommitted work
        ev = herd.verify(self.root, "t1")
        self.assertTrue(ev["dirty"])
        self.assertIn("plus uncommitted changes", herd.report(ev))

    def test_report_text(self):
        self.task()
        (self.root / "greet.txt").write_text("hello")
        text = herd.report(herd.verify(self.root, "t1"))
        self.assertIn("C1", text)
        self.assertIn("passing", text)
        self.assertIn("unchecked", text)
        self.assertIn("never counted as met", text)


class TestHygiene(Base):
    def warn(self, check):
        return herd.check_warnings({"criteria": [{"id": "C1", "check": check}]})

    def test_hygiene_flags_vacuous_checks(self):
        for check in ("true", ":", "exit 0", "echo ok", "test -f greet.txt", "test -e greet.txt"):
            self.assertEqual(len(self.warn(check)), 1, check)
            self.assertIn("C1", self.warn(check)[0])

    def test_hygiene_accepts_real_checks_and_empty(self):
        for check in ("python3 -m unittest", "pytest -q", "grep -q hello out.txt && ./run", ""):
            self.assertEqual(self.warn(check), [], check)

    def test_hygiene_cli_prints_warning_and_exits_zero(self):
        self.task(TASK.replace("test -f greet.txt", "true"))
        p = subprocess.run(["python3", str(Path(herd.__file__)), "check"], cwd=self.root,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn("ok", p.stdout)
        self.assertIn("warning: C1", p.stdout)


class TestQuick(Base):
    def test_quick_init_writes_one_criterion(self):
        herd.init_task(self.root, "q1", "Fix a typo in README", quick_check="python3 -m unittest")
        t = herd.load_task(self.root, "q1")
        self.assertEqual(t["route"], "quick")
        self.assertEqual(len(t["criteria"]), 1)
        c = t["criteria"][0]
        self.assertEqual((c["id"], c["source"], c["check"], c["text"]),
                         ("C1", "agent-proposed", "python3 -m unittest", "Fix a typo in README"))
        self.assertEqual(herd.validate_task(t), [])
        self.assertEqual(herd.active_slug(self.root), "q1")

    def test_quick_survives_quotes_in_goal_and_check(self):
        herd.init_task(self.root, "q1", 'Say "hi" \\ there', quick_check="grep -q 'a\"b' f.txt")
        c = herd.load_task(self.root, "q1")["criteria"][0]
        self.assertEqual(c["text"], 'Say "hi" \\ there')

    def test_quick_refuses_empty_check(self):
        with self.assertRaises(ValueError) as cm:
            herd.init_task(self.root, "q1", "goal", quick_check="  ")
        self.assertIn("check", str(cm.exception))
        self.assertFalse((self.root / ".herd/tasks/q1").exists())

    def test_quick_refuses_high_risk_floor(self):
        with self.assertRaises(ValueError) as cm:
            herd.init_task(self.root, "q1", "Rotate tokens in auth/session.py", quick_check=OK)
        self.assertIn("high", str(cm.exception))
        self.assertFalse((self.root / ".herd/tasks/q1").exists())
        self.assertFalse((self.root / ".herd/active").exists())

    def test_quick_uses_project_herd_toml(self):
        (self.root / "herd.toml").write_text('[floor]\nhigh = ["docs/**"]\n')
        with self.assertRaises(ValueError):
            herd.init_task(self.root, "q1", "Edit docs/guide.md", quick_check=OK)
        herd.init_task(self.root, "q2", "Edit auth/x.py", quick_check=OK)  # custom rules replace defaults

    def test_validate_route(self):
        ok = {"goal": "g", "criteria": [{"id": "C1", "text": "t", "source": "human", "check": "true"}]}
        self.assertEqual(herd.validate_task(ok), [])
        self.assertIn("route", " ".join(herd.validate_task({**ok, "route": "fast"})))
        self.assertEqual(herd.validate_task({**ok, "route": "quick"}), [])
        two = {**ok, "route": "quick", "criteria": ok["criteria"] + [dict(ok["criteria"][0], id="C2")]}
        self.assertIn("exactly one", " ".join(herd.validate_task(two)))
        empty = {**ok, "route": "quick", "criteria": [dict(ok["criteria"][0], check="")]}
        self.assertIn("quick", " ".join(herd.validate_task(empty)))

    def test_report_shows_route_and_flow_ends_in_evidence(self):
        herd.init_task(self.root, "q1", "Add greet file", quick_check="test -f greet.txt")
        ev = herd.verify(self.root, "q1")
        self.assertEqual(ev["summary"]["failing"], 1)
        (self.root / "greet.txt").write_text("hi")
        text = herd.report(herd.verify(self.root, "q1"))
        self.assertIn("Route: quick", text)
        self.assertEqual(herd.problems(self.root, "q1"), [])

    def test_cli_quick(self):
        p = subprocess.run(["python3", str(Path(herd.__file__)), "init", "q1", "Fix typo", "--quick", "true"],
                           cwd=self.root, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        p = subprocess.run(["python3", str(Path(herd.__file__)), "init", "q2", "Fix auth/x.py", "--quick", "true"],
                           cwd=self.root, capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn("high", p.stderr)


class TestBudgetAndRed(Base):
    def test_budget_note_in_report_and_validation(self):
        self.task('test_budget = "unit for parsing; not testing the CLI wrapper"\n' + TASK)
        (self.root / "greet.txt").write_text("hello")
        text = herd.report(herd.verify(self.root, "t1"))
        self.assertIn("Test budget: unit for parsing; not testing the CLI wrapper", text)
        t = herd.load_task(self.root, "t1")
        self.assertEqual(herd.validate_task(dict(t, test_budget=3))[0].split(":")[0], "test_budget")

    def test_no_budget_line_when_absent(self):
        self.task()
        self.assertNotIn("Test budget", herd.report(herd.verify(self.root, "t1")))

    def test_red_recorded_on_first_verify_only(self):
        self.task()
        ev = herd.verify(self.root, "t1")  # C1 fails, C2 unchecked
        self.assertEqual((ev["red"]["failed"], ev["red"]["total"]), (1, 1))
        self.assertTrue((self.root / ".herd/tasks/t1/red.json").exists())
        (self.root / "greet.txt").write_text("hello")
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["summary"]["passing"], 1)
        self.assertEqual((ev["red"]["failed"], ev["red"]["total"]), (1, 1))  # still the first run
        self.assertIn("First verify: 1 of 1 checks failed before the work", herd.report(ev))

    def test_green_from_the_start_is_visible(self):
        self.task()
        (self.root / "greet.txt").write_text("hello")
        ev = herd.verify(self.root, "t1")
        self.assertEqual((ev["red"]["failed"], ev["red"]["total"]), (0, 1))
        self.assertIn("First verify: 0 of 1 checks failed before the work", herd.report(ev))

    def test_red_does_not_make_evidence_stale(self):
        self.task(attacks=True)
        (self.root / "greet.txt").write_text("hello")
        herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])


class TestVerbatim(Base):
    REQUEST = "Build a thing.\n\nSuccess: the optimized route saves MORE than 20 percent of the time   vs a random walk."

    def human(self, text, source="human"):
        return {"goal": "g", "criteria": [{"id": "C1", "text": text, "source": source, "check": "python3 -m unittest"}]}

    def test_init_records_request(self):
        herd.init_task(self.root, "t1", "g", request=self.REQUEST)
        self.assertEqual((self.root / ".herd/tasks/t1/request.md").read_text(), self.REQUEST)
        herd.cancel_task(self.root, "t1")
        herd.init_task(self.root, "t2", "g")
        self.assertFalse((self.root / ".herd/tasks/t2/request.md").exists())

    def test_quote_is_accepted_ignoring_case_and_spacing(self):
        task = self.human("the optimized route saves more than 20 percent of the time vs a random walk")
        self.assertEqual(herd.human_unquoted(task, self.REQUEST), [])
        self.assertEqual(herd.check_warnings(task, self.REQUEST), [])

    def test_reworded_or_narrowed_human_criterion_is_flagged(self):
        task = self.human("Given the sample store, when compared over 10 runs, then optimized is more than 20% lower")
        self.assertEqual(herd.human_unquoted(task, self.REQUEST), ["C1"])
        warn = " ".join(herd.check_warnings(task, self.REQUEST))
        self.assertIn("C1", warn)
        self.assertIn("verbatim", warn)

    def test_agent_proposed_criteria_are_not_checked(self):
        task = self.human("Given anything, then something", source="agent-proposed")
        self.assertEqual(herd.human_unquoted(task, self.REQUEST), [])
        self.assertEqual(herd.check_warnings(task, self.REQUEST), [])

    def test_no_request_recorded_warns_for_human_criteria_only(self):
        warn = herd.check_warnings(self.human("anything"), None)
        self.assertTrue(any("no request" in w for w in warn))
        self.assertEqual(herd.check_warnings(self.human("anything", "agent-proposed"), None), [])
        self.assertIsNone(herd.human_unquoted(self.human("anything"), None))

    def test_evidence_and_report_show_unquoted_human_criteria(self):
        herd.init_task(self.root, "t1", "g", request=self.REQUEST)
        (self.root / ".herd/tasks/t1/task.toml").write_text(
            'goal = "g"\n[[criteria]]\nid = "C1"\ntext = "Given a sample, then it is 20% lower"\n'
            'source = "human"\ncheck = "true"\n')
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["human_not_verbatim"], ["C1"])
        self.assertIn("Human criteria not quoted verbatim from the request: C1", herd.report(ev))

    def test_report_is_quiet_when_quoted_or_unknown(self):
        herd.init_task(self.root, "t1", "g", request=self.REQUEST)
        (self.root / ".herd/tasks/t1/task.toml").write_text(
            'goal = "g"\n[[criteria]]\nid = "C1"\ntext = "saves MORE than 20 percent of the time"\n'
            'source = "human"\ncheck = "true"\n')
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["human_not_verbatim"], [])
        self.assertNotIn("verbatim", herd.report(ev))
        herd.cancel_task(self.root, "t1")
        herd.init_task(self.root, "t2", "g")  # no request recorded
        (self.root / ".herd/tasks/t2/task.toml").write_text(
            'goal = "g"\n[[criteria]]\nid = "C1"\ntext = "x"\nsource = "human"\ncheck = "true"\n')
        self.assertIsNone(herd.verify(self.root, "t2")["human_not_verbatim"])

    def test_cli_request_flag_and_check(self):
        run = lambda *a: subprocess.run(["python3", str(Path(herd.__file__)), *a], cwd=self.root,
                                        capture_output=True, text=True)
        self.assertEqual(run("init", "t1", "g", "--request", self.REQUEST).returncode, 0)
        (self.root / ".herd/tasks/t1/task.toml").write_text(
            'goal = "g"\n[[criteria]]\nid = "C1"\ntext = "reworded"\nsource = "human"\ncheck = "python3 -V"\n')
        out = run("check").stdout
        self.assertIn("warning: C1", out)
        self.assertIn("verbatim", out)


class TestCoverageAndLimits(Base):
    def task_with(self, extra_top="", extra_c1="", source="human", check="python3 -V"):
        return (f'{extra_top}goal = "g"\n[[criteria]]\nid = "C1"\ntext = "t"\nsource = "{source}"\n'
                f'check = "{check}"\n{extra_c1}')

    def load(self, text):
        import tomllib
        return tomllib.loads(text)

    def test_coverage_must_be_a_string(self):
        task = self.load(self.task_with(extra_c1='coverage = 3\n'))
        self.assertIn("coverage", " ".join(herd.validate_task(task)))
        self.assertEqual(herd.validate_task(self.load(self.task_with(extra_c1='coverage = "x"\n'))), [])

    def test_known_limits_must_be_a_string(self):
        task = self.load(self.task_with(extra_top='known_limits = 3\n'))
        self.assertIn("known_limits", " ".join(herd.validate_task(task)))

    def test_human_criterion_without_coverage_is_warned(self):
        warn = " ".join(herd.coverage_warnings(self.load(self.task_with())))
        self.assertIn("C1", warn)
        self.assertIn("coverage", warn)
        ok = herd.coverage_warnings(self.load(self.task_with(extra_c1='coverage = "proves X, not Y"\n')))
        self.assertFalse([w for w in ok if "coverage" in w])
        agent = herd.coverage_warnings(self.load(self.task_with(source="agent-proposed")))
        self.assertFalse([w for w in agent if "coverage" in w])

    def test_blank_coverage_counts_as_missing(self):
        warn = herd.coverage_warnings(self.load(self.task_with(extra_c1='coverage = "  "\n')))
        self.assertTrue([w for w in warn if "coverage" in w])

    def test_missing_known_limits_is_warned_on_standard_not_quick(self):
        warn = herd.coverage_warnings(self.load(self.task_with()))
        self.assertTrue([w for w in warn if "known_limits" in w])
        quick = self.load('route = "quick"\n' + self.task_with())
        self.assertFalse([w for w in herd.coverage_warnings(quick) if "known_limits" in w])
        stated = self.load(self.task_with(extra_top='known_limits = "holds on the demo store only"\n'))
        self.assertFalse([w for w in herd.coverage_warnings(stated) if "known_limits" in w])

    def test_report_shows_coverage_and_known_limits(self):
        herd.init_task(self.root, "t1", "g")
        (self.root / ".herd/tasks/t1/task.toml").write_text(self.task_with(
            extra_top='known_limits = "only the demo store; saving varies with basket size"\n',
            extra_c1='coverage = "proves per-stop events, not per-cell steps"\n'))
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["known_limits"], "only the demo store; saving varies with basket size")
        self.assertEqual(ev["results"][0]["coverage"], "proves per-stop events, not per-cell steps")
        text = herd.report(ev)
        self.assertIn("Known limits: only the demo store; saving varies with basket size", text)
        self.assertIn("Coverage of human criteria", text)
        self.assertIn("C1: proves per-stop events, not per-cell steps", text)

    def test_report_is_quiet_without_them(self):
        self.task()
        text = herd.report(herd.verify(self.root, "t1"))
        self.assertNotIn("Known limits", text)
        self.assertNotIn("Coverage of human criteria", text)

    def test_agent_proposed_coverage_is_not_listed_under_human_heading(self):
        herd.init_task(self.root, "t1", "g")
        (self.root / ".herd/tasks/t1/task.toml").write_text(
            self.task_with(source="agent-proposed", extra_c1='coverage = "internal"\n'))
        self.assertNotIn("Coverage of human criteria", herd.report(herd.verify(self.root, "t1")))


class TestQuantifierWarnings(Base):
    def warn(self, text, coverage="x", source="human"):
        task = {"goal": "g", "route": "quick", "criteria": [{"id": "C1", "text": text, "source": source,
                                                              "check": "python3 -V", "coverage": coverage}]}
        return herd.coverage_warnings(task)

    def test_any_with_a_coverage_that_names_no_variation_is_warned(self):
        out = self.warn("Works for any supermarket", "proves one demo store")
        self.assertEqual(len(out), 1)
        self.assertIn("any", out[0])
        self.assertIn("what varies", out[0])

    def test_coverage_that_names_the_variation_is_accepted(self):
        for cov in ("checked on generated layouts from several families and random ones", "random seeds, 100 inputs",
                    "property test over arbitrary inputs", "fuzz of many sizes"):
            self.assertEqual(self.warn("Works for any supermarket", cov), [], cov)
        # 0.4.1: families the agent designs vary the input but share the code's blind spots
        out = self.warn("Works for any supermarket", "checked on generated layouts from several families")
        self.assertEqual(len(out), 1)
        self.assertIn("names no random inputs", out[0])

    def test_each_quantifier_word_triggers(self):
        for word in ("any", "every", "whatever", "whichever", "many", "each", "arbitrary"):
            self.assertEqual(len(self.warn(f"It works for {word} case", "one example")), 1, word)

    def test_words_inside_other_words_do_not_trigger(self):
        for text in ("The company ships a manyfold report", "Eachother and anyway", "It is wall-clock timed"):
            self.assertEqual(self.warn(text, "one example"), [], text)

    def test_scale_words_need_a_scale_statement(self):
        out = self.warn("Handles very big stores quickly", "demo store, 40 products")
        self.assertEqual(len(out), 1)
        self.assertIn("scale", out[0])
        for cov in ("scale tiers up to 600x400 with a time limit", "largest input timed at 20 seconds",
                    "performance measured for size n up to 10000"):
            self.assertEqual(self.warn("Handles very big stores quickly", cov), [], cov)

    def test_both_kinds_give_two_warnings(self):
        self.assertEqual(len(self.warn("Works for any layout, even huge ones", "one demo store")), 2)

    def test_blank_coverage_gives_only_the_missing_coverage_warning(self):
        out = self.warn("Works for any layout, even huge ones", "  ")
        self.assertEqual(len(out), 1)
        self.assertIn("no `coverage`", out[0])

    def test_agent_proposed_and_plain_criteria_are_ignored(self):
        self.assertEqual(self.warn("Works for any layout", "x", source="agent-proposed"), [])
        self.assertEqual(self.warn("Prints a greeting", "one example"), [])


class TestNotes(Base):
    def at(self, hhmmss):
        return mock.patch.object(herd, "now", return_value=f"2026-11-22T{hhmmss}Z")

    def start(self):
        with self.at("10:00:00"):
            self.task()

    def test_add_note_appends_a_line_with_time(self):
        self.start()
        with self.at("10:01:40"):
            herd.add_note(self.root, "t1", "found", "unreachable pocket crashes the planner")
        with self.at("10:03:00"):
            herd.add_note(self.root, "t1", "fixed", "ignore cells with distance -1")
        notes = herd.load_notes(self.root, "t1")
        self.assertEqual([n["kind"] for n in notes], ["found", "fixed"])
        self.assertEqual((notes[0]["text"], notes[0]["elapsed_s"]), ("unreachable pocket crashes the planner", 100))
        self.assertEqual(notes[1]["at"], "2026-11-22T10:03:00Z")

    def test_bad_kind_and_empty_text_are_rejected(self):
        self.start()
        with self.assertRaises(ValueError):
            herd.add_note(self.root, "t1", "bug", "x")
        with self.assertRaises(ValueError):
            herd.add_note(self.root, "t1", "found", "   ")
        self.assertEqual(herd.load_notes(self.root, "t1"), [])

    def test_notes_without_a_start_file_have_no_elapsed(self):
        self.task()
        (self.root / ".herd/tasks/t1/started").unlink()
        herd.add_note(self.root, "t1", "open", "only tested on one store")
        self.assertIsNone(herd.load_notes(self.root, "t1")[0]["elapsed_s"])

    def test_report_lists_caveats_with_times_and_counts(self):
        self.start()
        with self.at("10:01:40"):
            herd.add_note(self.root, "t1", "found", "pockets crash")
        with self.at("10:03:00"):
            herd.add_note(self.root, "t1", "fixed", "pockets handled")
        herd.add_note(self.root, "t1", "open", "slow above 600x400")
        (self.root / "greet.txt").write_text("hello")
        with self.at("10:04:16"):
            text = herd.report(herd.verify(self.root, "t1"))
        self.assertIn("Caveats during the run: 1 found, 1 fixed, 1 open", text)
        self.assertIn("- 1m 40s found: pockets crash", text)
        self.assertIn("- 3m 00s fixed: pockets handled", text)
        self.assertIn("open: slow above 600x400", text)

    def test_adversarial_pass_line(self):
        self.start()
        text = herd.report(herd.verify(self.root, "t1"))
        self.assertIn("Adversarial pass: not recorded", text)
        herd.add_note(self.root, "t1", "tried", "8 layout families at 3 sizes")
        text = herd.report(herd.verify(self.root, "t1"))
        self.assertIn("Adversarial pass: 1 attempt recorded; missing: bad-input, collision", text)
        self.assertNotIn("not recorded", text)
        self.attacks()
        text = herd.report(herd.verify(self.root, "t1"))
        self.assertIn("Adversarial pass: 5 attempts recorded; bad-input passing (`", text)
        self.assertIn("; collision passing (`", text)
        self.assertNotIn("missing", text)

    def test_quick_route_has_no_adversarial_line(self):
        herd.init_task(self.root, "q1", "Fix a typo", quick_check="python3 -V")
        self.assertNotIn("Adversarial", herd.report(herd.verify(self.root, "q1")))

    def raw_notes(self, rows):
        import json
        d = self.root / ".herd/tasks/t1/notes.jsonl"
        d.write_text("".join(json.dumps({"at": at, "kind": k, "text": f"n{i}", "elapsed_s": el}) + "\n"
                             for i, (at, k, el) in enumerate(rows)))

    def report_text(self):
        self.start()
        (self.root / "greet.txt").write_text("hello")
        return herd.report(herd.verify(self.root, "t1"))

    def test_notes_logged_in_one_batch_are_flagged(self):
        self.start()
        self.raw_notes([("2026-11-22T10:02:38Z", "tried", 158), ("2026-11-22T10:02:38Z", "found", 158),
                        ("2026-11-22T10:02:38Z", "fixed", 158), ("2026-11-22T10:02:39Z", "open", 159)])
        (self.root / "greet.txt").write_text("hello")
        text = herd.report(herd.verify(self.root, "t1"))
        self.assertIn("4 notes were logged within 5 s of each other", text)
        self.assertIn("times show when they were written, not when found", text)

    def test_spread_out_notes_are_not_flagged(self):
        self.start()
        self.raw_notes([("2026-11-22T10:01:00Z", "found", 60), ("2026-11-22T10:02:00Z", "fixed", 120),
                        ("2026-11-22T10:03:00Z", "open", 180)])
        (self.root / "greet.txt").write_text("hello")
        self.assertNotIn("logged within", herd.report(herd.verify(self.root, "t1")))

    def test_two_close_notes_are_not_a_batch(self):
        self.start()
        self.raw_notes([("2026-11-22T10:02:38Z", "found", 158), ("2026-11-22T10:02:39Z", "fixed", 159)])
        (self.root / "greet.txt").write_text("hello")
        self.assertNotIn("logged within", herd.report(herd.verify(self.root, "t1")))

    def test_batch_is_found_inside_a_longer_log(self):
        self.start()
        self.raw_notes([("2026-11-22T10:00:30Z", "found", 30), ("2026-11-22T10:03:00Z", "tried", 180),
                        ("2026-11-22T10:03:02Z", "found", 182), ("2026-11-22T10:03:04Z", "fixed", 184)])
        (self.root / "greet.txt").write_text("hello")
        self.assertIn("3 notes were logged within 5 s of each other", herd.report(herd.verify(self.root, "t1")))

    def test_skill_tells_agents_to_log_each_note_when_found(self):
        text = (Path(herd.__file__).parent.parent / "skills" / "run" / "SKILL.md").read_text()
        self.assertIn("the moment it happens", text)
        self.assertIn("Notes logged together are flagged", text)

    def test_notes_are_in_evidence_and_do_not_make_it_stale(self):
        self.task(attacks=True)
        herd.add_note(self.root, "t1", "found", "x")
        (self.root / "greet.txt").write_text("hello")
        ev = herd.verify(self.root, "t1")
        self.assertIn("x", [n["text"] for n in ev["notes"]])
        herd.add_note(self.root, "t1", "fixed", "y")
        self.assertEqual(herd.problems(self.root, "t1"), [])

    def test_notes_added_after_the_last_verify_still_reach_done_and_status(self):
        run = lambda *a: subprocess.run(["python3", str(Path(herd.__file__)), *a], cwd=self.root,
                                        capture_output=True, text=True)
        self.task(attacks=True)
        (self.root / "greet.txt").write_text("hello")
        self.assertEqual(run("verify").returncode, 0)
        self.assertEqual(run("note", "--found", "late finding").returncode, 0)
        self.assertIn("late finding", run("status").stdout)
        done = run("done")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("late finding", (self.root / ".herd/tasks/t1/evidence.md").read_text())

    def test_cli_note_flags(self):
        run = lambda *a: subprocess.run(["python3", str(Path(herd.__file__)), *a], cwd=self.root,
                                        capture_output=True, text=True)
        self.task()
        for flag, kind in (("--found", "found"), ("--fixed", "fixed"), ("--open", "open"), ("--tried", "tried")):
            p = run("note", flag, f"a {kind} note")
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn(kind, p.stdout)
        self.assertEqual([n["kind"] for n in herd.load_notes(self.root, "t1")], ["found", "fixed", "open", "tried"])
        self.assertEqual(run("note", "--found").returncode, 1)          # no text
        self.assertEqual(run("note", "just text").returncode, 1)        # no kind flag
        self.assertEqual(run("note", "--bogus", "x").returncode, 1)


class TestSlugFallback(Base):
    def run_cli(self, *args):
        return subprocess.run(["python3", str(Path(herd.__file__)), *args], cwd=self.root,
                              capture_output=True, text=True)

    def finish_one(self, slug="t1"):
        herd.init_task(self.root, slug, "g")
        (self.root / f".herd/tasks/{slug}/task.toml").write_text(TASK)
        self.attacks(slug)
        (self.root / "greet.txt").write_text("hello")
        self.assertEqual(self.run_cli("verify", slug).returncode, 0)
        self.assertEqual(self.run_cli("done", slug).returncode, 0)

    def test_single_task_is_used_when_none_is_active(self):
        self.finish_one()
        self.assertFalse((self.root / ".herd/active").exists())
        p = self.run_cli("status")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("Evidence: t1", p.stdout)
        self.assertEqual(self.run_cli("verify").returncode, 0)

    def test_gate_does_not_treat_a_finished_task_as_active(self):
        self.finish_one()
        self.assertIsNone(herd.gate(self.root, {}))

    def test_several_tasks_and_none_active_is_still_an_error(self):
        self.finish_one("t1")
        herd.init_task(self.root, "t2", "g")
        (self.root / ".herd/active").unlink()
        p = self.run_cli("status")
        self.assertEqual(p.returncode, 1)
        self.assertIn("t1", p.stderr)
        self.assertIn("t2", p.stderr)

    def test_no_tasks_is_an_error(self):
        p = self.run_cli("status")
        self.assertEqual(p.returncode, 1)
        self.assertIn("herd init", p.stderr)


class TestTiming(Base):
    def at(self, hhmmss):
        return mock.patch.object(herd, "now", return_value=f"2026-11-22T{hhmmss}Z")

    def test_duration_format(self):
        for secs, text in ((0, "0s"), (45, "45s"), (71, "1m 11s"), (256, "4m 16s"), (3600, "1h 00m 00s"),
                           (3731, "1h 02m 11s")):
            self.assertEqual(herd.fmt_duration(secs), text)

    def test_init_records_start_time(self):
        with self.at("10:00:00"):
            herd.init_task(self.root, "t1", "g")
        self.assertEqual((self.root / ".herd/tasks/t1/started").read_text().strip(), "2026-11-22T10:00:00Z")
        herd.cancel_task(self.root, "t1")
        with self.at("10:00:05"):
            herd.init_task(self.root, "q1", "g", quick_check=OK)
        self.assertTrue((self.root / ".herd/tasks/q1/started").exists())

    def test_evidence_carries_elapsed_and_first_verify_time(self):
        with self.at("10:00:00"):
            self.task()
        with self.at("10:01:11"):
            ev = herd.verify(self.root, "t1")  # first verify
        self.assertEqual(ev["timing"], {"started_at": "2026-11-22T10:00:00Z", "elapsed_s": 71, "first_verify_s": 71})
        (self.root / "greet.txt").write_text("hello")
        with self.at("10:04:16"):
            ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["timing"]["elapsed_s"], 256)
        self.assertEqual(ev["timing"]["first_verify_s"], 71)  # fixed by the first run
        text = herd.report(ev)
        self.assertIn("Elapsed: 4m 16s from herd init to this verify; first verify at 1m 11s", text)
        self.assertIn("wall clock", text)

    def test_task_without_start_file_has_no_timing(self):
        self.task()
        (self.root / ".herd/tasks/t1/started").unlink()
        ev = herd.verify(self.root, "t1")
        self.assertIsNone(ev["timing"])
        self.assertNotIn("Elapsed", herd.report(ev))

    def test_all_unchecked_has_elapsed_but_no_first_verify(self):
        with self.at("10:00:00"):
            herd.init_task(self.root, "t1", "g")
        (self.root / ".herd/tasks/t1/task.toml").write_text(
            'goal = "g"\n[[criteria]]\nid = "C1"\ntext = "t"\nsource = "human"\ncheck = ""\n')
        with self.at("10:02:00"):
            ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["timing"], {"started_at": "2026-11-22T10:00:00Z", "elapsed_s": 120})
        self.assertNotIn("first verify at", herd.report(ev))

    def test_timing_does_not_make_evidence_stale(self):
        self.task(attacks=True)
        (self.root / "greet.txt").write_text("hello")
        herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])


class TestDetectCli(Base):
    def test_detect_prints_json(self):
        (self.root / "Cargo.toml").write_text("")
        p = subprocess.run(["python3", str(Path(herd.__file__)), "detect"], cwd=self.root,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout)[0]["type"], "rust")

    def test_detect_empty_repo(self):
        p = subprocess.run(["python3", str(Path(herd.__file__)), "detect"], cwd=self.root,
                           capture_output=True, text=True)
        self.assertEqual(json.loads(p.stdout), [])


class TestGate(Base):
    def gate(self, **hook):
        return herd.gate(self.root, hook)

    def test_no_active_task_allows(self):
        self.assertIsNone(self.gate())

    def test_blocks_without_evidence(self):
        self.task()
        out = self.gate()
        self.assertEqual(out["decision"], "block")
        self.assertIn("herd verify", out["reason"])

    def test_blocks_failing_then_asks_for_herd_done_when_passing(self):
        self.task(attacks=True)
        herd.verify(self.root, "t1")
        self.assertIn("C1", self.gate()["reason"])
        (self.root / "greet.txt").write_text("hello")
        herd.verify(self.root, "t1")
        self.assertIn("herd.py done", self.gate()["reason"])  # passing: only `herd done` ends the task

    def test_blocks_stale_evidence(self):
        self.task(attacks=True)
        (self.root / "greet.txt").write_text("hello")
        herd.verify(self.root, "t1")
        self.assertIn("evidence passes", self.gate()["reason"])
        (self.root / "greet.txt").write_text("changed")  # workspace changed after verify
        self.assertIn("stale", self.gate()["reason"])
        herd.verify(self.root, "t1")
        (self.root / ".herd/tasks/t1/task.toml").write_text(TASK + "\n# edit\n")
        self.assertIn("stale", self.gate()["reason"])

    def test_no_passing_criterion_blocks(self):
        self.task('goal = "g"\n\n[[criteria]]\nid = "C1"\ntext = "t"\nsource = "human"\ncheck = ""\n')
        herd.verify(self.root, "t1")
        self.assertIn("no passing", self.gate()["reason"])

    def test_circuit_breaker_after_three_blocks(self):
        self.task()
        for _ in range(herd.MAX_BLOCKS):
            self.assertEqual(self.gate()["decision"], "block")
        self.assertIsNone(self.gate())  # allows, so a stuck agent can stop and escalate

    def test_block_counter_resets_when_passing(self):
        self.task(attacks=True)
        self.gate()
        (self.root / "greet.txt").write_text("hello")
        herd.verify(self.root, "t1")
        self.assertIn("evidence passes", self.gate()["reason"])
        self.assertFalse((self.root / ".herd/tasks/t1/gate_blocks").exists())
        self.assertEqual(self.run_done(), 0)  # `herd done` ends it
        self.assertIsNone(self.gate())

    def test_a_passing_task_that_done_refuses_never_traps_the_agent(self):
        (self.root / "herd.toml").write_text("[pr]\nopen = true\n")
        git(self.root, "add", "herd.toml")
        git(self.root, "commit", "-q", "-m", "prs on")
        self.task(attacks=True)
        (self.root / "greet.txt").write_text("hello")  # verified, but not committed, and the agent may not commit
        herd.verify(self.root, "t1")
        for _ in range(herd.MAX_BLOCKS):
            out = self.gate()
            self.assertIn("Commit first", out["reason"])
        self.assertNotEqual(self.run_done(), 0)
        self.assertIsNone(self.gate())  # after MAX_BLOCKS it lets the agent stop and say why

    def run_done(self):
        return subprocess.run(["python3", str(Path(herd.__file__)), "done"], cwd=self.root,
                              capture_output=True, text=True).returncode


class TestCli(Base):
    def run_cli(self, *args):
        p = subprocess.run(["python3", str(Path(herd.__file__)), *args], cwd=self.root,
                           capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr

    def test_flow(self):
        rc, out, _ = self.run_cli("init", "t1", "Add a greeting")
        self.assertEqual(rc, 0)
        (self.root / ".herd/tasks/t1/task.toml").write_text(TASK)
        self.assertEqual(self.run_cli("check")[0], 0)
        for a in herd.ATTACKS:
            self.assertEqual(self.run_cli("note", "--tried", "--attack", a, "--check", OK, f"{a} attack")[0], 0)
        self.assertEqual(self.run_cli("verify")[0], 1)  # C1 failing
        (self.root / "greet.txt").write_text("hello")
        rc, out, _ = self.run_cli("verify")
        self.assertEqual(rc, 0)
        self.assertIn("1 passing", out)
        self.assertEqual(self.run_cli("review", "--by", "a fresh subagent", "no Blocker or Major")[0], 0)
        rc, out, _ = self.run_cli("done")
        self.assertEqual(rc, 0)
        self.assertFalse((self.root / ".herd/active").exists())
        self.assertTrue((self.root / ".herd/tasks/t1/evidence.md").exists())
        self.assertIn("done: evidence is fresh and passing", out)

    def test_done_refuses_when_not_passing(self):
        self.run_cli("init", "t1", "g")
        (self.root / ".herd/tasks/t1/task.toml").write_text(TASK)
        self.run_cli("verify")
        rc, _, err = self.run_cli("done")
        self.assertEqual(rc, 1)
        self.assertTrue((self.root / ".herd/active").exists())

    def test_gate_reads_hook_json_from_stdin(self):
        self.run_cli("init", "t1", "g")
        (self.root / ".herd/tasks/t1/task.toml").write_text(TASK)
        p = subprocess.run(["python3", str(Path(herd.__file__)), "gate"], cwd=self.root,
                           input=json.dumps({"cwd": str(self.root)}), capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout)["decision"], "block")

    def test_triage(self):
        rc, out, _ = self.run_cli("triage", "Change auth/session.py to rotate tokens", "--json")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["risk"]["floor"], "high")

    def test_missing_arguments_print_usage(self):
        for args, usage in ((["init"], "herd init <slug>"), (["init", "t1", "g", "--quick"], "herd init <slug>"),
                            (["note", "text"], "herd note --found"), (["cancel", "--reason"], "herd cancel")):
            rc, _, err = self.run_cli(*args)
            self.assertEqual(rc, 1, args)
            self.assertIn(f"usage: {usage}", err)

    def test_help_and_unknown_command(self):
        rc, out, _ = self.run_cli("help")
        self.assertEqual(rc, 0)
        self.assertIn("herd cancel", out)
        rc, _, err = self.run_cli("frobnicate")
        self.assertEqual(rc, 2)
        self.assertIn("unknown command `frobnicate`", err)


class TestCancel(Base):
    def test_cancel_stops_the_gate_and_keeps_the_record(self):
        self.task()
        self.assertEqual(herd.gate(self.root, {})["decision"], "block")
        herd.cancel_task(self.root, "t1", "the human changed their mind")
        self.assertIsNone(herd.gate(self.root, {}))
        self.assertFalse((self.root / ".herd/active").exists())
        self.assertFalse((self.root / ".herd/tasks/t1/gate_blocks").exists())
        self.assertTrue((self.root / ".herd/tasks/t1/task.toml").exists())
        self.assertEqual(herd.cancelled(self.root, "t1")["reason"], "the human changed their mind")

    def test_gate_ignores_a_cancelled_task_even_if_marked_active(self):
        self.task()
        herd.cancel_task(self.root, "t1")
        (self.root / ".herd/active").write_text("t1\n")
        self.assertIsNone(herd.gate(self.root, {}))

    def test_cancel_unknown_task_fails(self):
        with self.assertRaises(ValueError):
            herd.cancel_task(self.root, "nope")

    def test_cli_cancel_and_status(self):
        run = lambda *a: subprocess.run(["python3", str(Path(herd.__file__)), *a], cwd=self.root,
                                        capture_output=True, text=True)
        run("init", "t1", "g")
        p = run("cancel", "--reason", "superseded")
        self.assertEqual(p.returncode, 0, p.stderr)
        p = run("status")
        self.assertIn("cancelled at", p.stdout)
        self.assertIn("superseded", p.stdout)


class TestZeroTests(Base):
    ZERO = {
        "unittest": "\n----------------------------------------------------------------------\nRan 0 tests in 0.000s\n\nOK\n",
        "pytest": "============ no tests ran in 0.01s ============\n",
        "pytest collect": "collected 0 items\n",
        "cargo": "   Compiling x v0.1.0\n    Finished\n     Running unittests\n\nrunning 0 tests\n\n"
                 "test result: ok. 0 passed; 0 failed; 0 ignored\n",
        "go": "?   \texample.com/x\t[no test files]\n?   \texample.com/x/y\t[no test files]\n",
        "go with a -run filter matching nothing": "?   \texample.com/x\t[no test files]\n"
                                                  "ok  \texample.com/x/y\t0.221s [no tests to run]\n",
        "jest": "No tests found, exiting with code 0\n",
        "mocha": "\n\n  0 passing (2ms)\n\n",
    }
    SOME = {
        "unittest": "....\n----------------------------------------------------------------------\nRan 4 tests in 0.01s\n\nOK\n",
        "pytest": "collected 3 items\n\ntest_x.py ...\n============ 3 passed in 0.02s ============\n",
        "cargo with empty doc-tests": "running 12 tests\n............\ntest result: ok. 12 passed; 0 failed\n\n"
                                      "   Doc-tests x\n\nrunning 0 tests\n\ntest result: ok. 0 passed; 0 failed\n",
        "go with some empty packages": "?   \texample.com/x\t[no test files]\nok  \texample.com/x/y\t0.012s\n",
        "jest": "Tests:       5 passed, 5 total\n",
        "mocha": "\n  7 passing (40ms)\n",
        "no runner output": "built ok\n",
        "go cached": "ok  \texample.com/x/y\t(cached)\n?   \texample.com/x\t[no test files]\n",
    }

    def test_a_stray_ok_line_does_not_hide_an_empty_run(self):
        self.assertTrue(herd.ran_zero_tests("ok\nRan 0 tests in 0.0s\nOK\n"))
        self.assertTrue(herd.ran_zero_tests("ok 1 - lint clean\nNo tests found, exiting with code 0\n"))

    def test_real_unittest_with_no_tests(self):
        # Python 3.11 exits 0 on an empty run, so Herd must flag it; 3.12+ exits 5, so the check fails instead
        (self.root / "empty").mkdir()
        self.task(f"{shlex.quote(sys.executable)} -m unittest discover -s empty")
        r = herd.verify(self.root, "t1")["results"][0]
        if sys.version_info < (3, 12):
            self.assertEqual((r["status"], r["zero_tests"]), ("passing", True))
        else:
            self.assertEqual((r["status"], r["zero_tests"]), ("failing", False))

    def test_zero_test_output_is_detected_for_each_runner(self):
        for name, out in self.ZERO.items():
            self.assertTrue(herd.ran_zero_tests(out), name)

    def test_normal_and_mixed_output_is_not_flagged(self):
        for name, out in self.SOME.items():
            self.assertFalse(herd.ran_zero_tests(out), name)

    def task(self, check):
        herd.init_task(self.root, "t1", "Add a greeting")
        (self.root / ".herd/tasks/t1/task.toml").write_text(
            TASK.replace('check = "test -f greet.txt"', f"check = {json.dumps(check)}"))

    def test_verify_flags_a_passing_check_that_ran_zero_tests(self):
        self.task("python3 -c \"print('Ran 0 tests in 0.000s'); print('OK')\"")
        ev = herd.verify(self.root, "t1")
        r = ev["results"][0]
        self.assertEqual((r["status"], r["zero_tests"]), ("passing", True))
        self.assertIn("C1 passed but ran zero tests", herd.report(ev))

    def test_a_failing_check_is_not_flagged(self):
        self.task("python3 -c \"print('Ran 0 tests'); raise SystemExit(5)\"")
        r = herd.verify(self.root, "t1")["results"][0]
        self.assertEqual((r["status"], r["zero_tests"]), ("failing", False))

    def test_the_full_output_is_scanned_not_only_the_tail(self):
        # tests ran early on; only the tail shows an empty suite: not a zero-test run
        self.task(f"python3 -c \"print('Ran 5 tests'); print({herd.TAIL_CHARS * 2}*'x'); print('running 0 tests')\"")
        r = herd.verify(self.root, "t1")["results"][0]
        self.assertNotIn("Ran 5", r["output_tail"])
        self.assertFalse(r["zero_tests"])

    def test_done_is_unchanged_and_report_is_quiet_without_it(self):
        self.task("python3 -c \"print('Ran 0 tests'); print('OK')\"")
        self.attacks()
        herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])  # advisory: the gate does not block on it
        p = subprocess.run(["python3", str(Path(herd.__file__)), "done"], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        (self.root / ".herd/tasks/t1/task.toml").write_text(TASK.replace("test -f greet.txt", "test -n x"))
        self.assertNotIn("zero tests", herd.report(herd.verify(self.root, "t1")))

    def test_cli_verify_marks_the_line(self):
        self.task("python3 -c \"print('collected 0 items')\"")
        p = subprocess.run(["python3", str(Path(herd.__file__)), "verify"], cwd=self.root,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn("C1 passing (ran zero tests)", p.stdout)


class TestAttacks(Base):
    """On the standard route `herd done` needs a recorded attempt for each standard attack."""

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(Path(herd.__file__)), *args], cwd=self.root,
                              capture_output=True, text=True)

    def test_done_and_gate_refuse_until_every_attack_is_recorded(self):
        self.task()
        (self.root / "greet.txt").write_text("hello")
        herd.verify(self.root, "t1")
        probs = " ".join(herd.problems(self.root, "t1"))
        for a in herd.ATTACKS:
            self.assertIn(a, probs)
        self.assertIn("never a traceback", probs)  # the gate itself teaches the attacks
        self.assertEqual(herd.gate(self.root, {})["decision"], "block")
        self.assertEqual(self.run_cli("done").returncode, 1)
        herd.add_note(self.root, "t1", "tried", "fed it a malformed map", attack="bad-input", check=OK)
        herd.add_note(self.root, "t1", "tried", "an unscoped attempt")  # no --attack: counts for none
        herd.verify(self.root, "t1")
        probs = " ".join(herd.problems(self.root, "t1"))
        self.assertNotIn("bad-input", probs)
        self.assertIn("collision", probs)
        for a in ("collision", "one-bad-part", "recount"):
            self.assertEqual(self.run_cli("note", "--tried", "--attack", a, f"n/a: {a} explained").returncode, 0)
        self.assertEqual(self.run_cli("review", "--skipped", "no reviewer in this test").returncode, 0)
        herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])
        self.assertEqual(self.run_cli("done").returncode, 0)

    def test_quick_route_needs_no_attacks(self):
        herd.init_task(self.root, "q1", "Fix typo", quick_check=OK)
        herd.verify(self.root, "q1")
        self.assertEqual(herd.problems(self.root, "q1"), [])

    def test_attack_flag_is_validated(self):
        self.task()
        self.assertEqual(self.run_cli("note", "--tried", "--attack", "bogus", "x").returncode, 1)
        self.assertEqual(self.run_cli("note", "--found", "--attack", "recount", "x").returncode, 1)
        self.assertEqual(self.run_cli("note", "--tried", "--attack").returncode, 1)
        self.assertEqual(herd.load_notes(self.root, "t1"), [])

    def test_attacks_match_the_skill(self):
        text = (Path(herd.__file__).parent.parent / "skills/run/adversarial.md").read_text()
        for a in herd.ATTACKS:
            self.assertIn(f"--attack {a}", text)


class TestSimplifiedAdversarial(Base):
    """Each rule of the adversarial pass is written once; the gate keeps all four attacks."""
    def setUp(self):
        super().setUp()
        self.skill = (SKILLS / "run/SKILL.md").read_text()
        self.adv = (SKILLS / "run/adversarial.md").read_text()

    def step6(self):
        return self.skill.split("6. **Break it**", 1)[1].split("\n7. ", 1)[0]

    def test_step6_points_to_the_file_without_an_inline_list(self):
        s = self.step6()
        self.assertIn("[adversarial.md](adversarial.md)", s)
        self.assertIn("herd done", s)
        self.assertIn("four standard attacks", s)
        for inline in ("bad input at every entry point", "collision", "one bad part", "recount"):
            self.assertNotIn(inline, s.lower())
        self.assertNotIn("regression test", s)  # written once, in adversarial.md step 5
        self.assertIn("regression test", self.adv)

    def test_logging_rule_is_written_once(self):
        # it applies to every step, so its one home is the run skill's Rules
        rules = self.skill.split("## Rules", 1)[1]
        self.assertIn("the moment it happens, in any step", rules)
        self.assertIn("Notes logged together are flagged", rules)
        texts = [p.read_text() for p in SKILLS.glob("*/*.md")]
        for phrase in ("the moment it happens", "the moment you find", "Notes logged together", "never in a batch",
                       "one call at a time"):
            self.assertLessEqual(sum(x.count(phrase) for x in texts), 1, phrase)
        self.assertIn("as the run skill's Rules say", self.adv)

    def test_extremes_do_not_repeat_bad_input(self):
        step1, rest = self.adv.split("\n1. ", 1)[1].split("\n2. ", 1)
        self.assertNotIn("empty", step1)
        self.assertNotIn("malformed", step1)
        for kept in ("huge", "degenerate", "disconnected", "scale run"):
            self.assertIn(kept, step1)
        bad = rest.split("--attack bad-input", 1)[1].split("\n", 1)[0]
        self.assertIn("malformed", bad)
        self.assertIn("empty", bad)

    def test_one_bad_part_names_both_cases(self):
        # a benchmark run applied it to a requested product and silently skipped it
        rule = self.adv.split("--attack one-bad-part", 1)[1].split("\n", 1)[0]
        self.assertIn("does not ask for must not reject the whole input", rule)
        self.assertIn("a requested entry that is broken or unreachable must still fail with a clear message", rule)

    def test_existing_test_counts_only_if_it_meets_the_attack_rule(self):
        self.assertIn("counts for an attack only if it meets that attack's rule above", self.adv)
        self.assertIn("separate code for recount", self.adv)
        self.assertIn("every entry point for bad-input", self.adv)
        self.assertIn("Give that test as the `--check` and say what it covers", self.adv)
        self.assertNotIn("instead of probing again", self.adv)


class TestTaskBranch(Base):
    """A plain `herd init` puts the work on its own branch herd/<slug>, cut from the current one."""

    def cli(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(Path(herd.__file__)), *args], cwd=cwd or self.root,
                              capture_output=True, text=True)

    def branch(self, root=None):
        return subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root or self.root,
                              capture_output=True, text=True).stdout.strip()

    def test_init_switches_to_a_new_branch_and_records_the_base(self):
        start = self.branch()
        (self.root / "README.md").write_text("edited, not committed")
        p = self.cli("init", "t1", "g")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.branch(), "herd/t1")
        self.assertIn(f"cut from {start}", p.stdout)
        self.assertEqual((self.root / ".herd/tasks/t1/base").read_text().strip(), start)  # herd pr targets it
        self.assertEqual((self.root / "README.md").read_text(), "edited, not committed")  # nothing lost

    def test_already_on_the_task_branch_stays_there(self):
        git(self.root, "switch", "-q", "-c", "herd/t1")
        p = self.cli("init", "t1", "g")
        self.assertEqual((p.returncode, self.branch()), (0, "herd/t1"))
        self.assertNotIn("switched", p.stdout)
        self.assertFalse((self.root / ".herd/tasks/t1/base").exists())

    def test_existing_branch_or_detached_head_warns_and_keeps_the_task(self):
        git(self.root, "branch", "herd/t1")
        p = self.cli("init", "t1", "g")
        self.assertEqual(p.returncode, 0)
        self.assertIn("could not create branch herd/t1", p.stderr)
        self.assertTrue((self.root / ".herd/tasks/t1/task.toml").exists())
        herd.cancel_task(self.root, "t1")
        git(self.root, "switch", "-q", "--detach")
        p = self.cli("init", "t2", "g")
        self.assertEqual(p.returncode, 0)
        self.assertIn("detached", p.stderr)

    def test_no_commit_yet_or_no_git_warns_or_does_nothing(self):
        fresh = Path(tempfile.mkdtemp())
        try:
            p = self.cli("init", "t1", "g", cwd=fresh)  # not a git repository
            self.assertEqual((p.returncode, p.stderr), (0, ""))
            git(fresh, "init", "-q")
            herd.cancel_task(fresh, "t1")
            p = self.cli("init", "t2", "g", cwd=fresh)  # no commit yet
            self.assertEqual(p.returncode, 0)
            self.assertIn("no commit yet", p.stderr)
        finally:
            shutil.rmtree(fresh, ignore_errors=True)

    def test_a_refused_init_does_not_switch(self):
        start = self.branch()
        self.cli("init", "t1", "g")
        git(self.root, "switch", "-q", start)
        p = self.cli("init", "t2", "g")  # t1 still active
        self.assertEqual(p.returncode, 1)
        self.assertEqual(self.branch(), start)


class TestAttackChecks(Base):
    """Each standard attack names a command; herd verify runs it; the gate counts only passing ones."""

    def cli(self, *args):
        return subprocess.run([sys.executable, str(Path(herd.__file__)), *args], cwd=self.root,
                              capture_output=True, text=True)

    def ready(self):
        self.task()
        late_review(self.root)  # these tests are about attacks
        (self.root / "greet.txt").write_text("hello")

    def test_attack_needs_a_command(self):
        self.ready()
        for a in herd.ATTACKS:  # each of the four attacks
            p = self.cli("note", "--tried", "--attack", a, "tried it")
            self.assertEqual(p.returncode, 1, a)
            self.assertIn("--check", p.stderr)
        self.assertEqual([n for n in herd.load_notes(self.root, "t1") if n["kind"] != "review"], [])
        p = self.cli("note", "--tried", "--attack", "bad-input", "--check", "test -f greet.txt", "malformed map")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(herd.load_notes(self.root, "t1")[-1]["check"], "test -f greet.txt")
        self.assertEqual(self.cli("note", "--found", "--check", OK, "x").returncode, 1)  # only with --attack
        self.assertEqual(self.cli("note", "--tried", "--attack", "recount", "--check", " ", "x").returncode, 1)

    def test_verify_runs_attack_commands(self):
        self.ready()
        herd.add_note(self.root, "t1", "tried", "ok one", attack="bad-input", check="echo checked; exit 0")
        herd.add_note(self.root, "t1", "tried", "bad one", attack="collision", check="echo nope; exit 3")
        herd.add_note(self.root, "t1", "tried", "empty suite", attack="recount",
                      check="python3 -c \"print('Ran 0 tests')\"")
        ev = herd.verify(self.root, "t1")
        by = {a["attack"]: a for a in ev["attacks"]}
        self.assertEqual((by["bad-input"]["status"], by["bad-input"]["exit_code"]), ("passing", 0))
        self.assertIn("checked", by["bad-input"]["output_tail"])
        self.assertEqual((by["collision"]["status"], by["collision"]["exit_code"]), ("failing", 3))
        self.assertTrue(by["recount"]["zero_tests"])

    def test_gate_needs_a_passing_command(self):
        self.ready()
        fixed = "python3 -c \"import os, sys; sys.exit(not os.path.exists('fixed.txt'))\""
        herd.add_note(self.root, "t1", "tried", "a", attack="bad-input", check=fixed)
        for a in ("collision", "one-bad-part"):
            herd.add_note(self.root, "t1", "tried", a, attack=a, check=OK)
        herd.add_note(self.root, "t1", "tried", "zero", attack="recount", check="python3 -c \"print('Ran 0 tests')\"")
        herd.verify(self.root, "t1")
        probs = " ".join(herd.problems(self.root, "t1"))
        self.assertIn("bad-input", probs)
        self.assertIn("recount", probs)
        self.assertNotIn("collision (", probs)  # passing, so not listed (the recount text names collision inputs)
        self.assertEqual(herd.gate(self.root, {})["decision"], "block")
        self.assertEqual(self.cli("done").returncode, 1)
        herd.add_note(self.root, "t1", "tried", "real recount", attack="recount", check=OK)
        self.assertIn("herd verify", " ".join(herd.problems(self.root, "t1")))  # new commands not run yet
        herd.verify(self.root, "t1")
        self.assertIn("bad-input (its command fails)", " ".join(herd.problems(self.root, "t1")))
        (self.root / "fixed.txt").write_text("fixed")  # the fix makes the same command pass at the next verify
        herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])
        self.assertEqual(self.cli("done").returncode, 0)

    def test_a_later_note_replaces_a_wrong_command_but_it_stays_visible(self):
        self.ready()
        herd.add_note(self.root, "t1", "tried", "typo", attack="bad-input", check="python3 -m unittest tests.test_nope")
        for a in ("collision", "one-bad-part", "recount"):
            herd.add_note(self.root, "t1", "tried", a, attack=a, check=OK)
        herd.verify(self.root, "t1")
        self.assertIn("bad-input", " ".join(herd.problems(self.root, "t1")))
        herd.add_note(self.root, "t1", "tried", "right test", attack="bad-input", check=OK)
        herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])  # not stuck on the typo
        self.assertIn("Earlier bad-input command now fails: `python3 -m unittest tests.test_nope`",
                      herd.pr_body(self.root, "t1"))
        self.assertEqual(self.cli("done").returncode, 0)

    def test_commandless_attack_note_does_not_count(self):
        # notes from 0.3.1, or written straight into the log, have an attack but no command
        self.ready()
        with open(self.root / ".herd/tasks/t1/notes.jsonl", "a") as f:
            for a in herd.ATTACKS:
                f.write(json.dumps({"at": "2026-11-23T10:00:00Z", "kind": "tried", "text": f"old {a}", "attack": a}) + "\n")
        ev = herd.verify(self.root, "t1")
        probs = " ".join(herd.problems(self.root, "t1"))
        for a in herd.ATTACKS:
            self.assertIn(f"{a} (logged without a command)", probs)
        self.assertIn("bad-input has no command", herd.report(ev))
        self.assertEqual(self.cli("done").returncode, 1)

    def test_one_broken_or_slow_command_does_not_break_verify(self):
        self.ready()
        herd.add_note(self.root, "t1", "tried", "no such tool", attack="bad-input", check="no-such-binary-xyz")
        herd.add_note(self.root, "t1", "tried", "hangs", attack="collision", check="sleep 5")
        herd.add_note(self.root, "t1", "tried", "fine", attack="one-bad-part", check=OK)
        with mock.patch.object(herd, "DEFAULT_TIMEOUT", 1):
            ev = herd.verify(self.root, "t1")
        by = {a["attack"]: a for a in ev["attacks"]}
        self.assertEqual(by["bad-input"]["status"], "failing")
        self.assertEqual((by["collision"]["status"], by["collision"]["exit_code"]), ("failing", None))
        self.assertIn("timeout", by["collision"]["output_tail"])
        self.assertEqual(by["one-bad-part"]["status"], "passing")  # the others still run and report
        self.assertIn("one-bad-part passing", herd.report(ev))

    def test_report_matches_an_independent_recount(self):
        self.ready()
        cmds = {"bad-input": [OK, "false"], "collision": [OK], "recount": ["python3 -c \"print('Ran 0 tests')\""]}
        for a, cs in cmds.items():
            for c in cs:
                herd.add_note(self.root, "t1", "tried", f"{a} {c}", attack=a, check=c)
        herd.add_note(self.root, "t1", "tried", "n/a: one value only", attack="one-bad-part")
        herd.add_note(self.root, "t1", "tried", "free-form attempt")
        line = [x for x in herd.report(herd.verify(self.root, "t1")).splitlines() if x.startswith("Adversarial")][0]
        raw = [json.loads(x) for x in (self.root / ".herd/tasks/t1/notes.jsonl").read_text().splitlines()]
        self.assertIn(f"{sum(n['kind'] == 'tried' for n in raw)} attempts recorded", line)
        # recount by hand: the latest note per attack decides
        self.assertIn("bad-input failing", line)
        self.assertIn("collision passing", line)
        self.assertIn("one-bad-part n/a", line)
        self.assertIn("recount ran zero tests", line)
        self.assertNotIn("missing", line)

    def test_cli_verify_shows_attacks_and_fails_on_a_failing_one(self):
        self.ready()
        herd.add_note(self.root, "t1", "tried", "breaks", attack="bad-input", check="false")
        herd.add_note(self.root, "t1", "tried", "fine", attack="collision", check=OK)
        p = self.cli("verify")
        self.assertEqual(p.returncode, 1)  # a failing attack fails verify, like a failing criterion
        self.assertIn("attack bad-input failing: false", p.stdout)
        self.assertNotIn("attack collision", p.stdout)  # only what needs attention
        self.assertIn("attack collision passing", self.cli("verify", "--verbose").stdout)

    def test_vacuous_command_warns_and_does_not_count(self):
        self.ready()
        p = self.cli("note", "--tried", "--attack", "recount", "--check", "true", "x")
        self.assertEqual(p.returncode, 0)
        self.assertIn("runs no project code", p.stderr)
        herd.verify(self.root, "t1")
        self.assertIn("recount (its command runs no project code)", " ".join(herd.problems(self.root, "t1")))

    def test_na_needs_the_colon_and_a_check_still_runs(self):
        self.ready()
        with self.assertRaises(ValueError):
            herd.add_note(self.root, "t1", "tried", "n/a the tool takes one value", attack="collision")
        herd.add_note(self.root, "t1", "tried", "n/a: but checked", attack="collision", check="false")
        ev = herd.verify(self.root, "t1")
        self.assertEqual(ev["attacks"][0]["status"], "failing")  # a command always runs and decides

    def test_timeout_per_attack(self):
        self.ready()
        self.assertEqual(self.cli("note", "--tried", "--attack", "recount", "--timeout", "1", "x").returncode, 1)
        self.assertEqual(self.cli("note", "--tried", "--attack", "recount", "--check", OK, "--timeout", "0", "x")
                         .returncode, 1)
        herd.add_note(self.root, "t1", "tried", "slow", attack="recount", check="sleep 3", timeout=1)
        a = herd.verify(self.root, "t1")["attacks"][0]
        self.assertEqual((a["status"], a["exit_code"]), ("failing", None))

    def test_pr_shows_na_and_attacks_without_a_passing_command(self):
        self.ready()
        herd.add_note(self.root, "t1", "tried", "n/a: one value only", attack="collision")
        herd.add_note(self.root, "t1", "tried", "b", attack="bad-input", check="false")
        herd.verify(self.root, "t1")
        visible = re.sub(r"<details>.*?</details>", "", herd.pr_body(self.root, "t1"), flags=re.S)
        self.assertIn("Attack collision marked n/a: one value only", visible)
        self.assertIn("Standard attacks without a passing command: bad-input (command fails), one-bad-part, recount",
                      visible)

    def test_na_attack_counts_and_is_labelled(self):
        self.ready()
        for a in ("bad-input", "collision", "one-bad-part"):
            herd.add_note(self.root, "t1", "tried", a, attack=a, check=OK)
        herd.add_note(self.root, "t1", "tried", "n/a: the tool takes one value", attack="recount")
        with self.assertRaises(ValueError):
            herd.add_note(self.root, "t1", "tried", "skipped it", attack="recount")
        ev = herd.verify(self.root, "t1")
        self.assertEqual(herd.problems(self.root, "t1"), [])
        self.assertIn("recount n/a", herd.report(ev))

    def test_report_and_pr_show_attack_status(self):
        self.ready()
        herd.add_note(self.root, "t1", "tried", "a", attack="bad-input", check="python3 -m unittest tests.test_bad")
        herd.add_note(self.root, "t1", "tried", "b", attack="collision", check="false")
        ev = herd.verify(self.root, "t1")
        text = herd.report(ev)
        self.assertIn("bad-input failing", text)
        self.assertIn("collision failing", text)
        self.assertIn("`python3 -m unittest tests.test_bad`", text)
        self.assertIn("missing: one-bad-part, recount", text)
        body = herd.pr_body(self.root, "t1")
        self.assertIn("bad-input failing", body)


class TestOneActiveTask(Base):
    def test_second_init_in_one_checkout_is_refused_until_the_first_ends(self):
        herd.init_task(self.root, "t1", "g")
        with self.assertRaisesRegex(ValueError, "t1 is still active.*--worktree"):
            herd.init_task(self.root, "t2", "g")
        self.assertFalse((self.root / ".herd/tasks/t2").exists())
        self.assertEqual((self.root / ".herd/active").read_text().strip(), "t1")
        herd.cancel_task(self.root, "t1")
        herd.init_task(self.root, "t2", "g")
        self.assertEqual((self.root / ".herd/active").read_text().strip(), "t2")


FAKE_GH = """#!/bin/sh
# Stand-in for gh: logs every call; a PR "exists" once `pr create` has run.
printf 'ARGS %s\\n' "$*" >> "$FAKE_GH_DIR/log"
case "$1 $2" in
  "pr view") [ -f "$FAKE_GH_DIR/created" ] || exit 1; echo "https://github.com/o/r/pull/7" ;;
  "pr create") cat > "$FAKE_GH_DIR/body"; touch "$FAKE_GH_DIR/created"; echo "https://github.com/o/r/pull/7" ;;
  "pr edit") cat > "$FAKE_GH_DIR/body"; echo "https://github.com/o/r/pull/7" ;;
  *) exit 3 ;;
esac
"""

PR_TASK = TASK.replace('check = "test -f greet.txt"', 'check = "test -f greet.txt"\ncoverage = "Only that the file exists"')


class TestPr(Base):
    def setUp(self):
        super().setUp()
        self.gh = self.root.parent / (self.root.name + "-gh")
        self.gh.mkdir()
        (self.gh / "gh").write_text(FAKE_GH)
        (self.gh / "gh").chmod(0o755)
        self.origin = self.root.parent / (self.root.name + "-origin.git")
        subprocess.run(["git", "init", "-q", "--bare", str(self.origin)], check=True)
        git(self.root, "remote", "add", "origin", str(self.origin))
        git(self.root, "switch", "-q", "-c", "herd/t1")
        herd.init_task(self.root, "t1", "Add a greeting")
        (self.root / ".herd/tasks/t1/task.toml").write_text(PR_TASK)
        (self.root / "greet.txt").write_text("hello")
        git(self.root, "add", "greet.txt")
        git(self.root, "commit", "-q", "-m", "greet")

    def tearDown(self):
        shutil.rmtree(self.gh, ignore_errors=True)
        shutil.rmtree(self.origin, ignore_errors=True)
        shutil.rmtree(self.root.parent / (self.root.name + "-tools"), ignore_errors=True)
        super().tearDown()

    def herd(self, *args, path=True):
        tools = self.root.parent / (self.root.name + "-tools")  # no gh here, so a real gh is never found
        if not tools.exists():
            tools.mkdir()
            for name in ("git", "sh", "cat", "touch"):
                (tools / name).symlink_to(shutil.which(name))
        env = dict(os.environ, FAKE_GH_DIR=str(self.gh), PATH=(f"{self.gh}{os.pathsep}" if path else "") + str(tools))
        return subprocess.run([sys.executable, str(Path(herd.__file__)), *args], cwd=self.root,
                              capture_output=True, text=True, env=env)

    def calls(self):
        log = self.gh / "log"
        return log.read_text().splitlines() if log.exists() else []

    def test_refuses_without_opt_in(self):
        p = self.herd("pr", "t1")
        self.assertEqual(p.returncode, 1)
        self.assertIn("opt-in", p.stderr)
        self.assertEqual(self.calls(), [])

    def test_refuses_off_a_herd_branch(self):
        git(self.root, "switch", "-q", "-c", "feature")
        p = self.herd("pr", "t1", "--yes")
        self.assertEqual(p.returncode, 1)
        self.assertIn("herd/", p.stderr)
        self.assertEqual(self.calls(), [])

    def test_refuses_with_uncommitted_changes(self):
        (self.root / "greet.txt").write_text("not committed")
        p = self.herd("pr", "t1", "--yes")
        self.assertEqual(p.returncode, 1)
        self.assertIn("clean working tree", p.stderr)
        self.assertEqual(self.calls(), [])

    def test_refuses_without_gh(self):
        p = self.herd("pr", "t1", "--yes", path=False)
        self.assertEqual(p.returncode, 1)
        self.assertIn("gh", p.stderr)
        self.assertEqual(self.pushed(), "")

    def pushed(self):
        return subprocess.run(["git", "branch", "--list"], cwd=self.origin, capture_output=True, text=True).stdout

    def test_refuses_another_tasks_branch(self):
        git(self.root, "switch", "-q", "-c", "herd/other")
        p = self.herd("pr", "t1", "--yes")
        self.assertEqual(p.returncode, 1)
        self.assertIn("herd/t1", p.stderr)
        self.assertEqual((self.calls(), self.pushed()), ([], ""))

    def test_pushes_and_creates_with_herd_toml_opt_in(self):
        (self.root / "herd.toml").write_text("[pr]\nopen = true\n")
        git(self.root, "add", "herd.toml")
        git(self.root, "commit", "-qm", "opt in")
        herd.verify(self.root, "t1")
        p = self.herd("pr", "t1")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("https://github.com/o/r/pull/7", p.stdout)
        heads = subprocess.run(["git", "branch", "--list"], cwd=self.origin, capture_output=True, text=True).stdout
        self.assertIn("herd/t1", heads)
        create = [c for c in self.calls() if c.startswith("ARGS pr create")]
        self.assertEqual(len(create), 1)
        self.assertIn("--head herd/t1", create[0])
        self.assertIn("--title Add a greeting", create[0])

    def test_done_refreshes_the_pr_description(self):
        self.attacks()
        herd.verify(self.root, "t1")
        self.herd("pr", "t1", "--yes")
        self.assertTrue((self.root / ".herd/tasks/t1/pr").exists())
        herd.add_note(self.root, "t1", "found", "a late finding")  # after the PR, before done
        p = self.herd("done")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("pr: description updated", p.stdout)
        self.assertEqual(sum(c.startswith("ARGS pr edit") for c in self.calls()), 1)
        self.assertIn("a late finding", (self.gh / "body").read_text())

    def test_done_without_a_pr_never_calls_gh(self):
        self.attacks()
        herd.verify(self.root, "t1")
        self.assertEqual(self.herd("done").returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_updates_the_body_on_a_second_run(self):
        herd.verify(self.root, "t1")
        self.herd("pr", "t1", "--yes")
        git(self.root, "rm", "-q", "greet.txt")  # the evidence changes between the two runs
        git(self.root, "commit", "-qm", "drop greet")
        herd.verify(self.root, "t1")
        p = self.herd("pr", "t1", "--yes")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(sum(c.startswith("ARGS pr create") for c in self.calls()), 1)
        self.assertEqual(sum(c.startswith("ARGS pr edit") for c in self.calls()), 1)
        body = (self.gh / "body").read_text()
        self.assertIn("C1 is failing", body.split("## What is not proven")[1])
        self.assertNotIn("| C1 |", body)  # a failing criterion is never listed as proven

    def test_never_merges(self):
        herd.verify(self.root, "t1")
        self.herd("pr", "t1", "--yes")
        self.herd("pr", "t1", "--yes")
        self.assertFalse([c for c in self.calls() if "merge" in c])

    def test_body_puts_evidence_first(self):
        (self.root / ".herd/tasks/t1/task.toml").write_text('known_limits = "Only ASCII names"\n' + PR_TASK)
        herd.add_note(self.root, "t1", "open", "unicode names not tried")
        herd.verify(self.root, "t1")
        self.herd("pr", "t1", "--yes")
        body = (self.gh / "body").read_text()
        self.assertTrue(body.startswith("# Evidence: t1\n"))
        order = ["**Result:** 1 of 2 criteria proven", "## What is proven", "| C1 |", "`test -f greet.txt`",
                 "## What is not proven", "C2", "unchecked", "Only that the file exists", "Only ASCII names",
                 "unicode names not tried", "<summary>Run details", "<summary>Reproduce", "test -f greet.txt", "never merges"]
        at = 0
        for s in order:  # each piece appears after the previous one
            at = body.find(s, at)
            self.assertNotEqual(at, -1, f"{s!r} missing or out of order")
        self.assertIn("fresh", body.split("## What is proven")[0])

    def test_body_has_no_output_tail_and_caps_the_caveat_list(self):
        (self.root / ".herd/tasks/t1/task.toml").write_text(
            PR_TASK.replace('check = ""', 'check = "python3 -c \\"print(\'SECRET_\' + \'TOKEN_VALUE\'); exit(1)\\""'))
        git(self.root, "commit", "-q", "--allow-empty", "-m", "noop")
        for i in range(herd.MAX_PR_NOTES + 5):
            herd.add_note(self.root, "t1", "found", f"note {i} " + 900 * "x")
        herd.verify(self.root, "t1")
        self.herd("pr", "t1", "--yes")
        body = (self.gh / "body").read_text()
        self.assertNotIn("SECRET_TOKEN_VALUE", body)
        self.assertIn("C2 is failing", body)
        self.assertIn("and 5 more", body)
        self.assertLess(len(body), 65536)

    def test_body_says_when_evidence_is_missing_or_stale(self):
        self.herd("pr", "t1", "--yes")
        self.assertIn("No evidence yet", (self.gh / "body").read_text())
        herd.verify(self.root, "t1")
        (self.root / "greet.txt").write_text("changed")
        git(self.root, "commit", "-qam", "change after verify")
        self.herd("pr", "t1", "--yes")
        body = (self.gh / "body").read_text()
        self.assertIn("stale", body.split("## What")[0])
        self.assertIn("before later changes", body)
        self.assertNotIn("## What is proven", body)

    def test_body_does_not_count_a_zero_test_pass_as_proven(self):
        (self.root / ".herd/tasks/t1/task.toml").write_text(
            PR_TASK.replace('check = ""', 'check = "python3 -c \\"print(\'Ran 0 tests\')\\""'))
        git(self.root, "commit", "-q", "--allow-empty", "-m", "noop")
        herd.verify(self.root, "t1")
        self.herd("pr", "t1", "--yes")
        body = (self.gh / "body").read_text()
        self.assertIn("1 of 2 criteria proven", body)
        self.assertNotIn("| C2 |", body)
        self.assertIn("C2 passed but ran zero tests", body)

    def test_backticks_in_a_check_cannot_break_the_markdown(self):
        (self.root / ".herd/tasks/t1/task.toml").write_text(
            PR_TASK.replace('test -f greet.txt', 'test -f greet.txt # `x` ```'))  # backticks in a comment: still passes
        git(self.root, "commit", "-q", "--allow-empty", "-m", "noop")
        herd.verify(self.root, "t1")
        self.herd("pr", "t1", "--yes")
        body = (self.gh / "body").read_text()
        self.assertIn("````bash", body)
        self.assertIn("| ```` test -f greet.txt # `x` ``` ```` exit 0 |", body)

    def test_title_is_short_and_cut_at_a_word(self):
        self.assertEqual(herd.pr_title("Add a greeting", "t1"), "Add a greeting")
        long = "Opt-in PR step: a herd pr command pushes the branch and opens or updates a pull request"
        title = herd.pr_title(long + "\nsecond line", "t1")
        self.assertLessEqual(len(title), 72)
        self.assertTrue(title.endswith("...") and long.startswith(title[:-3]) and long[len(title) - 3] == " ")
        self.assertEqual(herd.pr_title("  \n", "t1"), "t1")

    def test_cli_warns_when_the_evidence_is_not_done(self):
        p = self.herd("pr", "t1", "--yes")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("warning: the pull request shows evidence that is not done", p.stderr)


WT_TASK = '''goal = "Write out.txt"
known_limits = "none"

[[criteria]]
id = "C1"
text = "out.txt exists"
source = "agent-proposed"
check = "test -f out.txt"
'''


class TestWorktree(Base):
    """Tasks in their own worktree, cut from the local branch the work starts on."""

    def setUp(self):
        super().setUp()
        git(self.root, "switch", "-q", "-c", "work")
        (self.root / "base.txt").write_text("from work")
        git(self.root, "add", "base.txt")
        git(self.root, "commit", "-q", "-m", "work commit")

    def tearDown(self):
        subprocess.run(["git", "worktree", "prune"], cwd=self.root, capture_output=True)
        super().tearDown()

    def herd(self, *args, cwd=None, env=None):
        return subprocess.run([sys.executable, str(Path(herd.__file__)), *args], cwd=cwd or self.root,
                              capture_output=True, text=True, env=env)

    def wt(self, slug):
        return self.root / ".claude" / "worktrees" / f"herd-{slug}"

    def out(self, args, cwd):
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True).stdout.strip()

    def test_creates_a_worktree_on_a_new_branch_cut_from_the_current_branch(self):
        p = self.herd("init", "t1", "Write out.txt", "--worktree")
        self.assertEqual(p.returncode, 0, p.stderr)
        path = self.wt("t1")
        self.assertIn(str(path), p.stdout)
        self.assertEqual(self.out(["git", "rev-parse", "--abbrev-ref", "HEAD"], path), "herd/t1")
        self.assertEqual(self.out(["git", "rev-parse", "HEAD"], path), self.out(["git", "rev-parse", "HEAD"], self.root))
        self.assertTrue((path / ".herd/tasks/t1/task.toml").exists())
        self.assertEqual((path / ".herd/active").read_text().strip(), "t1")
        self.assertEqual((path / ".herd/tasks/t1/base").read_text().strip(), "work")
        self.assertFalse((self.root / ".herd/active").exists())  # the starting checkout has no task of its own
        self.assertFalse((self.root / ".herd/tasks").exists())
        self.assertEqual(self.out(["git", "rev-parse", "--abbrev-ref", "HEAD"], self.root), "work")

    def test_base_warns_about_uncommitted_changes_left_behind(self):
        (self.root / "base.txt").write_text("edited, not committed")
        p = self.herd("init", "t1", "Write out.txt", "--worktree")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("uncommitted", p.stderr)
        self.assertEqual((self.wt("t1") / "base.txt").read_text(), "from work")

    def test_base_refuses_a_detached_head(self):
        git(self.root, "checkout", "-q", "--detach")
        p = self.herd("init", "t1", "Write out.txt", "--worktree")
        self.assertEqual(p.returncode, 1)
        self.assertIn("local branch", p.stderr)
        self.assertFalse(self.wt("t1").exists())

    def test_herd_pr_targets_the_recorded_base(self):
        self.herd("init", "t1", "Write out.txt", "--worktree")
        path = self.wt("t1")
        origin = self.root.parent / (self.root.name + "-origin.git")
        gh = self.root.parent / (self.root.name + "-gh")
        try:
            subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
            git(path, "remote", "add", "origin", str(origin))
            gh.mkdir()
            (gh / "gh").write_text(FAKE_GH)
            (gh / "gh").chmod(0o755)
            env = dict(os.environ, FAKE_GH_DIR=str(gh), PATH=f"{gh}{os.pathsep}{os.environ['PATH']}")
            p = self.herd("pr", "t1", "--yes", cwd=path, env=env)
            self.assertEqual(p.returncode, 0, p.stderr)
            create = [ln for ln in (gh / "log").read_text().splitlines() if ln.startswith("ARGS pr create")]
            self.assertIn("--base work", create[0])
        finally:
            shutil.rmtree(origin, ignore_errors=True)
            shutil.rmtree(gh, ignore_errors=True)

    def test_opt_in_off_plain_init_is_unchanged(self):
        p = self.herd("init", "t1", "Write out.txt")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue((self.root / ".herd/tasks/t1/task.toml").exists())
        self.assertFalse((self.root / ".claude").exists())

    def required(self):
        (self.root / "herd.toml").write_text("[worktree]\nrequired = true\n")
        git(self.root, "add", "herd.toml")
        git(self.root, "commit", "-q", "-m", "require worktrees")

    def test_opt_in_required_refuses_a_plain_init_in_the_main_checkout(self):
        self.required()
        p = self.herd("init", "t1", "Write out.txt")
        self.assertEqual(p.returncode, 1)
        self.assertIn("--worktree", p.stderr)
        self.assertFalse((self.root / ".herd/tasks/t1").exists())

    def test_opt_in_required_refuses_a_worktree_on_another_branch(self):
        self.required()
        other = self.root.parent / (self.root.name + "-other")
        git(self.root, "worktree", "add", "-q", "-b", "feature", str(other))
        try:
            p = self.herd("init", "t1", "Write out.txt", cwd=other)
            self.assertEqual(p.returncode, 1)
            self.assertIn("herd/t1", p.stderr)
        finally:
            git(self.root, "worktree", "remove", "--force", str(other))

    def test_opt_in_required_accepts_init_worktree_and_a_matching_worktree(self):
        self.required()
        p = self.herd("init", "t1", "Write out.txt", "--worktree")
        self.assertEqual(p.returncode, 0, p.stderr)
        manual = self.root.parent / (self.root.name + "-t2")
        git(self.root, "worktree", "add", "-q", "-b", "herd/t2", str(manual))
        try:
            p = self.herd("init", "t2", "Write out.txt", cwd=manual)
            self.assertEqual(p.returncode, 0, p.stderr)
        finally:
            git(self.root, "worktree", "remove", "--force", str(manual))

    def test_end_to_end_inside_the_worktree(self):
        self.assertEqual(self.herd("init", "t1", "Write out.txt", "--worktree").returncode, 0)
        path = self.wt("t1")
        (path / ".herd/tasks/t1/task.toml").write_text(WT_TASK)
        self.attacks(root=path)
        self.assertEqual(self.herd("check", cwd=path).returncode, 0)
        self.assertEqual(self.herd("verify", cwd=path).returncode, 1)  # red first
        (path / "out.txt").write_text("done")
        git(path, "add", "out.txt")
        git(path, "commit", "-q", "-m", "write out.txt")
        self.assertEqual(self.herd("verify", cwd=path).returncode, 0)
        p = self.herd("done", cwd=path)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("done: evidence is fresh and passing", p.stdout)
        self.assertFalse((self.root / "out.txt").exists())  # the starting checkout never saw the work

    def test_concurrent_inits_from_one_checkout_are_isolated(self):
        # a main-checkout task with fresh evidence must stay fresh while others start worktree tasks
        herd.init_task(self.root, "home", "Home task")
        (self.root / ".herd/tasks/home/task.toml").write_text(WT_TASK.replace("test -f out.txt", "test -f base.txt"))
        self.attacks("home")
        herd.verify(self.root, "home")
        slugs = [f"t{i}-{os.urandom(3).hex()}" for i in range(6)]
        procs = [subprocess.Popen([sys.executable, str(Path(herd.__file__)), "init", s, f"Goal {s}", "--worktree"],
                                  cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for s in slugs]
        results = [(p.wait(), p.stderr.read()) for p in procs]
        self.assertEqual([r[0] for r in results], [0] * len(slugs), results)
        for s in slugs:
            path = self.wt(s)
            self.assertEqual(self.out(["git", "rev-parse", "--abbrev-ref", "HEAD"], path), f"herd/{s}")
            self.assertEqual(sorted(p.name for p in (path / ".herd/tasks").iterdir()), [s])
            self.assertEqual((path / ".herd/active").read_text().strip(), s)
            block = herd.gate(path, {})
            self.assertIn(f"`{s}`", block["reason"])
            self.assertFalse([o for o in slugs if o != s and o in block["reason"]])
        self.assertEqual((self.root / ".herd/active").read_text().strip(), "home")
        self.assertEqual(herd.problems(self.root, "home"), [])  # not made stale by the new worktrees
        dup = self.herd("init", slugs[0], "Again", "--worktree")
        self.assertEqual(dup.returncode, 1)
        self.assertEqual((self.wt(slugs[0]) / ".herd/active").read_text().strip(), slugs[0])

    def test_gate_finds_the_task_from_a_subdirectory(self):
        self.herd("init", "t1", "Write out.txt", "--worktree")
        sub = self.wt("t1") / "deep" / "dir"
        sub.mkdir(parents=True)
        p = subprocess.run([sys.executable, str(Path(herd.__file__)), "gate"], cwd=self.root,
                           input=json.dumps({"cwd": str(sub)}), capture_output=True, text=True)
        self.assertIn('"decision": "block"', p.stdout)
        self.assertIn("t1", p.stdout)

    def test_clean_status_in_the_main_checkout_and_worktree_remove_works(self):
        self.assertEqual(self.herd("init", "t1", "Write out.txt", "--worktree").returncode, 0)
        self.assertEqual(self.out(["git", "status", "--porcelain"], self.root), "")  # nothing for `git add -A` to grab
        p = subprocess.run(["git", "worktree", "remove", str(self.wt("t1"))], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(herd.elsewhere(self.root), {})  # a removed worktree is forgotten
        self.assertEqual(self.herd("init", "t2", "Again", "--worktree").returncode, 0)
        exclude = Path(self.out(["git", "rev-parse", "--git-common-dir"], self.root))
        exclude = (exclude if exclude.is_absolute() else self.root / exclude) / "info" / "exclude"
        self.assertEqual(exclude.read_text().count(".herd/"), 1)  # added once, not on every init

    def test_subproject_in_a_subfolder_keeps_its_own_herd(self):
        pkg = self.root / "packages" / "app"
        pkg.mkdir(parents=True)
        (pkg / "herd.toml").write_text("# app config\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "app package")
        p = self.herd("init", "t1", "Write out.txt", cwd=pkg)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue((pkg / ".herd/tasks/t1").exists())
        deeper = pkg / "src"
        deeper.mkdir()
        self.assertIn("t1", self.herd("verify", cwd=deeper).stdout + self.herd("status", cwd=deeper).stdout)
        gate = subprocess.run([sys.executable, str(Path(herd.__file__)), "gate"], cwd=self.root,
                              input=json.dumps({"cwd": str(deeper)}), capture_output=True, text=True)
        self.assertIn('"decision": "block"', gate.stdout)
        p = self.herd("init", "t2", "Write out.txt", "--worktree", cwd=pkg)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue((self.wt("t2") / "packages/app/.herd/tasks/t2/task.toml").exists())

    def test_commands_from_the_starting_checkout_points_to_the_worktree(self):
        self.herd("init", "t1", "Write out.txt", "--worktree")
        for args in (["verify", "t1"], ["status"], ["note", "--tried", "x"]):
            p = self.herd(*args)
            self.assertNotEqual(p.returncode, 0, args)
            self.assertIn(str(self.wt("t1")), p.stderr, args)


SKILLS = Path(herd.__file__).resolve().parent.parent / "skills"


def words(text):
    return len(text.split())


class TestBudgets(Base):
    """Herd's own output stays short; the full detail is one flag or one file away."""

    def setUp(self):
        super().setUp()
        herd.init_task(self.root, "t1", "Add a greeting")
        (self.root / ".herd/tasks/t1/task.toml").write_text(PR_TASK.replace('check = ""', 'check = "test -n x"'))
        (self.root / "greet.txt").write_text("hello")

    def cli(self, *args):
        p = subprocess.run([sys.executable, str(Path(herd.__file__)), *args], cwd=self.root,
                           capture_output=True, text=True)
        out = p.stdout.strip().splitlines()
        if args[:1] == ("verify",):  # 0.4.0: one summary line for `herd check` warnings, budgeted on its own
            warn = [line for line in out if "herd check warning" in line]
            self.assertLessEqual(len(warn), 1, out)
            out = [line for line in out if line not in warn]
        return p.returncode, out

    # (1) short CLI output
    def test_cli_verify_prints_one_line_when_all_pass(self):
        rc, out = self.cli("verify")
        self.assertEqual((rc, out), (0, ["2 passing, 0 failing, 0 unchecked"]))

    def test_cli_verify_lists_only_what_needs_attention(self):
        (self.root / "greet.txt").unlink()
        rc, out = self.cli("verify")
        self.assertEqual(rc, 1)
        self.assertEqual(len(out), 2)
        self.assertIn("C1 failing", out[1])

    def test_cli_verify_still_lists_unchecked_and_zero_test_criteria(self):
        (self.root / ".herd/tasks/t1/task.toml").write_text(
            PR_TASK.replace('check = ""', 'check = "python3 -c \\"print(\'Ran 0 tests\')\\""')
            + '\n[[criteria]]\nid = "C3"\ntext = "Looks right"\nsource = "agent-proposed"\ncheck = ""\n')
        rc, out = self.cli("verify")
        self.assertEqual(len(out), 3)
        self.assertIn("C2 passing (ran zero tests)", out[1])
        self.assertIn("C3 unchecked", out[2])

    def test_cli_triage_names_a_broken_config(self):
        (self.root / "herd.toml").write_text('floor = "oops')
        rc, out = self.cli("triage", "Change docs")
        self.assertIn("fallback", out[0])
        self.assertIn("herd.toml", out[0])

    def test_cli_verify_verbose_lists_every_criterion(self):
        rc, out = self.cli("verify", "--verbose")
        self.assertEqual(len(out), 3)
        self.assertIn("C2 passing", out[2])

    def test_cli_done_is_at_most_three_lines_and_points_to_the_report(self):
        self.attacks()
        self.cli("verify")
        rc, out = self.cli("done")
        self.assertEqual(rc, 0)
        self.assertLessEqual(len(out), 11)  # 0.4.0: the result, the report path and the seven-line final report
        self.assertEqual(sum(line.startswith(("Done:", "Proven:", "Not proven:", "Caveats:", "Decisions:",
                                              "Limits:", "Review:")) for line in out), 7, out)
        self.assertIn("evidence.md", " ".join(out))
        self.assertIn("2 of 2", " ".join(out))
        self.assertIn("# Evidence: t1", (self.root / ".herd/tasks/t1/evidence.md").read_text())

    def test_cli_done_verbose_prints_the_report(self):
        self.attacks()
        self.cli("verify")
        rc, out = self.cli("done", "--verbose")
        self.assertIn("# Evidence: t1", out)

    def test_cli_triage_is_one_line_and_json_on_request(self):
        rc, out = self.cli("triage", "Change auth/session.py")
        self.assertEqual(len(out), 1)
        self.assertIn("risk: high", out[0])
        self.assertIn("auth/**", out[0])
        rc, out = self.cli("triage", "Change auth/session.py", "--json")
        self.assertEqual(json.loads("\n".join(out))["risk"]["floor"], "high")

    # (2) the final report is written by `herd done`, not by the agent from memory (0.4.0)
    def test_final_report_comes_from_herd_done(self):
        text = (SKILLS / "run/SKILL.md").read_text()
        section = text.split("## Final report", 1)[1].split("## Writing", 1)[0]
        self.assertIn("Paste the report `herd done` prints", section)
        self.assertIn("herd note --decision", section)
        self.assertNotIn("```text", section)  # no template left to fill by hand

    # (3) short skills, rare parts in reference files read only when needed
    def test_skill_word_budgets(self):
        # quality first: 0.3.1 raised run from 800 when the break-it attacks moved back into it
        budget = {"run": 830, "criteria": 450, "evidence": 450}  # 0.4.0: rules the CLI enforces left the skill;
        # 0.5.0: +10 for resuming from the stop record
        for name, limit in budget.items():
            self.assertLessEqual(words((SKILLS / name / "SKILL.md").read_text()), limit, name)

    def test_skill_reference_files_exist_and_are_linked(self):
        run = (SKILLS / "run/SKILL.md").read_text()
        refs = sorted(p.name for p in (SKILLS / "run").glob("*.md") if p.name != "SKILL.md")
        self.assertGreaterEqual(len(refs), 3)
        for name in refs:
            self.assertIn(name, run)

    def test_adversarial_pass_keeps_the_standard_attacks(self):
        text = (SKILLS / "run/adversarial.md").read_text()
        for attack in ("bad input at every entry point", "never a traceback", "same key", "does not ask for", "recompute"):
            self.assertIn(attack, text)
        run = (SKILLS / "run/SKILL.md").read_text()
        self.assertIn("Read [adversarial.md](adversarial.md) now", run)  # 0.3.0 runs skipped the optional file
        self.assertIn("read all of it before you act", run)

    # (4) PR description: visible part short, the rest collapsed but kept
    def test_pr_body_visible_part_is_short_and_nothing_is_dropped(self):
        herd.add_note(self.root, "t1", "tried", "fed it an empty name")
        herd.add_note(self.root, "t1", "found", "an empty name crashed")
        herd.add_note(self.root, "t1", "fixed", "empty names now rejected")
        herd.add_note(self.root, "t1", "open", "unicode names not tried")
        herd.verify(self.root, "t1")
        body = herd.pr_body(self.root, "t1")
        visible = re.sub(r"<details>.*?</details>", "", body, flags=re.S)
        self.assertLessEqual(words(visible), 200, visible)  # 0.4.0: + unreviewed and `herd check` warning lines
        self.assertIn("unicode names not tried", visible)  # open caveats stay in view
        for kept in ("fed it an empty name", "empty names now rejected", "test -f greet.txt", "Route: standard"):
            self.assertIn(kept, body)
            self.assertNotIn(kept, visible.split("## What is proven")[0])
        self.assertGreaterEqual(body.count("<details>"), 2)

    def test_pr_table_clips_long_checks_and_reproduce_keeps_them(self):
        long_check = "test -f greet.txt && " + " && ".join(["true"] * 20)
        (self.root / ".herd/tasks/t1/task.toml").write_text(PR_TASK.replace("test -f greet.txt", long_check))
        herd.verify(self.root, "t1")
        body = herd.pr_body(self.root, "t1")
        table = body.split("## What is not proven")[0]
        self.assertNotIn(long_check, table)
        self.assertIn("...", table)
        self.assertIn(long_check, body.split("<summary>Reproduce")[1])

    def test_check_warns_about_long_criterion_and_coverage_text(self):
        task = {"criteria": [{"id": "C1", "text": "word " * 41, "source": "agent-proposed", "coverage": "x " * 51},
                             {"id": "C2", "text": "short", "source": "agent-proposed"}]}
        warnings = herd.length_warnings(task)
        self.assertEqual(len(warnings), 2)
        self.assertTrue(all(w.startswith("C1") for w in warnings))
        human = {"criteria": [{"id": "H1", "text": "word " * 80, "source": "human"}]}
        self.assertEqual(herd.length_warnings(human), [])  # the human's own words are never pushed shorter

    # (5) writing rules
    def test_rules_section_in_the_run_skill(self):
        text = (SKILLS / "run/SKILL.md").read_text()
        rules = text.split("## Writing", 1)[1].split("\n## ", 1)[0]
        for rule in ("Answer first", "never drop", "exact", "No recap"):
            self.assertIn(rule.lower(), rules.lower())


def _old_python():
    for exe in ("/usr/bin/python3", "python3.10", "python3.9"):
        path = shutil.which(exe)
        if not path:
            continue
        v = subprocess.run([path, "-c", "import sys; print(sys.version_info < (3, 11))"], capture_output=True, text=True)
        if v.stdout.strip() == "True":
            return path
    return None


@unittest.skipUnless(_old_python(), "no Python older than 3.11 on this machine")
class TestOldPython(Base):
    def run_old(self, *args):
        return subprocess.run([_old_python(), str(Path(herd.__file__)), *args], cwd=self.root,
                              input="{}", capture_output=True, text=True)

    def test_hooks_exit_quietly(self):
        for hook in ("gate", "lint"):
            p = self.run_old(hook)
            self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""), hook)

    def test_cli_names_the_version_it_needs(self):
        p = self.run_old("status")
        self.assertEqual(p.returncode, 1)
        self.assertIn("herd needs Python 3.11 or newer", p.stderr)


if __name__ == "__main__":
    unittest.main()
