"""Attacks shape the design, and input that cannot be trusted is refused (0.12.14, issue #83)."""
import random
import unittest

from scripts import herd
from tests.test_attack_commands import REFUSES, Attacks
from tests.test_harness_rules import OK

NAMES = ("bad-input", "collision", "one-bad-part", "recount", "refusal", "other-reading")
NA_REFUSES = "n/a: the request says the last entry wins"


def late(warnings):
    return {w.split()[0] for w in warnings if "attack was logged after the first verify" in w}


def asked(warnings):
    return {w.split()[1] for w in warnings if w.startswith("no ") and " attack yet" in w}


class TestFirstVerify(Attacks):
    def note(self, name):
        herd.add_note(self.root, "t1", "tried", f"{name} attack", attack=name, check=OK)

    def test_generated_subsets_are_asked_for_and_late(self):
        """refusal: which attacks are asked for or late, judged by set arithmetic, not by Herd."""
        rng = random.Random(83)
        early = set(rng.sample(NAMES, rng.randint(1, 5)))
        self.start()
        for n in early:
            self.note(n)
        w = self.red_then_build()["warnings"]
        self.assertEqual(asked(w), set(NAMES) - early)
        self.assertEqual(late(w), set())
        for n in NAMES:
            self.note(n)  # a second note for an early attack does not make it late
        w = herd.verify(self.root, "t1")["warnings"]
        self.assertEqual((asked(w), late(w)), (set(), set(NAMES) - early))

    def test_na_counts_as_logged(self):
        self.start()
        for n in NAMES:
            herd.add_note(self.root, "t1", "tried", "n/a: cannot apply", attack=n)
        w = self.red_then_build()["warnings"]
        self.assertEqual((asked(w), late(w)), (set(), set()))


class TestCollisionRefuses(Attacks):
    def go(self, refuses):
        self.built()
        self.log()
        herd.add_note(self.root, "t1", "tried", "contradiction", attack="collision", check=OK, refuses=refuses)
        return self.run_all()

    def test_required_at_medium_risk(self):
        ev, _, probs = self.go(None)
        self.assertIn("collision has no --refuses", probs)

    def test_a_real_refusal_passes(self):
        ev, states, probs = self.go(REFUSES)
        self.assertEqual(states["collision"][0], "passing")
        self.assertNotIn("collision has no", probs)

    def test_a_warning_with_exit_0_is_not_a_refusal(self):
        _, states, _ = self.go("python3 -c \"import sys; print('warning: repeated id', file=sys.stderr)\"")
        self.assertEqual(states["collision"][0], "failing")

    def test_a_stated_na_is_not_run_and_is_shown(self):
        """The request says which entry wins: nothing to refuse, and the report says it was not run."""
        ev, states, probs = self.go(NA_REFUSES)
        self.assertEqual(states["collision"][0], "passing")
        self.assertNotIn("collision has no", probs)
        want = f"collision refusal not run: {NA_REFUSES}"
        notes = herd.load_notes(self.root, "t1")
        self.assertIn(want, "\n".join(herd.final_report(self.root, "t1", ev, notes)))
        self.assertIn(f"- {want}", herd.pr_body(self.root, "t1"))

    def test_na_is_only_for_collision(self):
        self.built()
        herd.add_note(self.root, "t1", "tried", "x", attack="one-bad-part", check=OK, refuses=NA_REFUSES)
        states = herd._attack_states(herd.verify(self.root, "t1")["attacks"])
        self.assertEqual(states["one-bad-part"][0], "failing")

    def test_na_needs_a_reason(self):
        self.built()
        with self.assertRaises(ValueError):
            herd.add_note(self.root, "t1", "tried", "x", attack="collision", check=OK, refuses="n/a:  ")

    def test_the_cli_gives_no_vacuous_warning_for_na(self):
        self.built()
        p = self.cli("note", "--tried", "--attack", "collision", "--check", OK, "--refuses", NA_REFUSES, "x")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("runs no project code", p.stdout + p.stderr)

    def test_generated_flag_places(self):
        """bad-input: each flag on each attack, accepted exactly where this table says."""
        self.built()
        allowed = {"refuses": {"bad-input", "collision", "one-bad-part"}, "example": {"other-reading"}}
        for flag, places in allowed.items():
            for name in NAMES:
                p = self.cli("note", "--tried", "--attack", name, "--check", OK, f"--{flag}", REFUSES, "x")
                self.assertEqual(p.returncode == 0, name in places, (flag, name, p.stderr))
                self.assertNotIn("Traceback", p.stderr)


class TestRuleText(unittest.TestCase):
    def setUp(self):
        from tests.test_herd_cli import SKILLS
        self.adv = (SKILLS / "run/adversarial.md").read_text()
        self.skill = (SKILLS / "run/SKILL.md").read_text()

    def rule(self, name):
        return self.adv.split(f"--attack {name}`:", 1)[1].split("\n", 1)[0]

    def test_collision_has_both_cases(self):
        r = self.rule("collision")
        for part in ("share a name, value or position", "contradicts itself", "must be refused",
                     "unless the request says which one wins", "identity fields"):
            self.assertIn(part, r)

    def test_one_bad_part_skips_only_when_harmless(self):
        r = self.rule("one-bad-part")
        for part in ("cannot change a requested answer", "any output the request asks for",
                     "A warning on stderr with exit 0 is never a refusal"):
            self.assertIn(part, r)
        self.assertNotIn("must not reject the whole input", r)

    def test_the_red_step_sends_to_the_attacks(self):
        plan, red = self.skill.split("3. **Break it**", 1)[1].split("\n4. **Red.**", 1)
        self.assertIn("[adversarial.md](adversarial.md)", plan)
        self.assertIn("all six", plan)
        self.assertIn("`herd verify` before writing code", red.split("\n5. ", 1)[0])


if __name__ == "__main__":
    unittest.main()
