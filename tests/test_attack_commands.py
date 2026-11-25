"""`--refuses` and `--example`: Herd runs the program itself for two attack claims (0.12.12, issue #66)."""
import unittest
from pathlib import Path

from scripts import herd
from tests.test_harness_rules import OK, Base
from tests.test_herd_cli import late_review

# a stand-in program: knows one item, written as a name or `name x2`
PROG = '''import sys
arg = sys.argv[1] if len(sys.argv) > 1 else ""
if arg.split(" x")[0] != "milk":
    sys.exit(f"unknown item: {arg}")
print("aisle 3")
'''
REFUSES, EXAMPLE = "python3 prog.py nosuch", "python3 prog.py 'milk x2'"
PLACE = {"refuses": ("bad-input", "one-bad-part"), "example": ("other-reading",)}


class Attacks(Base):
    def built(self):
        self.start()
        self.red_then_build()
        (self.root / "prog.py").write_text(PROG)

    def log(self, refuses=REFUSES, example=EXAMPLE, na=()):
        for a in herd.ATTACKS:
            if a in na:
                herd.add_note(self.root, "t1", "tried", "n/a: cannot apply here", attack=a)
                continue
            extra = {"collision": {"refuses": refuses}, "one-bad-part": {"refuses": refuses}, "other-reading": {"example": example}}.get(a, {})
            herd.add_note(self.root, "t1", "tried", f"{a} attack", attack=a, check=OK, **extra)

    def run_all(self):
        late_review(self.root)
        ev = herd.verify(self.root, "t1")
        return ev, herd._attack_states(ev["attacks"]), " ".join(herd.problems(self.root, "t1"))


