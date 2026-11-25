"""The ROI row, recomputed here from the raw files with separate code."""
import contextlib
import io
import itertools
import json
import math
import os
import random
import tempfile
import unittest
from pathlib import Path

import armfile
import judge
import report

CASE = "supermarket-route"
ARMS = list(armfile.load_arms())


def brute_p(a, b, c, d):
    """Fisher two-sided by listing every way to choose which runs are in the first arm."""
    marks = [1] * (a + c) + [0] * (b + d)
    sums = [sum(x) for x in itertools.combinations(marks, a + b)]
    seen = {k: sums.count(k) for k in set(sums)}
    return sum(n for n in seen.values() if n <= seen[a]) / len(sums)


def raw(results, arm):
    """(before, after, run.json, name) of every ok run, read straight from the files."""
    found = []
    for run in (results / CASE / arm).glob("run-*"):
        record = json.loads((run / "run.json").read_text())
        if record["status"] == "ok":
            labels = [json.loads((run / w / "label.json").read_text())["label"] for w in ("before", "after")]
            found.append((*labels, record, run.name))
    return found


def avg(found, key, parts=("first", "challenger", "resume")):
    return sum(r[2][key][p] for r in found for p in parts) / len(found)


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()

    def put(self, results, arm, n, before, after, status="ok", cost=None, seconds=None):
        run = results / CASE / arm / f"run-{n}"
        for when, label in (("before", before), ("after", after)):
            (run / when).mkdir(parents=True)
            (run / when / "label.json").write_text(json.dumps({"label": label}))
        record = {"status": status}
        for key, parts in (("cost", cost), ("seconds", seconds)):
            if parts:
                record[key] = dict(zip(("first", "challenger", "resume"), parts))
        (run / "run.json").write_text(json.dumps(record))

    def report(self, results, *argv, **kw):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = report.main([*([str(results)] if results else []), "--case", CASE, *argv], **kw)
        return code, out.getvalue()

    def rows(self, text):
        table = [[c.strip() for c in line.strip("|").split("|")] for line in text.splitlines() if line.startswith("|")]
        return {r[0]: dict(zip(table[0], r)) for r in table[2:]}


