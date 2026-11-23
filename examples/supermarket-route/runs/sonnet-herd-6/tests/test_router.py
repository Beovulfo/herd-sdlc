import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import router

LAYOUTS = ["aisles", "open", "maze", "perimeter"]


def solve(m, lines, seconds=3.0):
    items = [tuple(x.split(":", 1)) for x in lines]
    return router.run_both(router.parse_map(m), items, seconds)


def check_route(testcase, m, steps, lines):
    """Independent validation of a trace: walkable, adjacent steps, every item picked, ends at checkout."""
    grid = m["grid"]
    start = tuple(m["start"])
    end = tuple(m.get("checkout", m["start"]))
    pos = {p["id"]: (p["x"], p["y"]) for p in m["products"]}
    prev, picked = None, []
    for s in steps:
        c = (s["x"], s["y"])
        testcase.assertNotEqual(grid[c[1]][c[0]], "#")
        if s["event"] == "move":
            testcase.assertEqual(abs(c[0] - prev[0]) + abs(c[1] - prev[1]), 1)
        if s["event"].startswith("pick "):
            pid = s["event"].split()[1]
            px, py = pos[pid]
            testcase.assertLessEqual(abs(c[0] - px) + abs(c[1] - py), 1)
            picked.append(pid)
        prev = c
    testcase.assertEqual((steps[0]["x"], steps[0]["y"]), start)
    testcase.assertEqual(prev, end)
    testcase.assertEqual(sorted(picked), sorted(ln.split(":")[0] for ln in lines))
    return len([s for s in steps if s["event"] == "move"]), len(picked)


class TestLayouts(unittest.TestCase):  # C1: any layout
    def test_valid_route_on_every_layout(self):
        for layout in LAYOUTS:
            for seed in range(5):
                with self.subTest(layout=layout, seed=seed):
                    m, lines = router.generate(layout, seed, 40, 30, 12)
                    res = solve(m, lines)
                    for name in res:
                        check_route(self, m, res[name], lines)
                    self.assertLessEqual(router.kpis(res["optimized"])[1], router.kpis(res["list"])[1])

    def test_odd_shapes(self):
        # 1x1 store, a corridor, a disconnected pocket that holds no requested item
        one = {"grid": ["."], "start": [0, 0], "products": [{"id": "A", "name": "a", "x": 0, "y": 0}]}
        res = solve(one, ["A:a"])
        self.assertEqual(router.kpis(res["optimized"])[1], 0)
        corridor = {"grid": ["....#.."], "start": [0, 0], "products": [
            {"id": "A", "name": "a", "x": 3, "y": 0}, {"id": "Z", "name": "z", "x": 6, "y": 0}]}
        check_route(self, corridor, solve(corridor, ["A:a"])["optimized"], ["A:a"])
        with self.assertRaises(router.MapError):  # requested but unreachable
            solve(corridor, ["Z:z"])


class TestScale(unittest.TestCase):  # C1: very big
    def test_big_store_under_time_limit(self):
        m, lines = router.generate("aisles", 7, 300, 300, 40)
        t0 = time.time()
        res = solve(m, lines, seconds=10)
        self.assertLess(time.time() - t0, 90)
        check_route(self, m, res["optimized"], lines)
        self.assertLess(router.kpis(res["optimized"])[1], router.kpis(res["list"])[1])


