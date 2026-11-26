"""`herd verify` records and shows how long each check takes (issue #127)."""
import contextlib
import io
import json
import os
import random
import unittest
from unittest import mock

from scripts import herd
from tests.test_harness_rules import Base
from tests.test_herd_cli import run_herd

HEAD = 'goal = "Time checks"\ntest_budget = "short sleeps"\nknown_limits = "none shown"\ninputs = []\n'


def crit(cid, check, extra=""):
    return f'\n[[criteria]]\nid = "{cid}"\ntext = "t"\nsource = "agent-proposed"\ncheck = \'{check}\'\n{extra}'


class Case(Base):
    def task(self, *criteria):
        self.start(HEAD + "".join(criteria))

    def ev(self):
        return json.loads((self.root / ".herd/tasks/t1/evidence.json").read_text())

    def verify(self):
        p = run_herd(self.root, "verify", "--fresh")
        self.assertNotIn("Traceback", p.stderr)
        return p

    def cli(self, slow_s):
        """`herd verify` in this process, with the slow line at slow_s."""
        out = io.StringIO()
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            with mock.patch.object(herd, "SLOW_S", slow_s), contextlib.redirect_stdout(out):
                rc = herd.main(["verify", "--fresh"])
        finally:
            os.chdir(cwd)
        return rc, out.getvalue().splitlines()


class TestRecorded(Case):
    def test_each_checked_result_has_seconds(self):
        self.task(crit("C1", "sleep 1"), crit("C2", "sleep 1"), crit("C3", "exit 3"),
                  crit("C4", "sleep 5", "timeout_s = 1\n"), crit("C5", ""))
        self.verify()
        r = {r["id"]: r for r in self.ev()["results"]}
        for cid in ("C1", "C2", "C4"):  # identical commands each get their own time; a timeout has one too
            self.assertGreaterEqual(r[cid]["seconds"], 1, cid)
        self.assertLess(r["C3"]["seconds"], 1)
        self.assertNotIn("seconds", r["C5"])

    def test_total_covers_the_results_and_is_printed(self):
        self.task(crit("C1", "sleep 1"), crit("C2", "sleep 0.5"))
        p = self.verify()
        ev = self.ev()
        self.assertGreaterEqual(ev["seconds"] + 0.1, sum(r["seconds"] for r in ev["results"]))
        self.assertIn(f"2 passing, 0 failing, 0 unchecked (checks took {ev['seconds']:.1f} s)", p.stdout)
        self.assertNotIn("every verify reruns it", p.stdout)

    def test_report_and_evidence_md_show_the_time(self):
        self.task(crit("C1", "true"), crit("C2", ""))
        self.verify()
        r = self.ev()["results"][0]
        row = f"| C1 | passing ({r['seconds']:.1f} s) |"
        self.assertIn(row, run_herd(self.root, "status").stdout)
        self.assertIn("| C2 | unchecked |", run_herd(self.root, "status").stdout)
        self.assertIn(row, herd.report(self.ev()))

    def test_old_or_hand_edited_times_show_nothing(self):
        self.task(crit("C1", "true"))
        self.verify()
        path = self.root / ".herd/tasks/t1/evidence.json"
        for bad in ("missing", None, "12", True, [1]):
            ev = self.ev()
            ev["results"][0]["seconds"] = bad
            if bad == "missing":
                del ev["results"][0]["seconds"], ev["seconds"]
            path.write_text(json.dumps(ev))
            p = run_herd(self.root, "status")
            self.assertEqual((p.returncode, p.stderr), (0, ""), bad)
            self.assertIn("| C1 | passing |", p.stdout, bad)


class TestSlow(Case):
    def test_slow_lines_match_the_times_on_generated_runs(self):
        rng = random.Random(127)
        for _ in range(200):
            def times():
                return rng.choice([0.0, 59.9, 60.0, 60.1, 61.0, 412.0, rng.uniform(0, 3000)])
            ev = {"results": [{"id": f"C{i}", "seconds": times()} for i in range(rng.randint(1, 40))]
                  + [{"id": "C0"}],
                  "attacks": [{"attack": a, "seconds": times()} for a in rng.sample(sorted(herd.ATTACKS), 3)]
                  + [{"attack": "recount"}]}
            named = [(r["id"], r["seconds"]) for r in ev["results"] if "seconds" in r]
            named += [(f"attack {a['attack']}", a["seconds"]) for a in ev["attacks"] if "seconds" in a]
            self.assertEqual(herd.slow_lines(ev),
                             [f"{n} took {s:.0f} s: every verify reruns it" for n, s in named if s > 60])

    def test_a_slow_check_is_named_and_still_passes(self):
        self.task(crit("C1", "true"), crit("C2", "sleep 1"))
        rc, out = self.cli(slow_s=0.5)
        self.assertEqual(rc, 0, out)
        self.assertEqual([line.strip() for line in out if "reruns" in line], ["C2 took 1 s: every verify reruns it"])
        self.assertEqual([r["status"] for r in self.ev()["results"]], ["passing", "passing"])

    def test_the_line_is_60_s(self):
        self.assertEqual(herd.SLOW_S, 60)

    def test_a_shared_attack_command_is_timed_once(self):
        self.task(crit("C1", "true"))
        for name in ("bad-input", "collision"):
            p = run_herd(self.root, "note", "--tried", "--attack", name, "--check", "sleep 1", "x")
            self.assertEqual(p.returncode, 0, p.stderr)
        self.verify()
        timed = [a["seconds"] for a in self.ev()["attacks"] if "seconds" in a]
        self.assertEqual(len(timed), 1)
        self.assertGreaterEqual(timed[0], 1)

    def test_a_skipped_verify_prints_no_time(self):
        self.task(crit("C1", "true"))
        self.verify()
        p = run_herd(self.root, "verify")
        self.assertIn("unchanged since", p.stdout)
        self.assertNotIn("checks took", p.stdout)


class TestRefused(Case):
    """Input verify already refused is still refused: one message, no time, nothing written."""

    def test_duplicate_id_and_broken_entry(self):
        self.task()
        for bad in (crit("C1", "true") + crit("C1", "false"), '\n[[criteria]]\nid = "C1"\n'):
            (self.root / ".herd/tasks/t1/task.toml").write_text(HEAD + bad)
            p = self.verify()
            self.assertEqual(p.returncode, 1)
            self.assertTrue(p.stderr.strip())
            self.assertNotIn("checks took", p.stdout)
            self.assertFalse((self.root / ".herd/tasks/t1/evidence.json").exists())


if __name__ == "__main__":
    unittest.main()
