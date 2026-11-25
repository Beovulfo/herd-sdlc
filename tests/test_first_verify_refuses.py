"""The first verify refuses while a standard attack has no note (issue #94)."""
import itertools
import json
import unittest

from scripts import herd
from tests.test_harness_rules import APP_CHECK, OK, TASK, Base

NAMES = ("bad-input", "collision", "one-bad-part", "recount", "refusal", "other-reading")
MESSAGES = dict(herd.FIRST_VERIFY_ATTACKS)
STATE = ("red.json", "frozen.json", "evidence.json", "fails.json")
QUICK = f'''goal = "Add f()"
route = "quick"

[[criteria]]
id = "C1"
text = "f returns 1"
source = "agent-proposed"
check = {json.dumps(APP_CHECK)}
'''
# a check that leaves a trace, to show a refused verify ran nothing
TRACE = '\n[[criteria]]\nid = "C3"\ntext = "trace"\nsource = "agent-proposed"\ncheck = "touch ran.txt"\n'


class Refusal(Base):
    refuses_first = True

    def note(self, name, text="x", **kw):
        if not text.startswith("n/a:"):
            kw.setdefault("check", OK)
        herd.add_note(self.root, "t1", "tried", text, attack=name, **kw)

    def path(self, name):
        return self.root / ".herd/tasks/t1" / name

    def written(self):
        return [f for f in STATE if self.path(f).exists()]

    def refused(self):
        p = self.cli("verify")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        self.assertEqual(self.written(), [])
        return p.stderr


class TestRefuse(Refusal):
    def test_missing_attack_every_subset(self):
        """Also the refusal and recount attacks: what is named is judged by set arithmetic, not by Herd."""
        self.start(TASK + TRACE)
        notes = self.path("notes.jsonl")
        for size in range(1, len(NAMES) + 1):
            for missing in itertools.combinations(NAMES, size):
                with self.subTest(missing=missing):
                    notes.unlink(missing_ok=True)
                    for name in set(NAMES) - set(missing):
                        self.note(name)
                    err = self.refused()
                    self.assertEqual({n for n in NAMES if MESSAGES[n] in err}, set(missing))
                    self.assertEqual(err.count(" attack yet: "), len(missing))
                    self.assertIn(f"{len(missing)} of 6", err)
                    self.assertFalse((self.root / "ran.txt").exists())

    def test_missing_attack_duplicate_notes_count_once(self):
        """collision: many notes for one attack cover only that attack."""
        self.start()
        for _ in range(6):
            self.note("recount")
        err = self.refused()
        self.assertNotIn(MESSAGES["recount"], err)
        self.assertEqual(err.count(" attack yet: "), 5)

    def test_missing_attack_note_without_command_or_na(self):
        """one-bad-part: a hand-edited or old note with no command is not logged, and so is another note kind."""
        self.start()
        for name in NAMES[2:]:
            self.note(name)
        with open(self.path("notes.jsonl"), "a") as f:
            f.write(json.dumps({"at": herd.now(), "kind": "tried", "attack": NAMES[0], "text": "looked"}) + "\n")
            f.write(json.dumps({"at": herd.now(), "kind": "found", "attack": NAMES[1], "text": "n/a: x",
                                "check": OK}) + "\n")
        err = self.refused()
        self.assertEqual({n for n in NAMES if MESSAGES[n] in err}, set(NAMES[:2]))

    def test_bad_input_broken_state_is_one_message(self):
        """bad-input: a broken notes log or task file ends in a message, exit 1, nothing written."""
        self.start()
        for text in ("{not json\n", "\n\n", ""):
            with self.subTest(notes=text):
                self.path("notes.jsonl").write_text(text)
                self.refused()
        self.path("task.toml").write_text("goal = ")
        self.refused()
        self.path("task.toml").unlink()
        self.refused()


class TestRecordsRed(Refusal):
    def red(self):
        red = json.loads(self.path("red.json").read_text())
        return red["failed"], red["total"]

    def test_all_logged_with_commands_na_and_covered_by(self):
        self.start()
        self.note("bad-input", check="false")  # attacks should fail at the first verify
        self.note("collision")
        self.note("one-bad-part", "n/a: cannot apply")
        self.note("recount", check=None, covered_by="C1")
        self.note("refusal", "N/A: nothing is refused")
        self.note("other-reading")
        ev = self.red_then_build()
        self.assertEqual(self.red(), (2, 2))
        self.assertFalse([w for w in ev["warnings"] if " attack " in w])

    def test_all_logged_after_a_refusal(self):
        self.start()
        self.refused()
        self.log_attacks()
        self.red_then_build()
        self.assertEqual(self.red(), (2, 2))

    def test_all_logged_is_still_needed_with_no_runnable_check(self):
        """No red.json yet, so it is still the first verify."""
        self.start(TASK.replace(f"check = {json.dumps(APP_CHECK)}", 'check = ""')
                   .replace('check = "python3 -c \\"import app; app.f\\""', 'check = ""'))
        self.refused()


class TestUnchanged(Refusal):
    def test_quick_route_needs_no_attacks(self):
        self.start(QUICK)
        p = self.cli("verify")
        self.assertIn("1 failing", p.stdout, p.stderr)
        self.assertTrue(self.path("red.json").exists())
        self.assertNotIn("attack", p.stdout + p.stderr)

    def test_already_red_task_is_not_refused(self):
        """A 0.13.x task: red.json exists, attacks missing."""
        self.start()
        self.log_attacks()
        self.red_then_build()
        self.path("notes.jsonl").unlink()
        red = self.path("red.json").read_text()
        p = self.cli("verify")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.path("red.json").read_text(), red)
        self.assertNotIn("refused", p.stderr)


if __name__ == "__main__":
    unittest.main()