class TestSimulation(unittest.TestCase):  # C2: step-by-step KPIs
    def test_trace_kpis_recounted_independently(self):
        m, lines = router.generate("aisles", 3, 40, 30, 15)
        with tempfile.TemporaryDirectory() as d:
            mp, lp, tp = (os.path.join(d, n) for n in ("m.json", "l.txt", "t.csv"))
            with open(mp, "w") as f:
                json.dump(m, f)
            with open(lp, "w") as f:
                f.write("\n".join(lines))
            out = subprocess.run([sys.executable, router.__file__, "run", mp, lp, "--trace", tp, "--seconds", "3"],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            with open(tp) as f:
                rows = list(csv.DictReader(f))
        for name in ("list", "optimized"):
            r = [x for x in rows if x["route"] == name]
            moves = sum(x["event"] == "move" for x in r)
            picks = sum(x["event"].startswith("pick ") for x in r)
            self.assertEqual(picks, len(lines))
            self.assertEqual(int(r[-1]["dist"]), moves)  # distance recount
            self.assertAlmostEqual(float(r[-1]["t"]), moves / 1.4 + picks * 5.0, places=1)  # time recount
            ts = [float(x["t"]) for x in r]
            self.assertEqual(ts, sorted(ts))  # live KPI never goes backwards
            self.assertEqual(len(r), 1 + moves + picks + 1)
        self.assertIn("time-to-prepare-basket=", out.stdout)
        self.assertIn("distance-covered=", out.stdout)
        self.assertEqual(out.stdout.count(" route =="), 2)


class TestSavings(unittest.TestCase):  # C3: more than 30% time saved
    def test_over_30_percent_on_every_generated_case(self):
        worst = 100
        for layout in LAYOUTS:
            for seed in range(8):
                m, lines = router.generate(layout, seed, 60, 40, 15)
                res = solve(m, lines)
                tl, to = router.kpis(res["list"])[0], router.kpis(res["optimized"])[0]
                saved = 100 * (tl - to) / tl
                worst = min(worst, saved)
                self.assertGreater(saved, 30, f"{layout} seed {seed}: {saved:.1f}%")
        print(f"\nworst time saving over 32 cases: {worst:.1f}%")


def cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = router.main(list(args))
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


class TestBadInput(unittest.TestCase):  # C4
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.good = {"grid": ["...", ".#.", "..."], "start": [0, 0],
                     "products": [{"id": "A", "name": "a", "x": 1, "y": 1}]}

    def tearDown(self):
        self.d.cleanup()

    def w(self, name, content):
        p = os.path.join(self.d.name, name)
        with open(p, "w") as f:
            f.write(content if isinstance(content, str) else json.dumps(content))
        return p

    def fails(self, mp, lp, needle=""):
        code, _, err = cli("run", mp, lp)
        self.assertEqual(code, 2, err)
        self.assertTrue(err.startswith("error:") and needle in err, err)
        self.assertNotIn("Traceback", err)

    def test_every_entry_point(self):
        lp = self.w("l.txt", "A:a")
        self.fails(os.path.join(self.d.name, "nope.json"), lp, "cannot read map")
        self.fails(self.w("m1", "{not json"), lp, "not valid JSON")
        self.fails(self.w("m2", "[]"), lp, "JSON object")
        self.fails(self.w("m3", {"grid": ["..", "."], "start": [0, 0], "products": []}), lp, "same length")
        self.fails(self.w("m4", {"grid": ["..."], "products": []}), lp, "start")
        self.fails(self.w("m5", {"grid": ["..."], "start": [9, 9], "products": []}), lp, "outside")
        self.fails(self.w("m6", {"grid": ["#.."], "start": [0, 0], "products": []}), lp, "blocked")
        self.fails(self.w("m7", {"grid": ["..."], "start": [0, 0], "products": 5}), lp, "products")
        self.fails(self.w("m8", dict(self.good, products=[self.good["products"][0]] * 2)), lp, "duplicate")
        mp = self.w("m.json", self.good)
        self.fails(mp, os.path.join(self.d.name, "nope.txt"), "cannot read list")
        self.fails(mp, self.w("l0", ""), "empty")
        self.fails(mp, self.w("l1", "# only comment\n\n"), "empty")
        self.fails(mp, self.w("l2", "no colon here"), "id:short name")
        self.fails(mp, self.w("l3", ":nameonly"), "id:short name")
        self.fails(mp, self.w("l4", "ZZ:ghost"), "not in the map")
        code, _, err = cli("run", mp, self.w("l8", "A:a"), "--trace", os.path.join(self.d.name, "no", "t.csv"))
        self.assertEqual(code, 2)
        self.assertIn("cannot write trace", err)
        code, _, err = cli("gen", "aisles", os.path.join(mp, "x"))
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("error:"), err)
        code, _, err = cli("run", mp, self.w("l5", "A:a"), "--speed", "0")
        self.assertEqual(code, 2)
        self.fails(self.w("bin", ""), self.w("l6", "A:a"))
        with open(os.path.join(self.d.name, "b.json"), "wb") as f:
            f.write(b"\xff\xfe\x00")
        self.fails(os.path.join(self.d.name, "b.json"), self.w("l7", "A:a"), "not valid JSON")


class TestCollisionAndBadPart(unittest.TestCase):  # C5
    def test_same_cell_and_duplicates_all_counted(self):
        m = {"grid": ["....", ".##.", "...."], "start": [0, 0], "products": [
            {"id": "A", "name": "milk", "x": 1, "y": 1}, {"id": "B", "name": "milk", "x": 1, "y": 1},
            {"id": "C", "name": "milk", "x": 2, "y": 1}]}
        lines = ["A:milk", "B:milk", "C:milk", "A:milk"]  # same shelf cell, equal names, repeated id
        res = solve(m, lines)
        for name in res:
            picks = [s for s in res[name] if s["event"].startswith("pick ")]
            self.assertEqual(len(picks), 4)

    def test_unrequested_broken_entries_are_ignored_requested_ones_fail(self):
        m = {"grid": ["...", "###", "..."], "start": [0, 0], "products": [
            {"id": "A", "name": "a", "x": 2, "y": 0},
            {"id": "FAR", "name": "far", "x": 1, "y": 2},      # unreachable, not requested
            {"id": "BAD", "name": "bad", "x": "x", "y": None},  # malformed, not requested
            {"name": "noid", "x": 0, "y": 0}, "garbage", None]}
        res = solve(m, ["A:a"])
        self.assertEqual(sum(s["event"].startswith("pick ") for s in res["optimized"]), 1)
        for req in ("FAR:far", "BAD:bad"):
            with self.assertRaises(router.MapError):
                solve(m, ["A:a", req])


if __name__ == "__main__":
    unittest.main()
