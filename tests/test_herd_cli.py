import contextlib
import io
import json
import random
import re
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import traceback
import time
import unittest
from pathlib import Path
from unittest import mock

from scripts import herd

TASK = '''goal = "Add a greeting"
test_budget = "One file check; no unit tests"
known_limits = "Only the file is checked, not its text"
inputs = []

[[criteria]]
id = "C1"
text = "Given a name, when greet runs, then it prints hello"
source = "human"
coverage = "Proves greet.txt exists; not what it says"
check = "test -f greet.txt"

[[criteria]]
id = "C2"
text = "The greeting reads well"
source = "agent-proposed"
check = ""
'''
# TASK without test_budget, known_limits and coverage, which `herd done` needs at medium and high risk (0.10.0)
BARE = "\n".join(line for line in TASK.splitlines() if not line.startswith(("test_budget", "known_limits", "coverage"))) + "\n"


OK = "python3 -c \"import json\""  # an attack command that passes and is not vacuous
# what one-bad-part and other-reading also need at medium and high risk (0.12.12)
PROGRAMS = {"collision": {"refuses": "python3 -c \"import sys; sys.exit('repeated id')\""},
            "one-bad-part": {"refuses": "python3 -c \"import sys; sys.exit('no such item')\""},
            "other-reading": {"example": "python3 -c \"print('hello')\"",
                              "extra": {"expect": "hello"}}}  # extra: as if logged before red


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def run_herd(cwd, *args, input=None):
    """Run a herd command as `python3 scripts/herd.py` would, in this process: no interpreter start for tests that
    are not about the process itself (TestCli, the env, concurrency and old-Python tests keep real subprocesses).
    The result has returncode, stdout and stderr."""
    out, err, code, here = io.StringIO(), io.StringIO(), 0, os.getcwd()
    os.chdir(cwd)
    try:
        with mock.patch("sys.stdin", io.StringIO(input or "")), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            try:
                code = herd.main([str(a) for a in args])
            except SystemExit as e:
                if isinstance(e.code, str):  # sys.exit("message"): the message goes to stderr, the status is 1
                    print(e.code, file=sys.stderr)
                code = e.code if isinstance(e.code, int) else int(e.code is not None)
            except Exception:  # a traceback and exit 1, as the real process would
                traceback.print_exc()
                code = 1
    finally:
        os.chdir(here)
    return subprocess.CompletedProcess(args, code or 0, out.getvalue(), err.getvalue())


def no_design(root, slug="t1"):
    """Make the task one from before 0.14.0: a `herd` subprocess cannot stub the design rules (issue #102), which
    are not under test here. tests.test_designer covers them."""
    path = Path(root) / ".herd" / "tasks" / slug / "start.json"
    start = json.loads(path.read_text())
    start.pop("models", None)
    path.write_text(json.dumps(start))


def stub_first_verify_refusal(case):
    """Most tests are about other rules: they run a first verify with no attack notes, which is refused since issue #94.
    A class that tests the refusal itself sets `refuses_first = True`. The design rules (issue #102) are not under test
    here either: tests.test_designer covers them."""
    for name, value in (("has_answers", True), ("design_problems", [])):
        design = mock.patch.object(herd, name, return_value=value)
        design.start()
        case.addCleanup(design.stop)
    if not case.refuses_first:
        patch = mock.patch.object(herd, "unlogged_attacks", return_value=[])
        patch.start()
        case.addCleanup(patch.stop)


class Base(unittest.TestCase):
    refuses_first = False

    @classmethod
    def setUpClass(cls):
        """One template repository per test class; each test works in a copy of it (git init is not under test)."""
        super().setUpClass()
        cls.template = tempfile.TemporaryDirectory()
        root = Path(cls.template.name)
        git(root, "init", "-q")
        git(root, "config", "user.email", "t@example.com")
        git(root, "config", "user.name", "t")
        (root / "README.md").write_text("x")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "init")

    @classmethod
    def tearDownClass(cls):
        cls.template.cleanup()
        super().tearDownClass()

    def setUp(self):
        stub_first_verify_refusal(self)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(self.template.name, self.root, dirs_exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def task(self, text=TASK, attacks=False):
        herd.init_task(self.root, "t1", "Add a greeting")
        (self.root / ".herd/tasks/t1/task.toml").write_text(text)
        if attacks:
            self.attacks()

    def attacks(self, slug="t1", root=None):
        """Record the standard attacks, which `herd done` needs on the standard route."""
        for a in herd.ATTACKS:
            herd.add_note(root or self.root, slug, "tried", f"{a} attack", attack=a, check=OK, **PROGRAMS.get(a, {}))


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
        p = run_herd(self.root, "check")
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
        p = run_herd(self.root, "init", "q1", "Fix typo", "--quick", "true")
        self.assertEqual(p.returncode, 0, p.stderr)
        p = run_herd(self.root, "init", "q2", "Fix auth/x.py", "--quick", "true")
        self.assertEqual(p.returncode, 1)
        self.assertIn("high", p.stderr)


class TestBudgetAndRed(Base):
    def test_budget_note_in_report_and_validation(self):
        self.task(TASK.replace('"One file check; no unit tests"', '"unit for parsing; not testing the CLI wrapper"'))
        (self.root / "greet.txt").write_text("hello")
        text = herd.report(herd.verify(self.root, "t1"))
        self.assertIn("Test budget: unit for parsing; not testing the CLI wrapper", text)
        t = herd.load_task(self.root, "t1")
        self.assertEqual(herd.validate_task(dict(t, test_budget=3))[0].split(":")[0], "test_budget")

    def test_no_budget_line_when_absent(self):
        self.task(BARE)
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
        run = lambda *a: run_herd(self.root, *a)
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
        self.task(BARE)
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
        self.assertIn("open #1: slow above 600x400", text)

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
        self.assertIn("Adversarial pass: 7 attempts recorded; bad-input passing (`", text)
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
        run = lambda *a: run_herd(self.root, *a)
        self.task(attacks=True)
        (self.root / "greet.txt").write_text("hello")
        self.assertEqual(run("verify").returncode, 0)
        self.assertEqual(run("note", "--found", "late finding").returncode, 0)
        self.assertIn("late finding", run("status").stdout)
        done = run("done")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("late finding", (self.root / ".herd/tasks/t1/evidence.md").read_text())

    def test_cli_note_flags(self):
        run = lambda *a: run_herd(self.root, *a)
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
        return run_herd(self.root, *args)

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

    def test_no_tasks_status_is_not_an_error(self):  # issue #116: before `herd init` is a normal state
        p = self.run_cli("status")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("herd init", p.stdout)
        p = self.run_cli("verify")  # other commands still need a task
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
        p = run_herd(self.root, "detect")
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout)[0]["type"], "rust")

    def test_detect_empty_repo(self):
        p = run_herd(self.root, "detect")
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
        return run_herd(self.root, "done").returncode


