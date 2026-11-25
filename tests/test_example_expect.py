"""`--example` needs `--expect`: a text solved by hand, frozen at the first verify (issue #93).

`python3 -m tests.test_example_expect example|contradictory|empty` runs one case for --example or --refuses."""
import contextlib
import io
import json
import random
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import herd
from tests.test_harness_rules import OK, Base
from tests.test_herd_cli import TASK, run_herd

PROG = "import json, sys\ncode, out, err = json.loads(sys.argv[1])\nsys.stdout.write(out); sys.stderr.write(err); sys.exit(code)\n"


def cmd(code=0, out="aisle 3\n", err=""):
    return "python3 prog.py " + shlex.quote(json.dumps([code, out, err]))


def should_pass(code, out, expect):
    """The rule in the issue, written again: exit 0, some stdout, and the trimmed expected text found in it."""
    return code == 0 and out.split() != [] and out.find(expect.strip()) >= 0


class Case(Base):
    def setUp(self):
        super().setUp()
        self.start()
        (self.root / "prog.py").write_text(PROG)

    def note(self, example=None, expect=None, changed=None, check=OK, root=None):
        args = ["note", "--tried", "--attack", "other-reading", "--check", check, "--example", example or cmd()]
        args += [] if expect is None else ["--expect", expect]
        args += [] if changed is None else ["--expect-changed", changed]
        return run_herd(root or self.root, *args, "hand-solved case")

    def logged(self, **kw):
        p = self.note(**kw)
        self.assertEqual(p.returncode, 0, p.stderr)

    def fresh(self):
        """A task not verified yet, so the next case may set any expected text."""
        for f in ("frozen.json", "red.json", "evidence.json", "notes.jsonl"):
            (self.root / ".herd/tasks/t1" / f).unlink(missing_ok=True)

    def entry(self):
        return herd.verify(self.root, "t1")["attacks"][-1]

    def notes(self):
        return herd.load_notes(self.root, "t1")


class TestStores(Case):
    def test_stores_the_expected_text(self):
        self.logged(expect="aisle 3")
        n = self.notes()[-1]
        self.assertEqual((n["example"], n["expect"]), (cmd(), "aisle 3"))
        self.assertEqual(self.entry()["expect"], "aisle 3")


class TestPasses(Case):
    def test_passes_only_on_exit_0_stdout_and_the_text(self):
        for c, expect, ok in ((cmd(), "aisle 3", True), (cmd(), "  aisle 3 \n", True), (cmd(1), "aisle 3", False),
                              (cmd(out=""), "aisle 3", False), (cmd(out="  \n", err="aisle 3"), "aisle 3", False),
                              (cmd(out="aisle 4"), "aisle 3", False), (cmd(out="Aisle 3"), "aisle 3", False),
                              (cmd(out="aisle  3"), "aisle 3", False), (cmd(out="x" * 5000 + " end"), "xx", True)):
            with self.subTest(c=c[:60], expect=expect):
                self.fresh()
                self.logged(example=c, expect=expect)
                self.assertEqual(self.entry()["status"], "passing" if ok else "failing")

    def test_passes_only_with_an_expected_text(self):
        self.logged()
        a = self.entry()
        self.assertEqual(a["status"], "failing")
        self.assertIn("--expect", a["program_fault"])

    def test_passes_only_also_in_verify_only(self):
        herd.verify(self.root, "t1")
        self.logged(expect="aisle 9", changed="first expected text")
        ok, lines = herd.verify_only(self.root, "t1", "other-reading")
        self.assertFalse(ok)
        self.assertIn("stdout does not contain", "\n".join(lines))


class TestFrozen(Case):
    def test_frozen_at_the_first_verify(self):
        self.logged(expect="aisle 1")
        self.logged(expect="aisle 3")  # before the first verify: free to change
        herd.verify(self.root, "t1")
        self.logged(expect=" aisle 3 ")  # the same text
        p = self.note(expect="aisle 4")
        self.assertEqual(p.returncode, 1)
        self.assertIn("--expect-changed", p.stderr)
        self.logged(example=cmd(out="aisle 4"), expect="aisle 4", changed="miscounted by hand")
        ev = herd.verify(self.root, "t1")
        text = "\n".join(herd.final_report(self.root, "t1", ev, self.notes()))
        for want in ("aisle 3", "aisle 4", "miscounted by hand"):
            self.assertIn(want, text)
        self.assertIn("miscounted by hand", herd.report(ev))
        self.assertIn("miscounted by hand", herd.pr_body(self.root, "t1"))

    def test_frozen_even_when_nothing_was_expected_at_red(self):
        herd.verify(self.root, "t1")
        self.assertEqual(self.note(expect="aisle 3").returncode, 1)
        self.logged()  # a note without --expect does not set one
        self.assertEqual(self.note(expect="aisle 3").returncode, 1)
        self.logged(expect="aisle 3", changed="no example was logged before red")

    def test_frozen_survives_a_note_without_it_and_a_deleted_file(self):
        self.logged(expect="aisle 3")
        herd.verify(self.root, "t1")
        herd.add_note(self.root, "t1", "tried", "n/a: gone", attack="other-reading")
        self.logged()
        (self.root / ".herd/tasks/t1/frozen.json").unlink()
        self.assertEqual(self.note(expect="aisle 4").returncode, 1)

    def test_frozen_flags_are_checked(self):
        for kw in ({"expect": " "}, {"expect": "a", "changed": "not yet verified"}):
            self.assertEqual(self.note(**kw).returncode, 1, kw)
        herd.verify(self.root, "t1")
        self.assertEqual(self.note(expect="a", changed="  ").returncode, 1)
        self.logged(expect="a", changed="why")
        self.assertEqual(self.note(expect="a", changed="nothing changed").returncode, 1)