class TestRefuses(Attacks):
    def state(self, cmd, attack="one-bad-part"):
        herd.add_note(self.root, "t1", "tried", "refused", attack=attack, check=OK, refuses=cmd)
        return herd._attack_states(herd.verify(self.root, "t1")["attacks"])[attack][0]

    def test_stored_by_the_cli_and_run_by_verify(self):
        self.built()
        for attack in PLACE["refuses"]:
            p = self.cli("note", "--tried", "--attack", attack, "--check", OK, "--refuses", REFUSES, "x")
            self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual([n["refuses"] for n in herd.load_notes(self.root, "t1")], [REFUSES, REFUSES])
        states = herd._attack_states(herd.verify(self.root, "t1")["attacks"])
        self.assertEqual([states[a][0] for a in PLACE["refuses"]], ["passing", "passing"])
        self.assertIn(REFUSES, states["bad-input"][1])

    def test_only_a_real_refusal_passes(self):
        self.built()
        cases = {REFUSES: "passing",
                 "python3 prog.py milk": "failing",  # exits 0
                 "python3 -c \"import sys; sys.exit(3)\"": "failing",  # nothing on stderr
                 "python3 -c \"import sys; print('no'); sys.exit(1)\"": "failing",  # stdout only
                 "python3 -c \"raise KeyError('nosuch')\"": "failing",  # traceback
                 "python3 -c \"import sys; print('Traceback'); sys.exit('bad')\"": "failing",
                 "./no-such-program x": "failing",  # the shell could not run it
                 "python3 -c \"import os; os.kill(os.getpid(), 9)\"": "failing"}  # a crash, not a refusal
        for cmd, want in cases.items():
            with self.subTest(cmd=cmd):
                self.assertEqual(self.state(cmd), want)

    def test_the_failure_says_which_command_and_why(self):
        self.built()
        self.state("python3 prog.py milk")
        ev = herd.verify(self.root, "t1")
        what = herd._attack_states(ev["attacks"])["one-bad-part"][1]
        self.assertIn("--refuses python3 prog.py milk", what)
        self.assertIn("exit 0", what)

    def test_a_failing_check_still_fails(self):
        self.built()
        herd.add_note(self.root, "t1", "tried", "x", attack="bad-input", check="false", refuses=REFUSES)
        self.assertEqual(herd._attack_states(herd.verify(self.root, "t1")["attacks"])["bad-input"][0], "failing")

    def test_timeout_fails(self):
        self.built()
        herd.add_note(self.root, "t1", "tried", "x", attack="bad-input", check=OK, timeout=0.5,
                      refuses="python3 -c \"import time; time.sleep(5)\"")
        self.assertEqual(herd._attack_states(herd.verify(self.root, "t1")["attacks"])["bad-input"][0], "failing")

    def test_verify_only_runs_it(self):
        self.built()
        herd.add_note(self.root, "t1", "tried", "x", attack="bad-input", check=OK, refuses="python3 prog.py milk")
        ok, lines = herd.verify_only(self.root, "t1", "bad-input")
        self.assertFalse(ok)
        self.assertIn("python3 prog.py milk", "\n".join(lines))

    def test_wrong_attack_no_check_or_empty_is_refused(self):
        self.built()
        for kw in ({"attack": "recount", "check": OK, "refuses": REFUSES},
                   {"attack": "other-reading", "check": OK, "refuses": REFUSES},
                   {"attack": "bad-input", "refuses": REFUSES},
                   {"attack": "bad-input", "check": OK, "refuses": "  "},
                   {"refuses": REFUSES}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                herd.add_note(self.root, "t1", "tried", "n/a: x", **kw)
        self.assertEqual(herd.load_notes(self.root, "t1"), [])


class TestExample(Attacks):
    def state(self, cmd):
        herd.add_note(self.root, "t1", "tried", "literal form", attack="other-reading", check=OK, example=cmd)
        return herd._attack_states(herd.verify(self.root, "t1")["attacks"])["other-reading"][0]

    def test_stored_by_the_cli_and_passes_only_on_exit_0(self):
        self.built()
        p = self.cli("note", "--tried", "--attack", "other-reading", "--check", OK, "--example", EXAMPLE, "x")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(herd.load_notes(self.root, "t1")[0]["example"], EXAMPLE)
        self.assertEqual(herd._attack_states(herd.verify(self.root, "t1")["attacks"])["other-reading"][0], "passing")
        self.assertEqual(self.state("python3 prog.py 'two milk'"), "failing")
        self.assertEqual(self.state("python3 -c \"import sys; print('warn', file=sys.stderr)\""), "passing")

    def test_input_piped_into_the_program_counts(self):
        self.built()
        (self.root / "prog.py").write_text("import sys\nsys.exit(0 if sys.stdin.read().strip() == 'a|b' else 1)\n")
        self.assertEqual(self.state("echo 'a|b' | python3 prog.py"), "passing")
        for cmd in ("echo 'a|b'", "echo a || true", "echo a; exit 0"):
            self.assertEqual(self.state(cmd), "vacuous", cmd)

    def test_a_failing_program_is_not_shown_as_zero_tests(self):
        self.built()
        herd.add_note(self.root, "t1", "tried", "x", attack="other-reading",
                      check="python3 -c \"print('Ran 0 tests')\"", example="python3 prog.py nosuch")
        self.assertEqual(herd._attack_states(herd.verify(self.root, "t1")["attacks"])["other-reading"][0], "failing")

    def test_only_for_other_reading(self):
        self.built()
        p = self.cli("note", "--tried", "--attack", "bad-input", "--check", OK, "--example", EXAMPLE, "x")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("--example", p.stderr)


class TestVacuous(Attacks):
    def test_vacuous_commands_do_not_count(self):
        self.built()
        self.log(refuses="echo no >&2; exit 1", example="true")
        ev, states, probs = self.run_all()
        for a in ("one-bad-part", "other-reading"):
            self.assertEqual(states[a][0], "vacuous", a)
            self.assertIn(f"{a} (its command runs no project code)", probs)

    def test_the_cli_warns(self):
        self.built()
        p = self.cli("note", "--tried", "--attack", "other-reading", "--check", OK, "--example", "test -f prog.py", "x")
        self.assertIn("runs no project code", p.stderr)


class TestRequired(Attacks):
    def test_missing_flags_refuse_done(self):
        self.built()
        self.log(refuses=None, example=None)
        probs = self.run_all()[2]
        self.assertIn("one-bad-part has no --refuses", probs)
        self.assertIn("other-reading has no --example", probs)
        self.assertNotIn("bad-input has no --refuses", probs)

    def test_with_both_flags_done(self):
        self.built()
        self.log()
        self.assertEqual(self.run_all()[2], "")

    def test_na_needs_no_flag(self):
        self.built()
        self.log(na=("one-bad-part", "other-reading"))
        self.assertEqual(self.run_all()[2], "")

    def test_a_later_note_without_the_flag_does_not_keep_it(self):
        self.built()
        self.log()
        herd.add_note(self.root, "t1", "tried", "x", attack="one-bad-part", check=OK)
        self.assertIn("one-bad-part has no --refuses", self.run_all()[2])

    def test_a_note_with_a_flag_logged_after_verify_must_run(self):
        self.built()
        self.log()
        self.run_all()
        n = herd.load_notes(self.root, "t1")
        last = next(x for x in n if x.get("attack") == "one-bad-part")
        herd.add_note(self.root, "t1", "tried", last["text"], attack="one-bad-part", check=OK,
                      refuses="python3 prog.py milk", extra={"at": last["at"]})
        self.assertIn("have not run", " ".join(herd.problems(self.root, "t1")))

    def test_quick_and_low_risk_do_not_need_them(self):
        for ev in ({"route": "standard", "risk": {"effective": "low"}}, {"route": "quick", "risk": {"effective": "medium"}}):
            self.assertFalse(herd.review_needed(ev))
            self.assertEqual(herd.missing_programs(ev), [])


class TestWhenDone(Attacks):
    """The issue's done state: a program that accepts an unknown item, or rejects the human's form, is stopped."""

    def test_both_failures_show_at_red_and_block_done(self):
        self.built()
        (self.root / "prog.py").write_text("import sys\nif 'x' in sys.argv[1]:\n    sys.exit('bad form')\n")
        self.log()
        ev, states, probs = self.run_all()
        self.assertEqual([states[a][0] for a in ("one-bad-part", "other-reading")], ["failing", "failing"])
        self.assertIn("one-bad-part (its command fails)", probs)
        self.assertIn("other-reading (its command fails)", probs)
        self.assertNotEqual(self.cli("done").returncode, 0)


class TestDocs(unittest.TestCase):
    def test_adversarial_md_names_each_flag_in_one_sentence(self):
        text = (Path(herd.__file__).resolve().parent.parent / "skills/run/adversarial.md").read_text()
        for flag in ("--refuses", "--example"):
            self.assertEqual(text.count(flag), 1, flag)


if __name__ == "__main__":
    unittest.main()
