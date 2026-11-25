"""The sixth standard attack, other-reading (0.12.9): each input read in every way a person could read it."""
import json
import unittest

from scripts import herd
from tests.test_harness_rules import NO_INPUTS, OK, REQUEST, TASK, Base
from tests.test_herd_cli import PROGRAMS

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
                herd.add_note(self.root, "t1", "tried", f"{a} attack", attack=a, check=others, **PROGRAMS.get(a, {}))
        if check is None and not text.startswith("n/a:"):  # an old note, or one written straight into the log
            with open(self.root / ".herd/tasks/t1/notes.jsonl", "a") as f:
                f.write(json.dumps({"at": herd.now(), "kind": "tried", "text": text, "attack": NAME}) + "\n")
        else:
            herd.add_note(self.root, "t1", "tried", text, attack=NAME, check=check, **(PROGRAMS[NAME] if check else {}))

    def refused(self, why, **kw):
        self.built()
        self.log(**kw)
        herd.verify(self.root, "t1")
        self.assertIn(f"{NAME} ({why})", " ".join(herd.problems(self.root, "t1")))

    def test_it_is_a_standard_attack(self):
        self.assertIn(NAME, herd.ATTACKS)
        self.assertEqual(len(herd.ATTACKS), 6)

    def test_missing_refuses_done(self):
        self.built()
        for a in herd.ATTACKS:
            if a != NAME:
                herd.add_note(self.root, "t1", "tried", f"{a} attack", attack=a, check=OK, **PROGRAMS.get(a, {}))
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
        herd.verify(self.root, "t1")
        self.assertNotIn(NAME, " ".join(herd.problems(self.root, "t1")))

    def test_na_is_refused_when_the_task_has_an_input(self):
        self.built(TASK.replace("inputs = []\n", "") + ENTRY)
        self.log(check=None, text="n/a: nothing to read twice")
        herd.verify(self.root, "t1")
        self.assertIn(f"{NAME} marked n/a, but the task lists inputs", " ".join(herd.problems(self.root, "t1")))

    def test_na_is_accepted_with_no_inputs(self):
        self.built()
        self.log(check=None, text="n/a: the task has no inputs")
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


def entry(readings):
    return '\n[[inputs]]\nhuman = "a date"\nprogram = "03/04/2026"\n' + (f"readings = {readings}\n" if readings is not None else "")


class TestReadings(Base):
    """Each `[[inputs]]` entry lists at least 2 readings (0.12.9); only the number of items is counted."""

    def left(self, readings, text=TASK, risk=None):
        self.start(text.replace("inputs = []\n", "") + entry(readings))
        if risk:  # `herd init` stores the risk it triaged
            f = self.root / ".herd/tasks/t1/start.json"
            f.write_text(json.dumps({**json.loads(f.read_text()), "risk": risk}))
        return [w for w in self.red_then_build()["warnings"] if w.startswith("inputs #1")]

    def refused(self):
        herd.verify(self.root, "t1")
        return " ".join(herd.problems(self.root, "t1"))

    def test_none_one_or_an_empty_list_is_questioned(self):
        for r in (None, "[]", '["any call"]'):
            self.assertTrue(self.left(r), r)
            self.tearDown()
            self.setUp()

    def test_two_readings_are_not_questioned(self):
        self.assertEqual(self.left('["any call", "month first"]'), [])

    def test_the_wording_is_never_read(self):
        self.assertEqual(self.left('["any call", ""]'), [])

    def test_a_string_is_not_a_list_of_readings(self):
        self.assertTrue(self.left('"day first, month first"'))

    def test_one_reading_refuses_done_at_medium_risk(self):
        self.left('["any call"]')
        self.assertIn("inputs #1: `readings`", self.refused())

    def test_two_readings_do_not_refuse_done(self):
        self.left('["any call", "month first"]')
        self.assertNotIn("inputs #1", self.refused())

    def test_low_risk_only_warns(self):
        self.left('["any call"]', risk="low")
        self.assertNotIn("inputs #1", self.refused())

    def test_the_quick_route_is_exempt(self):
        herd.init_task(self.root, "q1", "Fix typo", quick_check=OK)
        self.assertEqual([w for w in herd.verify(self.root, "q1")["warnings"] if w.startswith("inputs #")], [])

    def test_the_readings_are_shown_next_to_the_input(self):
        self.left('["any call", "month first"]')
        self.assertIn("a date -> 03/04/2026 (readings: any call; month first)", herd.report(herd.verify(self.root, "t1")))


QUOTE = "inputs #{}: `readings[0]` is not a verbatim quote"
WORDS = REQUEST.split()


def entries(*firsts):
    """task.toml with one input per value, as its first reading (JSON strings are TOML strings)."""
    return TASK.replace("inputs = []\n", "") + "".join(entry(json.dumps([f, "another reading"])) for f in firsts)


