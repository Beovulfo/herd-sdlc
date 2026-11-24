"""The sixth standard attack, other-reading (0.12.9): each input read in every way a person could read it."""
import json
import unittest

from scripts import herd
from tests.test_harness_rules import NO_INPUTS, OK, TASK, Base
from tests.test_herd_cli import late_review

NAME = "other-reading"
ENTRY = '\n[[inputs]]\nhuman = "a date"\nprogram = "03/04/2026 or 2026-04-03"\n'
LATE = "other-reading attack was logged after the first verify"


class TestOtherReading(Base):
    def built(self, text=TASK):
        self.start(text)
        self.red_then_build()

    def log(self, check=OK, text="two readings of each input", others=OK):
        for a in herd.ATTACKS:
            if a != NAME:
                herd.add_note(self.root, "t1", "tried", f"{a} attack", attack=a, check=others)
        if check is None and not text.startswith("n/a:"):  # an old note, or one written straight into the log
            with open(self.root / ".herd/tasks/t1/notes.jsonl", "a") as f:
                f.write(json.dumps({"at": herd.now(), "kind": "tried", "text": text, "attack": NAME}) + "\n")
        else:
            herd.add_note(self.root, "t1", "tried", text, attack=NAME, check=check)

    def refused(self, why, **kw):
        self.built()
        self.log(**kw)
        late_review(self.root)
        herd.verify(self.root, "t1")
        self.assertIn(f"{NAME} ({why})", " ".join(herd.problems(self.root, "t1")))

    def test_it_is_a_standard_attack(self):
        self.assertIn(NAME, herd.ATTACKS)
        self.assertEqual(len(herd.ATTACKS), 6)

    def test_missing_refuses_done(self):
        self.built()
        for a in herd.ATTACKS:
            if a != NAME:
                herd.add_note(self.root, "t1", "tried", f"{a} attack", attack=a, check=OK)
        late_review(self.root)
        herd.verify(self.root, "t1")
        self.assertIn(f"{NAME} (no passing command)", " ".join(herd.problems(self.root, "t1")))

    def test_failing_refuses_done(self):
        self.refused("its command fails", check="false")

    def test_zero_tests_refuses_done(self):
        self.refused("its command ran zero tests", check="python3 -c \"print('Ran 0 tests')\"")

    def test_vacuous_refuses_done(self):
        self.refused("its command runs no project code", check="true")

    def test_no_command_refuses_done(self):
        self.refused("logged without a command", check=None)

    def test_passing_counts(self):
        self.built()
        self.log()
        late_review(self.root)
        herd.verify(self.root, "t1")
        self.assertNotIn(NAME, " ".join(herd.problems(self.root, "t1")))

    def test_na_is_refused_when_the_task_has_an_input(self):
        self.built(TASK.replace("inputs = []\n", "") + ENTRY)
        self.log(check=None, text="n/a: nothing to read twice")
        late_review(self.root)
        herd.verify(self.root, "t1")
        self.assertIn(f"{NAME} marked n/a, but the task lists inputs", " ".join(herd.problems(self.root, "t1")))

    def test_na_is_accepted_with_no_inputs(self):
        self.built()
        self.log(check=None, text="n/a: the task has no inputs")
        late_review(self.root)
        herd.verify(self.root, "t1")
        self.assertNotIn(NAME, " ".join(herd.problems(self.root, "t1")))

    def test_the_first_verify_asks_for_both_attacks(self):
        self.start(NO_INPUTS)
        w = self.red_then_build()["warnings"]
        self.assertIn(herd.REFUSAL_FIRST, w)
        self.assertIn(herd.OTHER_READING_FIRST, w)

    def test_logged_before_the_first_verify_is_not_late_or_asked_for(self):
        self.start()
        herd.add_note(self.root, "t1", "tried", "readings", attack=NAME, check=OK)
        self.assertNotIn(herd.OTHER_READING_FIRST, self.red_then_build()["warnings"])
        self.assertFalse([x for x in herd.verify(self.root, "t1")["warnings"] if x.startswith(LATE)])

    def test_logged_after_the_first_verify_is_warned_about(self):
        self.start()
        self.red_then_build()
        herd.add_note(self.root, "t1", "tried", "readings", attack=NAME, check=OK)
        w = herd.verify(self.root, "t1")["warnings"]
        self.assertTrue([x for x in w if x.startswith(LATE)], w)

    def test_the_quick_route_is_exempt(self):
        herd.init_task(self.root, "q1", "Fix typo", quick_check=OK)
        (self.root / "app.py").write_text("x = 1\n")
        herd.verify(self.root, "q1")
        self.assertNotIn(NAME, " ".join(herd.problems(self.root, "q1")))


if __name__ == "__main__":
    unittest.main()
