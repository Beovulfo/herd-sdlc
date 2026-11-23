import json
import os
import random
import subprocess
import sys
import tempfile
import time
import unittest

import route

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def store_and_items(layout, seed, rows=40, cols=60, n=20):
    store = route.parse_store(route.make_store(rows, cols, layout, seed))
    ids = list(store["products"])
    random.Random(seed).shuffle(ids)
    return store, [(i, store["products"][i]["name"]) for i in ids[:n]]


def trace_of(store, items, order_name, speed=1.0, pick_s=10.0):
    stops = route.resolve(store, items)
    order = list(range(len(stops))) if order_name == "list" else route.optimize(store, stops)
    return stops, list(route.simulate(store, stops, order, speed, pick_s))


def recount(store, stops, trace, speed, pick_s):
    """Independent check from the trace alone: adjacency, walls, picks, distance, time."""
    g = store["grid"]
    moves = picks = 0
    for a, b in zip(trace, trace[1:]):
        if b["event"] == "move":
            assert abs(a["pos"][0] - b["pos"][0]) + abs(a["pos"][1] - b["pos"][1]) == 1
            assert g[b["pos"][0]][b["pos"][1]] != "#"
            moves += 1
        elif b["event"].startswith("pick "):
            assert a["pos"] == b["pos"]
            pid = b["event"][5:]
            r, c = store["products"][pid]["pos"]
            assert abs(r - b["pos"][0]) + abs(c - b["pos"][1]) <= 1
            picks += 1
    assert trace[0]["pos"] == trace[-1]["pos"] == store["start"]
    return moves, picks, moves / speed + picks * pick_s


class Layouts(unittest.TestCase):
    def test_every_layout_and_seed(self):
        for layout in ("aisles", "random", "open-pillars"):
            for seed in range(1, 6):
                store, items = store_and_items(layout, seed, 30, 50, 15)
                for which in ("list", "optimized"):
                    stops, tr = trace_of(store, items, which)
                    moves, picks, t = recount(store, stops, tr, 1.0, 10.0)
                    self.assertEqual(picks, 15)
                    self.assertEqual(sorted(e["event"] for e in tr if e["event"].startswith("pick")),
                                     sorted("pick " + i for i, _ in items))

    def test_odd_shapes(self):
        # one-wide corridor, no shelves, product on the start cell, unreachable pocket unrequested
        s = route.parse_store({"grid": ["S....", "#####", ".#..."], "products": [
            {"id": "a", "name": "a", "row": 0, "col": 4}, {"id": "b", "name": "b", "row": 0, "col": 0},
            {"id": "z", "name": "z", "row": 2, "col": 2}]})
        r = route.compare(s, [("a", "a"), ("b", "b")])
        self.assertEqual(r["optimized"]["distance"], 8)
        s = route.parse_store({"grid": ["S"], "products": [{"id": "a", "name": "a", "row": 0, "col": 0}]})
        self.assertEqual(route.compare(s, [("a", "a")])["optimized"]["distance"], 0)

    def test_optimizer_beats_or_ties_list_and_finds_optimum_small(self):
        s = route.parse_store({"grid": ["S......"], "products": [
            {"id": str(i), "name": "", "row": 0, "col": i} for i in (6, 2, 4)]})
        r = route.compare(s, [("6", ""), ("2", ""), ("4", "")])
        self.assertEqual(r["optimized"]["distance"], 12)
        self.assertEqual(r["optimized"]["order"], ["2", "4", "6"])


class Scale(unittest.TestCase):
    def test_big_store_under_limit(self):
        store, items = store_and_items("aisles", 1, 200, 300, 60)
        t0 = time.time()
        r = route.compare(store, items)
        self.assertLess(time.time() - t0, 60)
        self.assertGreater(r["saving_pct"], 30)


class Saving(unittest.TestCase):
    def test_more_than_30_percent_everywhere(self):
        for layout in ("aisles", "random", "open-pillars"):
            for seed in range(1, 11):
                store, items = store_and_items(layout, seed)
                r = route.compare(store, items)
                self.assertGreater(r["saving_pct"], 30, (layout, seed, r["saving_pct"]))


class Simulation(unittest.TestCase):
    def test_steps_and_live_kpis(self):
        store, items = store_and_items("aisles", 3, 30, 50, 10)
        for which in ("list", "optimized"):
            stops, tr = trace_of(store, items, which, 2.0, 7.0)
            moves, picks, t = recount(store, stops, tr, 2.0, 7.0)
            self.assertAlmostEqual(tr[-1]["t"], t)
            self.assertEqual(tr[-1]["distance"], moves)
            self.assertEqual(tr[-1]["picked"], picks)
            for a, b in zip(tr, tr[1:]):  # KPIs never fall, one cell or one pick per event
                self.assertGreaterEqual(b["t"], a["t"])
                self.assertGreaterEqual(b["distance"], a["distance"])
                self.assertLessEqual(b["distance"] - a["distance"], 1)

    def test_cli_prints_live_steps(self):
        out = run_cli("demo", "--size", "20x30", "--items", "5", "--steps").stdout
        self.assertIn("time-to-prepare-basket=", out)
        self.assertIn("distance-covered=", out)
        self.assertGreater(out.count("move"), 20)


def wr(path, text):
    with open(path, "w") as f:
        f.write(text)


def run_cli(*args):
    return subprocess.run([sys.executable, os.path.join(ROOT, "route.py"), *args],
                          capture_output=True, text=True, timeout=120)