class TestGateOwner(Base):
    """Issue #136: the Stop gate blocks the session that ran `herd init` and the last one to run herd here."""

    def logs(self):
        """A task owned by home/owner.jsonl; parent.jsonl and other/owner.jsonl are other sessions."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        home = Path(os.path.realpath(tmp.name))
        (home / "other").mkdir()
        for name in ("owner.jsonl", "parent.jsonl", "other/owner.jsonl"):
            (home / name).touch()
        self.task()
        self.owner(str(home / "owner.jsonl"))
        return home

    def owner(self, session):
        path = self.root / ".herd/tasks/t1/start.json"
        start = json.loads(path.read_text())
        start["session"] = session
        path.write_text(json.dumps(start))

    def stop(self, log):
        return herd.gate(self.root, {"transcript_path": str(log)})

    def state(self):
        return {f.name: f.read_bytes() for f in (self.root / ".herd/tasks/t1").iterdir() if f.is_file()}

    def test_another_session_stops_and_changes_nothing(self):
        home = self.logs()
        before = self.state()
        for _ in range(herd.MAX_BLOCKS + 2):
            self.assertIsNone(self.stop(home / "parent.jsonl"))
        self.assertEqual(self.state(), before)  # no gate_blocks, no done_blocks, no stopped.json

    def test_another_session_leaves_a_passing_task_alone(self):
        home = self.logs()
        self.attacks()
        (self.root / "greet.txt").write_text("hello")
        herd.verify(self.root, "t1")
        self.assertIsNone(self.stop(home / "parent.jsonl"))
        self.assertFalse((self.root / ".herd/tasks/t1/done_blocks").exists())
        self.assertIn("evidence passes", self.stop(home / "owner.jsonl")["reason"])

    def test_the_owner_keeps_its_whole_budget(self):
        home = self.logs()
        blocked = 0
        for _ in range(herd.MAX_BLOCKS + 2):
            self.assertIsNone(self.stop(home / "parent.jsonl"))
            blocked += self.stop(home / "owner.jsonl") is not None
        self.assertEqual(blocked, herd.MAX_BLOCKS)
        self.assertEqual((self.root / ".herd/tasks/t1/gate_blocks").read_text(), str(herd.MAX_BLOCKS))

    def test_the_owner_through_any_path_to_its_log_is_blocked(self):
        home = self.logs()
        (home / "link.jsonl").symlink_to(home / "owner.jsonl")
        (home / "linked-home").symlink_to(home, target_is_directory=True)
        forms = [home / "owner.jsonl", home / "link.jsonl", home / "linked-home/owner.jsonl",
                 f"{home}/other/../owner.jsonl", f"{home}//./owner.jsonl"]
        for recorded in forms:
            for seen in forms:
                with self.subTest(recorded=str(recorded), seen=str(seen)):
                    self.owner(str(recorded))
                    (self.root / ".herd/tasks/t1/gate_blocks").unlink(missing_ok=True)
                    self.assertEqual(self.stop(seen)["decision"], "block")

    def test_blocks_exactly_the_owner_on_generated_paths(self):
        home = self.logs()
        names = ["owner.jsonl", "parent.jsonl", "other/owner.jsonl", "gone.jsonl", "Owner (1).jsonl",
                 "s\u00e9ance.jsonl", "x" * 200 + ".jsonl"]
        (home / "alias.jsonl").symlink_to(home / "parent.jsonl")
        names.append("alias.jsonl")

        def real(name):  # the oracle follows the one link by hand, not with the code under test
            return "parent.jsonl" if name == "alias.jsonl" else name

        rng = random.Random(136)
        for _ in range(60):
            a, b = rng.choice(names), rng.choice(names)
            with self.subTest(recorded=a, seen=b):
                self.owner(str(home / a))
                (self.root / ".herd/tasks/t1/gate_blocks").unlink(missing_ok=True)
                self.assertEqual(self.stop(home / b) is not None, real(a) == real(b))

    def test_same_file_name_elsewhere_is_another_session(self):
        home = self.logs()
        self.assertIsNone(self.stop(home / "other/owner.jsonl"))

    def test_unknown_owner_or_stopper_blocks(self):
        home = self.logs()
        parent = str(home / "parent.jsonl")
        for hook in ({}, {"transcript_path": None}, {"transcript_path": ""}, {"transcript_path": 7},
                     {"transcript_path": ["a"]}, {"transcript_path": "a\0b"}, {"transcript_path": "\ud800"}):
            with self.subTest(hook=hook):
                (self.root / ".herd/tasks/t1/gate_blocks").unlink(missing_ok=True)
                self.assertEqual(herd.gate(self.root, hook)["decision"], "block")
        for session in (None, "", 7, ["a"], "a\0b"):
            with self.subTest(session=session):
                self.owner(session)
                (self.root / ".herd/tasks/t1/gate_blocks").unlink(missing_ok=True)
                self.assertEqual(self.stop(parent)["decision"], "block")
        for text in ("{", "[]", "7", '"x"', "null", ""):
            with self.subTest(start=text):
                (self.root / ".herd/tasks/t1/start.json").write_text(text)
                (self.root / ".herd/tasks/t1/gate_blocks").unlink(missing_ok=True)
                self.assertEqual(self.stop(parent)["decision"], "block")
        (self.root / ".herd/tasks/t1/start.json").write_bytes(b"\xff\xfe")
        (self.root / ".herd/tasks/t1/gate_blocks").unlink(missing_ok=True)
        self.assertEqual(self.stop(parent)["decision"], "block")

    def herd_command(self, log, command="python3 herd.py status"):
        herd.preinit({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(self.root),
                      "transcript_path": str(log)})

    def test_a_session_that_ran_a_herd_command_here_is_blocked_too(self):
        home = self.logs()
        (home / "next.jsonl").touch()
        (home / "link.jsonl").symlink_to(home / "next.jsonl")
        self.herd_command(home / "link.jsonl")
        for log in ("next.jsonl", "link.jsonl", "owner.jsonl"):  # the continuation, and still the owner
            with self.subTest(log=log):
                (self.root / ".herd/tasks/t1/gate_blocks").unlink(missing_ok=True)
                self.assertEqual(self.stop(home / log)["decision"], "block")
        self.assertIsNone(self.stop(home / "parent.jsonl"))  # never ran a herd command

    def test_only_the_last_herd_session_is_added(self):
        home = self.logs()
        self.herd_command(home / "other/owner.jsonl")
        self.herd_command(home / "parent.jsonl")
        self.herd_command(home / "other/owner.jsonl", command="ls")  # not a herd command: not recorded
        self.assertIsNone(self.stop(home / "other/owner.jsonl"))
        self.assertIsNotNone(self.stop(home / "parent.jsonl"))

    def test_a_broken_session_record_adds_no_session(self):
        home = self.logs()
        record = herd._session_path(self.root)
        for raw in (b"{", b"[]", b"7", b'{"log": 7}', b'{"log": "a\\u0000b"}', b"\xff\xfe"):
            with self.subTest(raw=raw):
                record.write_bytes(raw)
                (self.root / ".herd/tasks/t1/gate_blocks").unlink(missing_ok=True)
                self.assertIsNone(self.stop(home / "parent.jsonl"))
                self.assertIsNotNone(self.stop(home / "owner.jsonl"))

    def test_hook_input_of_the_wrong_shape_never_gives_a_traceback(self):
        self.logs()
        for raw in ("[]", "7", '"x"', '{"cwd": 7}', "{}"):
            with self.subTest(raw=raw):
                (self.root / ".herd/tasks/t1/gate_blocks").unlink(missing_ok=True)
                p = run_herd(self.root, "gate", input=raw)
                self.assertNotIn("Traceback", p.stderr)
                self.assertEqual(json.loads(p.stdout)["decision"], "block")
        p = run_herd(self.root, "gate", input="{")
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("Traceback", p.stderr)


class TestGateWithoutInit(Base):
    """Issue #124: a /herd:run session that edits files but never runs `herd init` is sent back to it."""
    RUN = ("<command-message>herd:run</command-message>\n<command-name>/herd:run</command-name>\n"
           "<command-args>Fix the typo in README.md</command-args>")

    def log(self, request=RUN, tools=(("Edit", {"file_path": "README.md", "old_string": "x", "new_string": "y"}),)):
        lines = [{"type": "user", "message": {"role": "user", "content": request}}]
        lines += [{"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": f"t{i}", "name": name, "input": inp}]}} for i, (name, inp) in enumerate(tools)]
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        path = Path(path)
        self.addCleanup(path.unlink, missing_ok=True)
        path.write_text("".join(json.dumps(x) + "\n" for x in lines))
        return path

    def stop(self, log):
        return herd.gate(self.root, {"transcript_path": str(log)})

    def test_blocks_then_releases_and_records_it(self):
        log = self.log()
        for i in range(1, herd.MAX_BLOCKS + 1):
            out = self.stop(log)
            self.assertEqual(out["decision"], "block")
            self.assertIn(f"({i}/{herd.MAX_BLOCKS} stop attempts blocked)", out["reason"])
            self.assertIn("init <slug>", out["reason"])
        self.assertIsNone(self.stop(log))
        record = json.loads((self.root / ".git" / herd.NOINIT_FILE).read_text())
        self.assertEqual(record[os.path.realpath(log)]["blocks"], herd.MAX_BLOCKS)
        self.assertIn("released", record[os.path.realpath(log)])
        self.assertEqual(self.stop(self.log())["decision"], "block")  # another session has its own budget

    def test_other_sessions_stop_freely(self):
        edit = ("Write", {"file_path": "a.txt", "content": "a"})
        init = ("Bash", {"command": "cd /x && python3 /p/scripts/herd.py init fix-typo \"Fix the typo\""})
        cases = {"no /herd:run": self.log(request="Fix the typo"),
                 "quoted /herd:run": self.log(request="say " + self.RUN),
                 "bare /herd:run": self.log(request="<command-name>/herd:run</command-name>\n<command-args></command-args>"),
                 "no edit": self.log(tools=(("Read", {"file_path": "README.md"}),)),
                 "ran herd init": self.log(tools=(edit, init)),
                 "missing log": self.root.parent / "gone.jsonl"}
        for name, log in cases.items():
            with self.subTest(name):
                self.assertIsNone(self.stop(log))
        for hook in ({}, {"transcript_path": None}, {"transcript_path": 7}, {"transcript_path": "a\0b"},
                     {"transcript_path": "\ud800"}):
            with self.subTest(hook=hook):
                self.assertIsNone(herd.gate(self.root, hook))
        self.assertFalse((self.root / ".git" / herd.NOINIT_FILE).exists())

    def test_herd_init_in_a_subagent_log_counts(self):
        log = self.log()
        sub = log.parent / log.stem / "subagents"
        sub.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, log.parent / log.stem)
        (sub / "agent-1.jsonl").write_text(json.dumps({"type": "assistant", "isSidechain": True, "message": {
            "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "python3 herd.py init t1 \"g\""}}]}}))
        self.assertIsNone(self.stop(log))  # a designer subagent started the task, since done

    def test_a_task_this_session_started_counts_as_init(self):
        init = ("Bash", {"command": 'H=/p/scripts/herd.py && python3 "$H" init t1 "g"'})  # not seen as an init
        log = self.log(tools=(("Write", {"file_path": "a.txt", "content": "a"}), init))
        self.assertEqual(self.stop(log)["decision"], "block")
        start = self.root / ".herd" / "tasks" / "t1" / "start.json"
        start.parent.mkdir(parents=True)
        start.write_text(json.dumps({"session": str(self.log())}))  # another session's task: still blocked
        self.assertEqual(self.stop(log)["decision"], "block")
        start.write_text(json.dumps({"session": str(log)}))  # done since, so no task is active
        self.assertIsNone(self.stop(log))

    def test_odd_content_items_do_not_crash(self):
        log = self.log()
        with log.open("a") as f:  # a string, a number and a null among the content items
            f.write(json.dumps({"type": "assistant", "message": {"content": ["text", 3, None]}}) + "\n")
        self.assertEqual(self.stop(log)["decision"], "block")

    def test_an_active_task_keeps_the_task_gate(self):
        self.task()
        self.assertIn("Herd task `t1`", self.stop(self.log())["reason"])