class TestRoi(Base):
    def test_roi_row_by_hand(self):
        results = self.tmp / "r"
        for n, after in enumerate(["shelf", "cell", "cell", "unstated"], 1):
            self.put(results, "control", n, "shelf" if n < 3 else "unstated", after,
                     cost=(0.10, 0, 0.02), seconds=(100, 0, 20))
        for n, after in enumerate(["shelf", "shelf", "shelf", "fixed-side"], 1):
            self.put(results, "generic-after-red", n, "shelf" if n == 4 else "cell", after,
                     cost=(0.10, 0.05, 0.03), seconds=(100, 30, 50))
        self.put(results, "generic-after-red", 5, "cell", "shelf", status="leak")
        code, out = self.report(results)
        self.assertEqual(code, 0, out)
        got = self.rows(out)["generic-after-red"]
        want = {"runs": "4", "right before": "1", "right after": "3", "gain": "+2",
                "right-to-wrong flips": "1 (run-4)", "challenger $/run": "0.0500", "extra $/run": "+0.0600",
                "extra min/run": "+1.0", "$ per extra right design": "0.1200", "excluded": "leak 1",
                "transitions": "cell→shelf 3; shelf→fixed-side 1", "Fisher p": "0.486"}
        self.assertEqual({k: got[k] for k in want}, want)
        control = self.rows(out)["control"]
        self.assertEqual((control["gain"], control["$ per extra right design"], control["Fisher p"]),
                         ("+0", "n/a", "1.000"))
        for word in ("met", "keep", "cut", "Bar"):
            self.assertNotRegex(out, rf"\b{word}\b")

    def test_roi_without_control_or_cost_says_n_a(self):
        results = self.tmp / "r"
        self.put(results, "generic-after-red", 1, "cell", "shelf")
        got = self.rows(self.report(results)[1])["generic-after-red"]
        for key in ("gain", "challenger $/run", "extra $/run", "extra min/run", "$ per extra right design", "Fisher p"):
            self.assertEqual(got[key], "n/a", key)
        self.put(results, "control", 1, "cell", "cell", cost=(None, 0, 0.1), seconds=(1, 0, 1))
        got = self.rows(self.report(results)[1])["generic-after-red"]
        self.assertEqual((got["gain"], got["extra $/run"]), ("+1", "n/a"))

    def test_roi_bad_cost_refuses(self):
        for bad in ("x", -1, True, float("nan")):
            results = Path(tempfile.mkdtemp(dir=self.tmp))
            self.put(results, "control", 1, "cell", "cell", cost=(bad, 0, 1))
            code, out = self.report(results)
            self.assertEqual(code, 2, (bad, out))
            self.assertNotIn("Traceback", out)

    def test_roi_fisher_matches_brute_force(self):
        for a, b, c, d in itertools.product(range(5), repeat=4):
            if a + b and c + d:
                self.assertAlmostEqual(report.fisher(a, b, c, d), brute_p(a, b, c, d), places=9, msg=(a, b, c, d))
        self.assertAlmostEqual(report.fisher(6, 0, 3, 3), 2 * math.comb(9, 6) / math.comb(12, 6), places=9)

    def test_roi_recount_on_random_results(self):
        labels = [x["id"] for x in judge.load_cases()[CASE]["labels"]]
        for seed in range(30):
            rng, results = random.Random(seed), Path(tempfile.mkdtemp(dir=self.tmp))
            for arm in ARMS:
                for n in range(1, rng.randint(2, 13)):
                    self.put(results, arm, n, rng.choice(labels), rng.choice(labels),
                             rng.choice(["ok"] * 4 + ["leak"]),
                             [rng.randint(0, 99) / 1000 for _ in range(3)], [rng.randint(0, 900) for _ in range(3)])
            code, out = self.report(results)
            self.assertEqual(code, 0, out)

            base, shown = raw(results, "control"), self.rows(out)
            for arm in ARMS:
                found, got = raw(results, arm), shown[arm]
                after = sum(r[1] == "shelf" for r in found)
                self.assertEqual((int(got["runs"]), int(got["right after"]), int(got["right before"])),
                                 (len(found), after, sum(r[0] == "shelf" for r in found)))
                self.assertEqual(int(got["right-to-wrong flips"].split()[0]),
                                 sum(r[0] == "shelf" and r[1] in ("cell", "fixed-side") for r in found))
                shifts = {} if got["transitions"] == "none" else dict(
                    x.rsplit(" ", 1) for x in got["transitions"].split("; "))
                want = [f"{r[0]}→{r[1]}" for r in found]
                self.assertEqual({k: int(v) for k, v in shifts.items()}, {k: want.count(k) for k in want})
                if not (found and base):
                    self.assertEqual(got["gain"], "n/a")
                    continue
                gain = after - sum(r[1] == "shelf" for r in base)
                extra = avg(found, "cost") - avg(base, "cost")
                self.assertEqual(int(got["gain"]), gain)
                self.assertAlmostEqual(float(got["challenger $/run"]), avg(found, "cost", ["challenger"]), delta=6e-5)
                self.assertAlmostEqual(float(got["extra $/run"]), extra, delta=6e-5)
                self.assertAlmostEqual(float(got["extra min/run"]),
                                       (avg(found, "seconds") - avg(base, "seconds")) / 60, delta=0.051)
                if gain > 0:
                    self.assertAlmostEqual(float(got["$ per extra right design"]), extra * len(found) / gain,
                                           delta=6e-5)
                else:
                    self.assertEqual(got["$ per extra right design"], "n/a")

    def test_roi_without_a_results_argument_reads_the_newest(self):
        for n, name in enumerate(["old", "new"]):
            results = self.tmp / "design-eval" / name / "results"
            self.put(results, "control", 1, "cell", "cell")
            os.utime(results, (n + 1, n + 1))
        code, out = self.report(None, env={"TMPDIR": str(self.tmp)})
        self.assertEqual(code, 0, out)
        self.assertIn(str(self.tmp / "design-eval" / "new"), out)


if __name__ == "__main__":
    unittest.main()