MAP = {"grid": ["#####", "#S..#", "#.#.#", "#####"], "products": [
    {"id": "m1", "name": "milk", "row": 0, "col": 2}, {"id": "b1", "name": "bread", "row": 2, "col": 2},
    {"id": "x9", "name": "gold", "row": 0, "col": 0}]}  # x9 unreachable? (0,0) corner has no floor neighbour


class CliInput(unittest.TestCase):
    def test_map_and_list_files(self):
        with tempfile.TemporaryDirectory() as d:
            m, lst = os.path.join(d, "m.json"), os.path.join(d, "l.txt")
            wr(m, json.dumps(MAP))
            wr(lst, "m1:milk\nb1:bread\n")
            p = run_cli("run", m, lst)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(p.stdout.count("pick m1"), 2)  # once per route
            self.assertEqual(p.stdout.count("pick b1"), 2)
            self.assertNotIn("x9", p.stdout)
            self.assertIn("time saved:", p.stdout)


class BadInput(unittest.TestCase):
    def cli(self, mapdata, listtext, raw=None):
        with tempfile.TemporaryDirectory() as d:
            m, lst = os.path.join(d, "m.json"), os.path.join(d, "l.txt")
            wr(m, raw if raw is not None else json.dumps(mapdata))
            wr(lst, listtext)
            return run_cli("run", m, lst)

    def assertClean(self, p, text):
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        self.assertEqual(len(p.stderr.strip().splitlines()), 1)
        self.assertIn(text, p.stderr)

    def mod(self, **kw):
        d = json.loads(json.dumps(MAP))
        d.update(kw)
        return d

    def test_files(self):
        self.assertClean(run_cli("run", "/nope/m.json", "/nope/l.txt"), "cannot read map")
        self.assertClean(self.cli(None, "m1:milk", raw="{oops"), "not valid JSON")
        with tempfile.TemporaryDirectory() as d:
            m = os.path.join(d, "m.json")
            wr(m, json.dumps(MAP))
            self.assertClean(run_cli("run", m, os.path.join(d, "none")), "cannot read list")
            self.assertClean(run_cli("run", d, os.path.join(d, "none")), "cannot read map")

    def test_map_shapes(self):
        for bad, text in [
            ([], "non-empty 'grid'"), ({"grid": [], "products": []}, "non-empty 'grid'"),
            ({"grid": ["#S", "#"], "products": []}, "equal length"),
            ({"grid": [5], "products": []}, "equal length"),
            ({"grid": ["#S?"], "products": []}, "unknown character"),
            ({"grid": ["#.."], "products": []}, "exactly one 'S'"),
            ({"grid": ["SS."], "products": []}, "exactly one 'S'"),
            ({"grid": ["S.."]}, "'products' list"),
            ({"grid": ["S.."], "products": [5]}, "string 'id'"),
            ({"grid": ["S.."], "products": [{"id": "a", "row": "1", "col": 0}]}, "integer"),
            ({"grid": ["S.."], "products": [{"id": "a", "row": 0, "col": True}]}, "integer"),
            ({"grid": ["S.."], "products": [{"id": "a", "row": 5, "col": 0}]}, "outside the grid"),
            ({"grid": ["S.."], "products": [{"id": "a", "row": 0, "col": 1}, {"id": "a", "row": 0, "col": 2}]},
             "duplicate product id"),
        ]:
            self.assertClean(self.cli(bad, "a:x"), text)

    def test_binary_list(self):
        with tempfile.TemporaryDirectory() as d:
            m, lst = os.path.join(d, "m.json"), os.path.join(d, "l.bin")
            wr(m, json.dumps(MAP))
            with open(lst, "wb") as f:
                f.write(b"\xff\xfe\x00")
            self.assertClean(run_cli("run", m, lst), "not UTF-8")

    def test_list_errors(self):
        self.assertClean(self.cli(MAP, ""), "empty")
        self.assertClean(self.cli(MAP, "m1 milk"), "not 'id:short name'")
        self.assertClean(self.cli(MAP, ":milk"), "not 'id:short name'")
        self.assertClean(self.cli(MAP, "zz:milk"), "unknown product id")
        self.assertClean(self.cli(MAP, "m1:milk\nm1:milk"), "duplicate id in list")
        self.assertClean(self.cli(MAP, "m1:cheese"), "named")

    def test_unreachable(self):
        p = self.cli(MAP, "x9:gold")  # requested but boxed in: clear failure
        self.assertClean(p, "cannot be reached")
        wall = self.mod(grid=["S.#.", "..#.", "####"], products=[
            {"id": "a", "name": "a", "row": 0, "col": 1}, {"id": "b", "name": "b", "row": 0, "col": 3}])
        self.assertEqual(self.cli(wall, "a:a").returncode, 0)  # unrequested pocket does not matter
        self.assertClean(self.cli(wall, "a:a\nb:b"), "cannot be reached")

    def test_shared_cell_counts_each(self):
        s = self.mod(products=[{"id": "p", "name": "", "row": 0, "col": 2}, {"id": "q", "name": "", "row": 0, "col": 2}])
        r = route.compare(route.parse_store(s), [("p", ""), ("q", "")])
        self.assertEqual(r["optimized"]["time_s"], r["optimized"]["distance"] + 20)

    def test_bad_flags(self):
        self.assertEqual(run_cli("demo", "--size", "abc").returncode, 2)
        self.assertEqual(run_cli("demo", "--speed", "0").returncode, 2)
        self.assertEqual(run_cli("demo", "--layout", "zzz").returncode, 2)
        self.assertEqual(run_cli("demo", "--items", "0").returncode, 2)


if __name__ == "__main__":
    unittest.main()