class TestReopen(Base):
    """Issue #145: a new /herd:run session that continues a finished task runs `herd reopen <slug>`."""
    RUN, log, stop = TestGateWithoutInit.RUN, TestGateWithoutInit.log, TestGateWithoutInit.stop

    def herd_command(self, log, command):
        herd.preinit({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(self.root),
                      "transcript_path": str(log)})

    def finished(self):
        """t1, started and finished by session A. Returns A's log."""
        a = self.log(request=self.RUN.replace("Fix the typo in README.md", "Given a name, when greet runs, then it "
                                              "prints hello"))
        self.herd_command(a, 'python3 herd.py init t1 "Add a greeting"')
        self.task(attacks=True)
        (self.root / "greet.txt").write_text("hello")
        herd.verify(self.root, "t1")
        p = run_herd(self.root, "done")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIsNone(self.stop(a))
        return a

    def start(self):
        return json.loads((self.root / ".herd/tasks/t1/start.json").read_text())

    def test_a_session_that_reopens_the_task_is_gated_as_its_owner(self):
        a, b = self.finished(), self.log()
        self.herd_command(b, "python3 herd.py reopen t1")
        p = run_herd(self.root, "reopen", "t1")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("reopened t1", p.stdout)
        self.assertEqual((self.root / ".herd/active").read_text().strip(), "t1")
        self.assertEqual((self.start()["session"], self.start()["sessions"]), (str(a), [str(b)]))
        (self.root / "greet.txt").write_text("hello again")  # the new edit: the old evidence no longer counts
        self.assertIn("evidence is stale", self.stop(b)["reason"])
        self.assertNotEqual(run_herd(self.root, "done").returncode, 0)
        herd.verify(self.root, "t1")
        self.assertEqual(run_herd(self.root, "done").returncode, 0)
        self.assertIsNone(self.stop(b))  # finished again: no "no Herd task was started" block
        self.assertFalse((self.root / ".git" / herd.NOINIT_FILE).exists())

    def test_reopen_twice_records_the_session_once(self):
        self.finished()
        b = self.log()
        self.herd_command(b, "python3 herd.py reopen t1")
        herd.reopen_task(self.root, "t1")
        herd.reopen_task(self.root, "t1")
        self.assertEqual(self.start()["sessions"], [str(b)])

    def test_a_session_that_neither_inits_nor_reopens_is_still_blocked(self):
        self.finished()
        b = self.log()
        for i in range(1, herd.MAX_BLOCKS + 1):
            self.assertIn(f"no Herd task was started ({i}/{herd.MAX_BLOCKS}", self.stop(b)["reason"])
        self.assertIsNone(self.stop(b))

    def test_reopen_of_a_cancelled_or_missing_task_is_refused(self):
        self.finished()
        herd.cancel_task(self.root, "t1", "dropped")
        for slug, why in (("t1", "was cancelled"), ("nope", "no task nope"), ("../x", "no task")):
            with self.subTest(slug=slug):
                p = run_herd(self.root, "reopen", slug)
                self.assertEqual(p.returncode, 1)
                self.assertIn(why, p.stderr)
        self.assertFalse((self.root / ".herd/active").exists())
        self.assertNotIn("sessions", self.start())
        self.assertEqual(run_herd(self.root, "reopen").returncode, 1)  # the slug is required

    def test_reopen_is_refused_while_another_task_is_active(self):
        self.finished()
        herd.init_task(self.root, "t2", "Another")
        with self.assertRaisesRegex(ValueError, "t2 is still active"):
            herd.reopen_task(self.root, "t1")

    def test_the_pre_init_hook_records_a_reopen(self):
        b = self.log()
        hook = json.dumps({"tool_name": "Bash", "tool_input": {"command": "python3 /p/scripts/herd.py reopen t1"},
                           "cwd": str(self.root), "transcript_path": str(b)})
        subprocess.run([sys.executable, str(Path(herd.__file__)), "preinit"], cwd=self.root, input=hook,
                       text=True, check=True)
        self.assertEqual(herd._seen_session(self.root), str(b))