class TestRequiredEveryRisk(unittest.TestCase):
    def probs(self, route="standard", risk="low", **latest):
        a = dict({"attack": "other-reading", "status": "passing", "check": OK, "text": "t"}, **latest)
        return " ".join(herd.missing_programs({"route": route, "risk": {"effective": risk}, "attacks": [a]}))

    def test_required_every_risk(self):
        for risk in herd.LEVELS:
            with self.subTest(risk=risk):
                self.assertIn("--example", self.probs(risk=risk))
                self.assertIn("--expect", self.probs(risk=risk, example="p"))
                self.assertEqual(self.probs(risk=risk, example="p", expect="x"), "")
                self.assertEqual(self.probs(risk=risk, status="na", text="n/a: takes no input"), "")

    def test_required_every_risk_but_not_quick_and_nothing_else_at_low(self):
        self.assertEqual(self.probs(route="quick"), "")
        self.assertEqual(self.probs(attack="one-bad-part"), "")


class TestRequiredDone(Case):
    def test_required_every_risk_done_refuses_at_low(self):
        self.red_then_build()
        for a in herd.ATTACKS:
            if a != "other-reading":
                herd.add_note(self.root, "t1", "tried", "n/a: cannot apply", attack=a)
        herd.add_note(self.root, "t1", "tried", "no example", attack="other-reading", check=OK)
        ev = herd.verify(self.root, "t1")
        ev["risk"]["effective"] = "low"
        self.assertIn("other-reading has no --example", " ".join(herd.attack_problems(self.root, "t1", ev)))

    def test_required_every_risk_na_needs_a_reason(self):
        for text in ("n/a:", "n/a:   "):
            with self.assertRaises(ValueError):
                herd.add_note(self.root, "t1", "tried", text, attack="other-reading")


class TestReport(Case):
    def test_report_shows_command_text_and_output(self):
        c = cmd(out="header\naisle 3\ntotal 7\n")
        self.logged(example=c, expect="aisle 3")
        ev = herd.verify(self.root, "t1")
        for text in ("\n".join(herd.final_report(self.root, "t1", ev, self.notes())), herd.report(ev)):
            for want in (c, '"aisle 3"', "total 7"):
                self.assertIn(want, text)
        self.assertNotIn("total 7", herd.pr_body(self.root, "t1").replace(c, ""))  # output stays out of the PR


class TestReportShape(Case):
    def test_report_keeps_a_piped_multiline_command_on_one_line(self):
        self.logged(example="echo aisle 3 |\ncat", expect="aisle 3")
        ev = herd.verify(self.root, "t1")
        for text in ("\n".join(herd.final_report(self.root, "t1", ev, self.notes())), herd.report(ev)):
            self.assertIn("Example: `echo aisle 3 | cat`", text)


class TestBadInput(Case):
    def test_bad_input_one_message_no_traceback(self):
        base = ["note", "--tried", "--attack", "other-reading", "--check", OK, "--example", "p"]
        bad = [base + ["x", "--expect"], base + ["--expect", "", "x"], base + ["--expect-changed", "r", "x"],
               base + ["--expect", "a", "x", "--expect-changed"],
               ["note", "--tried", "--attack", "other-reading", "--check", OK, "--expect", "a", "x"],
               ["note", "--tried", "--attack", "bad-input", "--check", OK, "--expect", "a", "x"],
               ["note", "--found", "--expect", "a", "x"]]
        for args in bad:
            p = run_herd(self.root, *args)
            self.assertNotEqual(p.returncode, 0, args)
            self.assertNotIn("Traceback", p.stderr, args)
        self.assertEqual(self.notes(), [])

    def test_bad_input_expected_text_that_is_not_utf8(self):
        p = self.note(expect="\udcff1")
        self.assertEqual(p.returncode, 1)
        self.assertIn("not valid UTF-8", p.stderr)
        self.assertEqual(self.notes(), [])

    def test_bad_input_undecodable_stdout(self):
        self.logged(example="printf '\\377 ok' | cat", expect="ok")
        self.assertEqual(self.entry()["status"], "passing")