class TestReadingQuotes(Base):
    """The first reading of each input quotes the request (0.12.13), by the human criteria's quote rule."""

    def checked(self, text, risk="medium", request=REQUEST):
        herd.init_task(self.root, "t1", "Add f() to app.py", request=request)
        (self.root / ".herd/tasks/t1/task.toml").write_text(text)
        f = self.root / ".herd/tasks/t1/start.json"
        f.write_text(json.dumps({**json.loads(f.read_text()), "risk": risk}))
        return self.cli("check", "t1")

    def refusals(self, p):
        return [ln for ln in p.stderr.splitlines() if "`readings[0]`" in ln]

    def again(self):
        self.tearDown()
        self.setUp()

    def test_check_refuses_at_medium_and_high_risk(self):
        for risk in ("medium", "high"):
            p = self.checked(entries("a date typed by hand"), risk)
            self.assertEqual(p.returncode, 1, risk)
            self.assertIn(QUOTE.format(1), p.stderr)
            self.assertNotIn("ok", p.stdout.split())
            self.assertNotIn("Traceback", p.stderr)
            self.again()

    def test_a_quote_passes_whatever_its_spacing_case_or_marks(self):
        for first in ("return 1 for any call", "RETURN  1\nfor   any call.", "`f()` to app.py", '"any call"'):
            p = self.checked(entries(first))
            self.assertEqual((p.returncode, self.refusals(p)), (0, []), first)
            self.again()

    def test_part_of_a_word_or_number_is_not_a_quote(self):
        for first in ("", "ny call", "return 10", "any call at all"):
            self.assertEqual(self.checked(entries(first)).returncode, 1, repr(first))
            self.again()

    def test_no_first_reading_is_refused(self):
        for r in (None, "[]", '"any call"'):
            p = self.checked(TASK.replace("inputs = []\n", "") + entry(r))
            self.assertEqual((p.returncode, len(self.refusals(p))), (1, 1), r)
            self.again()

    def test_the_next_step_is_to_quote(self):
        why = herd.reading_quote_warnings({"inputs": [{}]}, REQUEST)[0]
        step = next(s for pat, s in herd.NEXT_STEPS if pat.search(why))
        self.assertIn("quote of the request", step)

    def test_done_refuses_too(self):
        self.start(entries("typed by hand"))
        self.red_then_build()
        herd.verify(self.root, "t1")
        self.assertIn(QUOTE.format(1), " ".join(herd.problems(self.root, "t1")))

    def test_changed_files_that_raise_the_risk_refuse(self):
        (self.root / "herd.toml").write_text('[floor]\nmedium = ["api/**"]\n')
        (self.root / "api").mkdir()
        self.assertEqual(self.checked(entries("typed by hand"), "low").returncode, 0)
        (self.root / "api/x.py").write_text("x = 1\n")
        self.assertEqual(self.cli("check", "t1").returncode, 1)

    def test_low_risk_exempt(self):
        p = self.checked(entries("typed by hand"), "low")
        self.assertEqual((p.returncode, self.refusals(p)), (0, []))
        self.assertIn("warning: " + QUOTE.format(1), p.stdout)
        self.red_then_build()
        herd.verify(self.root, "t1")
        self.assertNotIn("readings[0]", " ".join(herd.problems(self.root, "t1")))
        self.assertEqual(herd.reading_quote_warnings({"route": "quick", "inputs": [{"readings": ["no"]}]}, REQUEST), [])

    def test_no_recorded_request_leaves_nothing_to_quote(self):
        self.assertEqual(self.checked(entries("typed by hand"), request=None).returncode, 0)

    def test_bad_input_never_ends_in_a_traceback(self):
        base = TASK.replace("inputs = []\n", "")
        for text in (TASK.replace("inputs = []", 'inputs = "a date"'), TASK.replace("inputs = []", "inputs = [1, []]"),
                     base + entry(None), base + entry("[]"), base + entry('"any call"'), base + entry("[7, 8]"),
                     base + entry('[{a = 1}, "x"]'), "inputs = [", ""):
            p = self.checked(text)
            self.assertIn(p.returncode, (0, 1, 2), text)
            self.assertNotIn("Traceback", p.stderr, text)
            self.again()

    def test_collision_equal_entries_are_each_named(self):
        p = self.checked(entries("typed by hand", "typed by hand"))
        self.assertEqual(len(self.refusals(p)), 2)
        self.assertIn(QUOTE.format(2), p.stderr)

    def test_one_bad_part_only_the_unquoted_first_reading_is_named(self):
        p = self.checked(entries("any call", "typed by hand", "app.py"))  # every second reading is unquoted
        self.assertEqual([r.split(":")[1].strip() for r in self.refusals(p)], ["inputs #2"])

    def test_recount_and_refusal_on_generated_readings(self):
        """Every run of whole words of the request passes; the same run with a foreign word is refused."""
        runs = [" ".join(WORDS[i:j]) for i in range(len(WORDS)) for j in range(i + 1, len(WORDS) + 1)]
        good = herd.reading_quote_warnings({"inputs": [{"readings": [r]} for r in runs]}, REQUEST)
        self.assertEqual(good, [])
        mixed = [r if n % 3 else r + " zebra" for n, r in enumerate(runs)]
        bad = herd.reading_quote_warnings({"inputs": [{"readings": [r]} for r in mixed]}, REQUEST)
        self.assertEqual([int(w.split("#")[1].split(":")[0]) for w in bad],
                         [n + 1 for n, r in enumerate(mixed) if "zebra" in r.split()])

    def test_other_reading_of_the_task_and_request(self):
        """Inline tables, [[inputs]] tables and a Markdown, wrapped or CRLF request are all read."""
        inline = TASK.replace("inputs = []", 'inputs = [{human = "d", program = "d", readings = ["any call", "x"]}]')
        for request in (REQUEST, "- Add f() to\r\n  app.py.\r\n> It must return **1** for\r\n> any call."):
            for text in (inline, entries("It must return 1 for any call")):
                p = self.checked(text, request=request)
                self.assertEqual((p.returncode, self.refusals(p)), (0, []), (request, text))
                self.again()


if __name__ == "__main__":
    unittest.main()