class TestCli(Base):
    def run_cli(self, *args):
        p = subprocess.run(["python3", str(Path(herd.__file__)), *args], cwd=self.root,
                           capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr

    def test_flow(self):
        rc, out, _ = self.run_cli("init", "t1", "Add a greeting")
        self.assertEqual(rc, 0)
        no_design(self.root)
        (self.root / ".herd/tasks/t1/task.toml").write_text(TASK)
        self.assertEqual(self.run_cli("check")[0], 0)
        for a in herd.ATTACKS:
            flags = dict(PROGRAMS.get(a, {}))
            flags.update(flags.pop("extra", {}))
            programs = [x for k, v in flags.items() for x in (f"--{k}", v)]
            self.assertEqual(self.run_cli("note", "--tried", "--attack", a, "--check", OK, *programs, f"{a} attack")[0], 0)
        self.assertEqual(self.run_cli("verify")[0], 1)  # C1 failing
        (self.root / "greet.txt").write_text("hello")
        rc, out, _ = self.run_cli("verify")
        self.assertEqual(rc, 0)
        self.assertIn("1 passing", out)
        rc, out, _ = self.run_cli("done")
        self.assertEqual(rc, 0)
        self.assertFalse((self.root / ".herd/active").exists())
        self.assertTrue((self.root / ".herd/tasks/t1/evidence.md").exists())
        self.assertIn("done: evidence is fresh and passing", out)

    def test_done_without_review_at_medium_and_high_risk(self):
        for risk in ("medium", "high"):
            with self.subTest(risk=risk):
                shutil.rmtree(self.root / ".herd", ignore_errors=True)
                (self.root / "greet.txt").unlink(missing_ok=True)
                (self.root / "herd.toml").write_text(f'[floor]\n{risk} = ["greet.txt"]\n')
                self.task()
                (self.root / ".herd/active").write_text("t1\n")
                herd.verify(self.root, "t1")  # red
                (self.root / "greet.txt").write_text("hello")
                self.attacks()
                self.assertEqual(herd.verify(self.root, "t1")["risk"]["effective"], risk)
                self.assertEqual(herd.problems(self.root, "t1"), [])
                no_design(self.root)
                self.assertEqual(self.run_cli("done")[0], 0)

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
        run = lambda *a: run_herd(self.root, *a)
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
        p = run_herd(self.root, "done")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        (self.root / ".herd/tasks/t1/task.toml").write_text(TASK.replace("test -f greet.txt", "test -n x"))
        self.assertNotIn("zero tests", herd.report(herd.verify(self.root, "t1")))

    def test_cli_verify_marks_the_line(self):
        self.task("python3 -c \"print('collected 0 items')\"")
        p = run_herd(self.root, "verify")
        self.assertEqual(p.returncode, 0)
        self.assertIn("C1 passing (ran zero tests)", p.stdout)


class TestAttacks(Base):
    """On the standard route `herd done` needs a recorded attempt for each standard attack."""

    def run_cli(self, *args):
        return run_herd(self.root, *args)

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
        for a in ("collision", "one-bad-part", "recount", "refusal", "other-reading"):
            self.assertEqual(self.run_cli("note", "--tried", "--attack", a, f"n/a: {a} explained").returncode, 0)
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

    def break_step(self):
        return self.skill.split("3. **Break it**", 1)[1].split("\n4. ", 1)[0]

    def test_break_it_step_points_to_the_file_without_an_inline_list(self):
        s = self.break_step()
        self.assertIn("[adversarial.md](adversarial.md)", s)
        self.assertIn("herd done", s)
        self.assertIn("six standard attacks", s)
        for inline in ("bad input at every entry point", "collision", "one bad part", "recount", "refusal"):
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
        self.assertIn("cannot change a requested answer", rule)
        self.assertIn("a requested entry that is broken or unreachable always fails", rule)

    def test_existing_test_counts_only_if_it_meets_the_attack_rule(self):
        self.assertIn("counts for an attack only if it meets that attack's rule above", self.adv)
        self.assertIn("separate code for recount", self.adv)
        self.assertIn("every entry point for bad-input", self.adv)
        self.assertIn("Give that test as the `--check` and say what it covers", self.adv)
        self.assertNotIn("instead of probing again", self.adv)


class TestTaskBranch(Base):
    """A plain `herd init` puts the work on its own branch herd/<slug>, cut from the current one."""

    def cli(self, *args, cwd=None):
        return run_herd(cwd or self.root, *args)

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

    def test_init_from_an_unpushed_branch_records_its_upstream_as_the_base(self):
        # a branch made by `git worktree add -b work <path> origin/main` tracks origin/main and is not on origin
        start = self.branch()
        origin = self.root.parent / (self.root.name + "-up.git")
        try:
            subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
            git(self.root, "remote", "add", "origin", str(origin))
            git(self.root, "push", "-q", "origin", f"{start}:trunk")
            git(self.root, "fetch", "-q", "origin")
            git(self.root, "switch", "-q", "-c", "work", "--track", "origin/trunk")
            p = self.cli("init", "t1", "g")
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual((self.root / ".herd/tasks/t1/base").read_text().strip(), "trunk")
        finally:
            shutil.rmtree(origin, ignore_errors=True)

    def test_init_from_a_pushed_branch_keeps_it_as_the_base(self):
        start = self.branch()
        origin = self.root.parent / (self.root.name + "-up.git")
        try:
            subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
            git(self.root, "remote", "add", "origin", str(origin))
            git(self.root, "push", "-q", "-u", "origin", start)
            p = self.cli("init", "t1", "g")
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual((self.root / ".herd/tasks/t1/base").read_text().strip(), start)
        finally:
            shutil.rmtree(origin, ignore_errors=True)

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
        return run_herd(self.root, *args)

    def ready(self):
        self.task()
        (self.root / "greet.txt").write_text("hello")

    def test_attack_needs_a_command(self):
        self.ready()
        for a in herd.ATTACKS:  # each of the four attacks
            p = self.cli("note", "--tried", "--attack", a, "tried it")
            self.assertEqual(p.returncode, 1, a)
            self.assertIn("--check", p.stderr)
        self.assertEqual(herd.load_notes(self.root, "t1"), [])
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
        for a in ("collision", "one-bad-part", "refusal", "other-reading"):
            herd.add_note(self.root, "t1", "tried", a, attack=a, check=OK, **PROGRAMS.get(a, {}))
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
        for a in ("collision", "one-bad-part", "recount", "refusal", "other-reading"):
            herd.add_note(self.root, "t1", "tried", a, attack=a, check=OK, **PROGRAMS.get(a, {}))
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
        cmds = {"bad-input": [OK, "false"], "collision": [OK], "refusal": [OK], "other-reading": [OK],
                "recount": ["python3 -c \"print('Ran 0 tests')\""]}
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
        self.assertIn("Standard attacks without a passing command: bad-input (command fails), one-bad-part, recount, refusal, other-reading",
                      visible)

    def test_na_attack_counts_and_is_labelled(self):
        self.ready()
        for a in ("bad-input", "collision", "one-bad-part", "refusal", "other-reading"):
            herd.add_note(self.root, "t1", "tried", a, attack=a, check=OK, **PROGRAMS.get(a, {}))
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
        self.assertIn("missing: one-bad-part, recount, refusal, other-reading", text)
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

PR_TASK = TASK.replace('"Proves greet.txt exists; not what it says"', '"Only that the file exists"')


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
        no_design(self.root)
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
        no_design(self.root)
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
        (self.root / ".herd/tasks/t1/task.toml").write_text(PR_TASK.replace('"Only the file is checked, not its text"', '"Only ASCII names"'))
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
test_budget = "One file check"
known_limits = "none"
inputs = []

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
        no_design(path)
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
        p = run_herd(self.root, "gate", input=json.dumps({"cwd": str(sub)}))
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
        gate = run_herd(self.root, "gate", input=json.dumps({"cwd": str(deeper)}))
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
        p = run_herd(self.root, *args)
        out = p.stdout.strip().splitlines()
        if args[:1] == ("verify",):  # 0.4.0: one summary line for `herd check` warnings, budgeted on its own
            warn = [line for line in out if "herd check warning" in line]
            self.assertLessEqual(len(warn), 1, out)
            out = [line for line in out if line not in warn]
        return p.returncode, out

    # (1) short CLI output
    def test_cli_verify_prints_one_line_when_all_pass(self):
        rc, out = self.cli("verify")
        self.assertEqual((rc, len(out)), (0, 1), out)
        self.assertRegex(out[0], r"^2 passing, 0 failing, 0 unchecked \(checks took \d+\.\d s\)$")

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
        self.assertLessEqual(len(out), 10)  # 0.4.0: the result, the report path and the final report (six lines)
        self.assertEqual(sum(line.startswith(("Done:", "Proven:", "Not proven:", "Caveats:", "Decisions:",
                                              "Limits:")) for line in out), 6, out)
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
        budget = {"run": 1050, "criteria": 565, "evidence": 450}  # 0.4.0: rules the CLI enforces left the skill;
        # 0.5.0: +10 for resuming from the stop record; 0.6.0: +15 for the guard rule; 0.9.0: criteria +30 for `inputs`;
        # 0.10.0: criteria +20 for the top-level [[inputs]] example (a Haiku run put `inputs` inside [[criteria]])
        # 0.12.9: criteria +45 for `readings` (a sentence and an example line)
        # 0.12.13: criteria +30 for the sentence that the first reading quotes the request
        # 0.11.0: run +30 for an intake review step, given back in 0.12.0 when it was removed
        # 0.14.0: run +180 for who designs and who builds, and the second look (issue #102)
        # 0.14.12: run +25 for `herd reopen` (issue #145)
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
        self.assertLessEqual(words(visible), 200, visible)  # 0.4.0: + `herd check` warning lines
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


FIRST_ATTACK = next(iter(herd.ATTACKS))


class TestVerifyOnly(Base):
    """`herd verify --only <id>`: one check, nothing written, never counts for the gate."""

    def run_cli(self, *args):
        p = subprocess.run(["python3", str(Path(herd.__file__)), *args], cwd=self.root,
                           capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr

    def state(self):
        d = self.root / ".herd/tasks/t1"
        return {p.name: p.read_bytes() for p in d.iterdir() if p.is_file()}

    def test_only_writes_nothing(self):
        self.task(attacks=True)
        herd.verify(self.root, "t1")  # the red run, C1 failing
        rc, out, _ = self.run_cli("verify", "--only", "C1")
        self.assertEqual(rc, 1)
        self.assertIn("C1 failing", out)
        (self.root / "greet.txt").write_text("hello")
        before = self.state()
        rc, out, _ = self.run_cli("verify", "--only", "C1")
        self.assertEqual(rc, 0)
        self.assertRegex(out, r"C1 passing \(\d+(\.\d+)? s\)")
        self.assertEqual(self.state(), before)  # evidence.json, evidence.md, green.json, fails.json: none touched

    def test_only_runs_an_attack_by_name(self):
        self.task(attacks=True)
        herd.verify(self.root, "t1")
        before = self.state()
        rc, out, _ = self.run_cli("verify", "--only", FIRST_ATTACK)
        self.assertEqual(rc, 0)
        self.assertIn(f"{FIRST_ATTACK} passing", out)
        self.assertEqual(self.state(), before)

    def test_only_uses_the_latest_attack_note(self):
        self.task()
        herd.verify(self.root, "t1")
        a = FIRST_ATTACK
        herd.add_note(self.root, "t1", "tried", "old", attack=a, check="false")
        herd.add_note(self.root, "t1", "tried", "new", attack=a, check=OK, **PROGRAMS.get(a, {}))
        self.assertEqual(self.run_cli("verify", "--only", a)[0], 0)

    def test_only_timeout_prints_as_failing(self):
        self.task()
        herd.verify(self.root, "t1")
        herd.add_note(self.root, "t1", "tried", "slow", attack=FIRST_ATTACK, check="sleep 5", timeout=0.2)
        rc, out, _ = self.run_cli("verify", "--only", FIRST_ATTACK)
        self.assertEqual(rc, 1)
        self.assertIn("failing", out)
        self.assertIn("timeout", out)

    def test_only_does_not_satisfy_gate(self):
        self.task(attacks=True)
        (self.root / "greet.txt").write_text("hello")
        herd.verify(self.root, "t1")
        (self.root / "greet.txt").write_text("changed")  # an edit after the full verify
        self.assertEqual(self.run_cli("verify", "--only", "C1")[0], 0)
        self.assertIn("stale", herd.gate(self.root, {})["reason"])
        self.assertNotEqual(self.run_cli("done")[0], 0)  # herd done still refuses stale evidence
        self.assertTrue((self.root / ".herd/active").exists())

    def test_only_unknown_id(self):
        self.task(attacks=True)
        herd.verify(self.root, "t1")
        rc, out, err = self.run_cli("verify", "--only", "C9")
        self.assertEqual(rc, 1)
        for name in ("C1", "C2", FIRST_ATTACK):
            self.assertIn(name, out + err)

    def test_only_before_red_refuses(self):
        self.task()
        rc, out, err = self.run_cli("verify", "--only", "C1")
        self.assertEqual(rc, 1)
        self.assertIn("herd verify", out + err)
        self.assertFalse((self.root / ".herd/tasks/t1/red.json").exists())
        self.assertFalse((self.root / ".herd/tasks/t1/evidence.json").exists())

    def test_only_needs_an_id(self):
        self.task()
        rc, _, err = self.run_cli("verify", "--only")
        self.assertEqual(rc, 1)
        self.assertIn("usage: herd verify", err)

    def test_skill_verify_points(self):
        text = (Path(herd.__file__).parent.parent / "skills/run/SKILL.md").read_text()
        step = re.search(r"^7\. \*\*Verify\.\*\*.*$", text, re.M).group(0)
        self.assertNotIn("after every change", step)
        self.assertIn("once the work is done", step)
        self.assertIn("herd verify --only", step)

    def test_only_bad_input_ends_with_a_message(self):
        self.task()
        herd.verify(self.root, "t1")
        for args in (["--only", ""], ["--only", "c1"], ["--only", "C1; rm -rf x"], ["t1", "--only", "nope"],
                     ["--only", "C1", "--only", "C2"]):
            rc, out, err = self.run_cli("verify", *args)
            self.assertIn(rc, (0, 1), args)
            self.assertNotIn("Traceback", out + err, args)
        rc, _, err = self.run_cli("verify", "nosuchtask", "--only", "C1")
        self.assertEqual(rc, 1)
        self.assertNotIn("Traceback", err)

    def test_only_with_a_slug_and_verbose(self):
        self.task()
        herd.verify(self.root, "t1")
        (self.root / "greet.txt").write_text("hello")
        rc, out, _ = self.run_cli("verify", "t1", "--verbose", "--only", "C1")
        self.assertEqual((rc, out.split()[:2]), (0, ["C1", "passing"]))

    def test_only_collision_the_latest_attack_note_wins_both_ways(self):
        self.task()
        herd.verify(self.root, "t1")
        herd.add_note(self.root, "t1", "tried", "good", attack=FIRST_ATTACK, check=OK)
        herd.add_note(self.root, "t1", "tried", "later and broken", attack=FIRST_ATTACK, check="false")
        self.assertEqual(self.run_cli("verify", "--only", FIRST_ATTACK)[0], 1)
        herd.add_note(self.root, "t1", "tried", "n/a: nothing to test", attack="collision")
        rc, out, _ = self.run_cli("verify", "--only", "collision")  # an n/a note has no command to run
        self.assertEqual(rc, 1)
        self.assertIn("no criterion or attack", out)

    def test_only_one_bad_part_other_checks_do_not_matter(self):
        self.task()
        herd.verify(self.root, "t1")
        herd.add_note(self.root, "t1", "tried", "broken", attack="collision", check="false")
        (self.root / "greet.txt").write_text("hello")
        self.assertEqual(self.run_cli("verify", "--only", "C1")[0], 0)  # C2 is unchecked, collision fails
        self.assertEqual(self.run_cli("verify", "--only", "C2")[0], 1)  # an unchecked criterion is not passing

    def test_only_recount_reports_the_real_time(self):
        self.task()
        herd.verify(self.root, "t1")
        herd.add_note(self.root, "t1", "tried", "slow", attack=FIRST_ATTACK, check="python3 -c 'import time; time.sleep(1.2)'")
        began = time.monotonic()
        rc, out, _ = self.run_cli("verify", "--only", FIRST_ATTACK)
        wall = time.monotonic() - began
        secs = int(re.search(r"\((\d+) s\)", out).group(1))
        self.assertEqual(rc, 0)
        self.assertTrue(1 <= secs <= wall + 1, (secs, wall))


class TestCoveredBy(Base):
    """recount, refusal and other-reading may reuse a criterion's check instead of a command (issue #85)."""

    COVERABLE = ("recount", "refusal", "other-reading")

    def cli(self, *args):
        return run_herd(self.root, *args)

    def note(self, attack, cid="C1", *more):
        return self.cli("note", "--tried", "--attack", attack, "--covered-by", cid, *more, "covers it")

    def real_check(self, check=OK + " && test -f greet.txt"):
        self.task(TASK.replace('check = "test -f greet.txt"', f"check = {json.dumps(check)}"))

    def states(self, ev):
        return {a["attack"]: a["status"] for a in ev["attacks"]}

    def test_covered_by_is_accepted_and_follows_the_criterion(self):
        self.real_check()
        for a in self.COVERABLE:
            p = self.note(a)
            self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.states(herd.verify(self.root, "t1")), dict.fromkeys(self.COVERABLE, "failing"))
        (self.root / "greet.txt").write_text("hello")
        ev = herd.verify(self.root, "t1")
        self.assertEqual(self.states(ev), dict.fromkeys(self.COVERABLE, "passing"))
        self.assertIn("recount passing (`--covered-by C1`)", herd.report(ev))
        for a in ("bad-input", "collision", "one-bad-part"):
            herd.add_note(self.root, "t1", "tried", f"n/a: {a}", attack=a)
        herd.add_note(self.root, "t1", "tried", "with its example", attack="other-reading", covered_by="C1",
                      **PROGRAMS["other-reading"])
        herd.verify(self.root, "t1")
        self.assertNotIn("attack", " ".join(herd.problems(self.root, "t1")))
        (self.root / "greet.txt").unlink()
        herd.verify(self.root, "t1")
        self.assertIn("recount (its command fails)", " ".join(herd.problems(self.root, "t1")))

    def test_covered_by_an_unchecked_criterion_never_passes(self):
        self.real_check()
        self.assertEqual(self.note("recount", "C2").returncode, 0)
        self.assertEqual(self.states(herd.verify(self.root, "t1")), {"recount": "nocheck"})

    def test_covered_by_a_check_that_proves_nothing_does_not_count(self):
        self.real_check("true")
        self.note("recount")
        herd.verify(self.root, "t1")
        self.assertIn("recount (its command runs no project code)", " ".join(herd.problems(self.root, "t1")))

    def test_covered_by_works_with_verify_only(self):
        self.real_check()
        herd.verify(self.root, "t1")
        self.note("recount")
        self.assertEqual(self.cli("verify", "--only", "recount").returncode, 1)
        (self.root / "greet.txt").write_text("hello")
        self.assertEqual(self.cli("verify", "--only", "recount").returncode, 0)

    def test_covered_by_logged_after_the_last_verify_must_run(self):
        self.real_check()
        (self.root / "greet.txt").write_text("hello")
        herd.add_note(self.root, "t1", "tried", "a", attack="recount", check=OK)
        herd.verify(self.root, "t1")
        self.note("recount")
        self.assertIn("have not run", " ".join(herd.problems(self.root, "t1")))

    def test_covered_by_refused_for_other_attacks_and_unknown_ids(self):
        self.real_check()
        for attack, cid in [(a, "C1") for a in ("bad-input", "collision", "one-bad-part")] + [
                (a, c) for a in self.COVERABLE for c in ("C9", "c1", "")]:
            p = self.note(attack, cid)
            self.assertEqual(p.returncode, 1, (attack, cid))
            self.assertIn("--covered-by", p.stderr)
            self.assertNotIn("Traceback", p.stderr)
        self.assertEqual(self.note("recount", "C1", "--check", OK).returncode, 1)
        self.assertEqual(herd.load_notes(self.root, "t1"), [])

    def test_covered_by_keeps_example(self):
        self.real_check()
        (self.root / "greet.txt").write_text("hello")
        toml = (self.root / ".herd/tasks/t1/task.toml").read_text()
        herd.cancel_task(self.root, "t1")
        herd.init_task(self.root, "t2", "Change auth/session.py")  # high risk by path
        (self.root / ".herd/tasks/t2/task.toml").write_text(toml)
        herd.add_note(self.root, "t2", "tried", "no example", attack="other-reading", covered_by="C1")
        ev = herd.verify(self.root, "t2")
        self.assertTrue(herd.full_rules(ev))
        missing = " ".join(herd.missing_programs(ev))
        self.assertIn("other-reading has no --example", missing)
        self.assertIn("--covered-by C1", missing)
        herd.add_note(self.root, "t2", "tried", "broken", attack="other-reading", covered_by="C1", example="exit 3")
        ev = herd.verify(self.root, "t2")
        self.assertEqual(self.states(herd.verify(self.root, "t2"))["other-reading"], "failing")
        herd.add_note(self.root, "t2", "tried", "ok", attack="other-reading", covered_by="C1",
                      **PROGRAMS["other-reading"])
        ev = herd.verify(self.root, "t2")
        self.assertEqual(ev["attacks"][-1]["status"], "passing")
        self.assertEqual(herd.missing_programs(ev), [])

    def test_covered_by_before_first_verify(self):
        self.real_check()
        self.note("recount")
        ev = herd.verify(self.root, "t1")
        self.assertNotIn("recount attack", " ".join(ev["warnings"]))
        self.note("refusal")
        ev = herd.verify(self.root, "t1")
        self.assertIn("refusal attack was logged after the first verify", " ".join(ev["warnings"]))


class TestStatusNoTask(Base):
    """`herd status` before any task is a normal state: exit 0, hint on stdout. Every other no-task case still
    exits 1 with its message on stderr (issue #116)."""

    def status(self, *args):
        return run_herd(self.root, "status", *args)

    def add_task(self, slug):
        (self.root / ".herd/tasks" / slug).mkdir(parents=True)
        (self.root / ".herd/tasks" / slug / "task.toml").write_text(TASK)

    def test_no_task_exits_0_hint_on_stdout(self):
        p = self.status()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('no active task: run herd init <slug> "<goal>"', p.stdout)
        self.assertIn("Design:", p.stdout)
        self.assertEqual(p.stderr, "")

    def test_no_task_json_null_exits_0(self):
        p = self.status("--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), "null")

    def test_several_tasks_none_active_exits_1(self):
        self.add_task("t1")
        self.add_task("t2")
        p = self.status()
        self.assertEqual(p.returncode, 1)
        self.assertIn("pass one of: t1, t2", p.stderr)
        self.assertNotIn("no active task: run", p.stdout)

    def test_tasks_in_other_worktrees_exits_1(self):
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        (self.root / ".herd/elsewhere").mkdir(parents=True)
        (self.root / ".herd/elsewhere/t9").write_text(other.name)
        p = self.status()
        self.assertEqual(p.returncode, 1)
        self.assertIn("t9 in " + other.name, p.stderr)
        self.assertNotIn("no active task: run", p.stdout)

    def test_broken_herd_toml_exits_1(self):
        (self.root / "herd.toml").write_text("[models\n")
        for args in ((), ("--json",)):
            with self.subTest(args=args):
                p = self.status(*args)
                self.assertEqual(p.returncode, 1, p.stdout)
                self.assertIn("herd.toml", p.stderr)
                self.assertNotIn("Traceback", p.stderr)

    def test_bad_input_status(self):
        (self.root / "herd.toml").write_text("[models\n")
        for args in ((), ("--json",)):
            with self.subTest(args=args):
                p = self.status(*args)
                self.assertEqual(p.returncode, 1, p.stdout)
                self.assertNotIn("Traceback", p.stderr)
        self.add_task("t1")
        p = self.status("nope")  # an unknown slug is not a no-task case: its own message, never the hint
        self.assertNotIn("no active task: run herd init", p.stdout)
        self.assertNotIn("Traceback", p.stderr)

    def test_refusals_match_independent_count(self):
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        layouts = {
            "several tasks": lambda: (self.add_task("t1"), self.add_task("t2")),
            "other worktree": lambda: ((self.root / ".herd/elsewhere").mkdir(parents=True),
                                       (self.root / ".herd/elsewhere/t9").write_text(other.name)),
        }
        for name, make in layouts.items():
            with self.subTest(layout=name):
                make()
                tasks_dir, moved_dir = self.root / ".herd/tasks", self.root / ".herd/elsewhere"
                tasks = [p for p in tasks_dir.iterdir() if (p / "task.toml").exists()] if tasks_dir.exists() else []
                moved = list(moved_dir.iterdir()) if moved_dir.exists() else []
                self.assertTrue(len(tasks) >= 2 or moved, name)  # independent count of the layout
                p = self.status()
                self.assertEqual(p.returncode, 1, p.stdout)
                self.assertTrue(p.stderr.strip())
                self.assertNotIn("no active task: run herd init", p.stdout)
                shutil.rmtree(self.root / ".herd")

    def test_no_task_readings(self):
        p = self.status()  # no .herd folder at all
        self.assertEqual(p.returncode, 0, p.stderr)
        (self.root / ".herd/tasks").mkdir(parents=True)  # an empty .herd/tasks folder
        p = self.status()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("no active task: run herd init", p.stdout)


class TestInitIgnoresHerd(Base):
    """A plain or quick `herd init` keeps .herd/ out of `git status` and `git add -A` (issue #116)."""

    def porcelain(self, cwd=None):
        return subprocess.run(["git", "status", "--porcelain"], cwd=cwd or self.root, capture_output=True,
                              text=True, check=True).stdout

    def test_plain_init_hides_herd_from_git_status(self):
        p = run_herd(self.root, "init", "t1", "Add a greeting")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue((self.root / ".herd/tasks/t1").exists())
        self.assertNotIn(".herd", self.porcelain())

    def test_quick_init_hides_herd_from_git_status(self):
        p = run_herd(self.root, "init", "q1", "Fix typo", "--quick", "true")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn(".herd", self.porcelain())

    def test_git_add_all_does_not_stage_herd(self):
        run_herd(self.root, "init", "t1", "Add a greeting")
        git(self.root, "add", "-A")
        staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=self.root, capture_output=True,
                                text=True, check=True).stdout
        self.assertNotIn(".herd", staged)

    def test_exclude_line_not_duplicated(self):
        self.assertEqual(run_herd(self.root, "init", "t1", "Add a greeting").returncode, 0)
        p = run_herd(self.root, "init", "t1", "Another goal")  # refused: the task exists
        self.assertNotEqual(p.returncode, 0)
        lines = (self.root / ".git/info/exclude").read_text().splitlines()
        self.assertEqual(lines.count(".herd/"), 1)

    def test_init_readings(self):
        exclude = self.root / ".git/info/exclude"
        with tempfile.TemporaryDirectory() as td:  # a linked worktree: init there hides .herd/ too
            wt = Path(td) / "wt"
            git(self.root, "worktree", "add", "-q", "-b", "wt1", str(wt), "HEAD")
            p = run_herd(wt, "init", "t2", "Add a greeting")
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertNotIn(".herd", self.porcelain(cwd=wt))
            git(self.root, "worktree", "remove", "--force", str(wt))
        # the exclude file is shared by linked worktrees: drop the line the worktree init wrote, then list it by hand
        kept = [line for line in exclude.read_text().splitlines() if line != ".herd/"]
        exclude.write_text("".join(line + "\n" for line in kept) + ".herd/\n")
        p = run_herd(self.root, "init", "t1", "Add a greeting")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn(".herd", self.porcelain())
        self.assertEqual(exclude.read_text().splitlines().count(".herd/"), 1)


if __name__ == "__main__":
    unittest.main()