class TestCollision(Case):
    def test_collision_same_command_two_texts_both_judged(self):
        self.logged(expect="aisle 3")
        self.logged(expect="aisle 4")
        got = [a["status"] for a in herd.verify(self.root, "t1")["attacks"]]
        self.assertEqual(got, ["passing", "failing"])

    def test_collision_a_flag_given_twice_is_refused(self):
        self.assertNotEqual(contradictory(self.root).returncode, 0)
        self.assertEqual(self.notes(), [])


class TestOneBadPart(Case):
    def test_one_bad_part_an_empty_text_is_refused_not_skipped(self):
        p = self.note(expect="\n ")
        self.assertEqual(p.returncode, 1)
        self.assertIn("needs a text", p.stderr)
        self.assertEqual(self.notes(), [])


class TestRecount(Case):
    def test_recount_every_change_is_listed_once(self):
        rng = random.Random(93)
        self.logged(expect="v0")
        herd.verify(self.root, "t1")
        value, want = "v0", []
        for i in range(25):
            new = f"v{rng.randrange(4)}"
            self.logged(expect=new, changed=None if new == value else f"reason-{i}.")
            if new != value:
                want.append(f"reason-{i}.")
            value = new
        ev = herd.verify(self.root, "t1")
        line = herd.final_report(self.root, "t1", ev, self.notes())[2]
        self.assertEqual(line.count("Expected text changed"), len(want))
        self.assertEqual([w for w in want if w not in line], [])


class TestRefusal(Case):
    def test_refusal_generated_outputs_match_the_rule(self):
        rng = random.Random(930)
        words = ("a", "A", " ", "\n", ".*", "é", "3", "[x]")
        cases = []
        for _ in range(60):
            out = "".join(rng.choices(words, k=rng.randrange(6)))
            expect = "".join(rng.choices(words, k=rng.randrange(1, 4))).strip() or "a"
            cases.append((rng.choice((0, 0, 0, 1)), out, expect))
        for code, out, expect in cases:
            self.logged(example=cmd(code, out), expect=expect)
        got = [a["status"] == "passing" for a in herd.verify(self.root, "t1")["attacks"]]
        self.assertEqual(got, [should_pass(*c) for c in cases])
        self.assertTrue(any(got) and not all(got))

    def test_refusal_of_changes_matches_the_rule(self):
        rng = random.Random(931)
        value, verified = None, False
        for i in range(40):
            if i == 8:
                herd.verify(self.root, "t1")
                verified = True
            new = rng.choice(("a", " a ", "b", None))
            changed = rng.choice((None, "why"))
            differs = new is not None and new.strip() != value
            if new is None:
                ok = changed is None
            else:
                ok = (changed is not None) == (verified and differs)
            p = self.note(expect=new, changed=changed)
            self.assertEqual(p.returncode == 0, ok, (i, new, changed, value, p.stderr))
            if ok and new is not None:
                value = new.strip()


class TestOtherReading(Case):
    """Readings of "expected text": literal, not a pattern; part of the output, not a whole line; ends trimmed."""

    def test_other_reading_literal_substring(self):
        for out, expect, ok in (("a.c", "a.c", True), ("abc", "a.c", False), ("total: 12 eur", "12", True),
                                ("one\ntwo\n", "one\ntwo", True), ("one two", "one\ntwo", False),
                                ("--x y", " --x y\n", True), ("'q' \"r\" $s", "'q' \"r\" $s", True)):
            with self.subTest(out=out, expect=expect):
                self.fresh()
                self.logged(example=cmd(out=out), expect=expect)
                self.assertEqual(self.entry()["status"] == "passing", ok)


def contradictory(root):
    return run_herd(root, "note", "--tried", "--attack", "other-reading", "--check", OK, "--example", "p",
                    "--expect", "a", "--expect", "b", "x")


def one_case(case):
    """In a throwaway project: herd's own output and exit code."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        herd.init_task(root, "t1", "demo")
        (root / ".herd/tasks/t1/task.toml").write_text(TASK)
        (root / "prog.py").write_text(PROG)
        note = ["note", "--tried", "--attack", "other-reading", "--check", OK, "--example", cmd()]
        if case == "contradictory":
            p = contradictory(root)
        elif case == "empty":
            p = run_herd(root, *note, "--expect", " ", "x")
        else:  # example: the hand-solved case, seen by verify
            run_herd(root, *note, "--expect", "aisle 3", "x")
            with contextlib.redirect_stdout(io.StringIO()):
                a = herd.verify(root, "t1")["attacks"][-1]
            print(f"other-reading {a['status']} expected={a.get('expect')}")
            return 0
        sys.stdout.write(p.stdout)
        sys.stderr.write(p.stderr)
        return p.returncode


if __name__ == "__main__":
    if sys.argv[1:] and sys.argv[1] in ("example", "contradictory", "empty"):
        sys.exit(one_case(sys.argv[1]))
    unittest.main()
