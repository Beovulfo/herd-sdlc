"""The standard attacks on `--refuses` and `--example` (issue #66): generated commands, judged by separate code."""
import json
import random
import shlex
import subprocess
import unittest

from scripts import herd
from tests.test_harness_rules import OK, Base

# what each generated program does, written as data: (exit code, stdout, stderr)
CODES = (0, 1, 2, 7, 64, 125, 126, 127, 130, 255)
OUTS = ("", "ok\n", "Traceback (most recent call last):\n", "   \n", "é\n")
ERRS = ("", "unknown item\n", "Traceback (most recent call last):\n  x\n", "  \n\n", "é: not found\n")
PROG = '''import json, sys
code, out, err = json.loads(sys.argv[1])
sys.stdout.write(out); sys.stderr.write(err); sys.exit(code)
'''


def cmd(behaviour):
    return "python3 prog.py " + shlex.quote(json.dumps(behaviour))


def should_refuse(code, out, err):
    """The rule in the issue, plus Herd's own: 126, 127 and above mean the shell could not run it or it crashed."""
    return code in range(1, 126) and err.split() != [] and "Traceback" not in out and "Traceback" not in err


class Gen(Base):
    def setUp(self):
        super().setUp()
        self.start()
        self.red_then_build()
        (self.root / "prog.py").write_text(PROG)

    def note(self, attack, **kw):
        herd.add_note(self.root, "t1", "tried", f"{attack} generated", attack=attack, check=OK, **kw)

    def verified(self):
        return herd.verify(self.root, "t1")["attacks"]


class TestRefusal(Gen):
    """Everything Herd refuses to count is confirmed by separate code, on random behaviours."""

    def test_generated_behaviours(self):
        rng = random.Random(66)
        cases = [(c, rng.choice(OUTS), rng.choice(ERRS)) for c in CODES]
        cases += [(rng.choice(CODES), rng.choice(OUTS), rng.choice(ERRS)) for _ in range(30)]
        for c in cases:
            self.note("bad-input", refuses=cmd(c))
            self.note("other-reading", example=cmd(c))
        ran = self.verified()
        got = [a["status"] == "passing" for a in ran]
        want = [w for c in cases for w in (should_refuse(*c), c[0] == 0)]
        self.assertEqual(got, want)
        self.assertTrue(any(want[0::2]) and not all(want[0::2]))

    def test_a_flag_is_refused_exactly_where_it_does_not_belong(self):
        allowed = {("refuses", "bad-input"), ("refuses", "one-bad-part"), ("example", "other-reading")}
        for flag in ("refuses", "example"):
            for attack in herd.ATTACKS:
                try:
                    self.note(attack, **{flag: cmd((1, "", "no"))})
                    ok = True
                except ValueError:
                    ok = False
                self.assertEqual(ok, (flag, attack) in allowed, (flag, attack))


class TestOtherReading(Gen):
    """The builder may write the command in several shell forms: Herd runs each as written."""

    def test_shell_forms(self):
        (self.root / "items.txt").write_text("milk\n")
        refuse = cmd((1, "", "no"))
        forms = [refuse, f"{refuse} 2>&1 1>/dev/null >&2", f"cd . && {refuse}", f"X=1 {refuse}",
                 f"echo milk | {refuse}", f"{refuse} < items.txt", f"({refuse})", f"{refuse}\n"]
        for f in forms[:1] + forms[2:]:
            self.note("one-bad-part", refuses=f)
        self.assertEqual([a["status"] for a in self.verified()], ["passing"] * (len(forms) - 1))
        ok = cmd((0, "", ""))
        for f in (ok, f"cat items.txt | {ok}", f"{ok} && {ok}", f"{ok} -- --refuses"):
            self.note("other-reading", example=f)
        self.assertEqual([a["status"] for a in self.verified()][-4:], ["passing"] * 4)

    def test_both_flag_orders_on_the_cli(self):
        for args in (["--refuses", cmd((1, "", "no")), "--attack", "bad-input", "--check", OK],
                     ["--check", OK, "--attack", "bad-input", "--refuses", cmd((1, "", "no"))]):
            p = self.cli("note", "--tried", *args, "text")
            self.assertEqual(p.returncode, 0, p.stderr)


class TestBadInput(Gen):
    def test_every_bad_flag_ends_in_one_message(self):
        base = ["note", "--tried", "--attack", "bad-input", "--check", OK]
        bad = [base + ["x", "--refuses"], base + ["--refuses", "", "x"], base + ["--example", "c", "x"],
               ["note", "--tried", "--refuses", "c", "x"], ["note", "--open", "--refuses", "c", "x"],
               ["note", "--tried", "--attack", "bad-input", "--refuses", "c", "n/a: x"],
               base + ["--refuses", "c", "--refuses", "d", "x"]]
        for args in bad:
            p = self.cli(*args)
            self.assertNotEqual(p.returncode, 0, args)
            self.assertNotIn("Traceback", p.stderr, args)
            self.assertTrue(p.stderr.strip(), args)
        self.assertEqual(herd.load_notes(self.root, "t1"), [])

    def test_unrunnable_or_binary_commands_never_crash_verify(self):
        for c in ("/dev/null", "no-such-cmd-66", "python3 -c \"import sys; sys.stderr.buffer.write(b'\\xff'); sys.exit(1)\"",
                  "echo '"):
            self.note("bad-input", refuses=c)
        self.assertEqual([a["status"] for a in self.verified()], ["failing", "failing", "passing", "failing"])


class TestCollision(Gen):
    def test_same_check_different_programs_each_count(self):
        good, bad = cmd((1, "", "no")), cmd((0, "", ""))
        for c in (good, bad, good):
            self.note("bad-input", refuses=c)
        self.note("one-bad-part", refuses=bad)
        self.note("other-reading", example=bad)  # the same command, judged by the other rule
        self.assertEqual([a["status"] for a in self.verified()],
                         ["passing", "failing", "passing", "failing", "passing"])


class TestOneBadPart(Gen):
    def test_a_broken_note_does_not_stop_the_others(self):
        self.note("bad-input", refuses="no-such-cmd-66")
        self.note("one-bad-part", refuses=cmd((1, "", "no")))
        self.assertEqual([a["status"] for a in self.verified()], ["failing", "passing"])


class TestRecount(Gen):
    def test_verify_counts_match_a_direct_run(self):
        cmds = [cmd((c, "", "no")) for c in (0, 1, 2)]
        for c in cmds:
            self.note("bad-input", refuses=c)
        direct = [subprocess.run(c, shell=True, cwd=self.root, capture_output=True).returncode for c in cmds]
        self.assertEqual([a["status"] == "passing" for a in self.verified()], [d != 0 for d in direct])


if __name__ == "__main__":
    unittest.main()
