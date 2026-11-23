"""Tests for routeopt. Recount helpers below are separate from routeopt's own code paths."""

import collections
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest

import routeopt as ro

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = [sys.executable, os.path.join(HERE, "routeopt.py")]
STEP, PICK = ro.STEP_S, ro.PICK_S
STEP_RE = re.compile(r"^  step t=\s*([\d.]+)s dist=\s*(\d+) picked=(\d+)/(\d+) -> \((\d+),(\d+)\)$")
PICK_RE = re.compile(r"^  PICK t=\s*([\d.]+)s dist=\s*(\d+) picked=(\d+)/(\d+) (\S+) at \((\d+),(\d+)\)$")


def cli(*args):
    return subprocess.run(CLI + list(args), capture_output=True, text=True, cwd=HERE)


def write_json(d, obj, name):
    path = os.path.join(d, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    return path


def write_text(d, text, name):
    path = os.path.join(d, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def recount(map_obj, events, step_s, pick_s):
    """Recount steps, picks and time from the events alone, using the raw map rows."""
    rows = map_obj["rows"]
    entrance = next((r, row.index("E")) for r, row in enumerate(rows) if "E" in row)
    cells = {p["id"]: tuple(p["cell"]) for p in map_obj["products"]}
    prev, steps, picks = entrance, 0, 0
    for e in events:
        cell = tuple(e["cell"])
        if e["event"] == "step":
            assert abs(cell[0] - prev[0]) + abs(cell[1] - prev[1]) == 1, f"not a one-cell move: {prev} -> {cell}"
            assert rows[cell[0]][cell[1]] != "#", f"walked into a wall at {cell}"
            steps += 1
        else:
            assert cell == prev, "pick not at the picker's position"
            assert cells[e["item"]] == cell, "pick not at the product's cell"
            picks += 1
        prev = cell
    return steps, steps * step_s + picks * pick_s


class Layouts(unittest.TestCase):
    def test_every_family_many_seeds(self):
        for family in ro.FAMILIES:
            for seed in range(25):
                m, ids = ro.make_store(seed, family, 24, 16, 40, 8)
                store = ro.parse_map(m)
                list_stops, best = ro.solve(store, ids)
                ev_list = list(ro.simulate(store, list_stops, STEP, PICK))
                ev_best = list(ro.simulate(store, best, STEP, PICK))
                for ev in (ev_list, ev_best):
                    steps, t = recount(m, ev, STEP, PICK)
                    k = ro.kpis(ev)
                    self.assertEqual(steps, k["distance_covered"], (family, seed))
                    self.assertAlmostEqual(t, k["time_to_prepare_basket_s"], places=6)
                    self.assertEqual(sorted(e["item"] for e in ev if e["event"] == "pick"), sorted(ids))
                self.assertLessEqual(ro.kpis(ev_best)["distance_covered"], ro.kpis(ev_list)["distance_covered"],
                                     (family, seed))


class Scale(unittest.TestCase):
    def test_very_big_store_under_time_limit(self):
        m, ids = ro.make_store(1, "aisles", 300, 300, 1000, 60)
        t0 = time.time()
        res = ro.compare(ro.parse_map(m), ids, STEP, PICK)
        elapsed = time.time() - t0
        print(f"\n300x300 store, 1000 products, 60 items: {elapsed:.1f} s", file=sys.stderr)
        self.assertLess(elapsed, 120)
        self.assertLessEqual(res["optimized"]["distance_covered"], res["list-order"]["distance_covered"])
        self.assertGreater(res["time_saving_pct"], 0)


class Simulate(unittest.TestCase):
    def test_cli_trace_recount_matches_kpis(self):
        m, ids = ro.make_store(3, "aisles", 30, 20, 60, 12)
        with tempfile.TemporaryDirectory() as d:
            mp = write_json(d, m, "map.json")
            lp = write_text(d, "".join(f"{i}:x\n" for i in ids), "list.txt")
            out = cli("simulate", mp, lp)
        self.assertEqual(out.returncode, 0, out.stderr)
        events, kpi_time, kpi_dist = [], None, None
        for line in out.stdout.splitlines():
            s = STEP_RE.match(line)
            p = PICK_RE.match(line)
            if s:
                events.append({"event": "step", "cell": (int(s[5]), int(s[6]))})
            elif p:
                events.append({"event": "pick", "item": p[5], "cell": (int(p[6]), int(p[7]))})
            elif line.startswith("time-to-prepare-basket:"):
                kpi_time = float(line.split(":")[1].split()[0])
            elif line.startswith("distance-covered:"):
                kpi_dist = int(line.split(":")[1].split()[0])
        self.assertEqual(len([e for e in events if e["event"] == "pick"]), 12)
        steps, t = recount(m, events, STEP, PICK)
        self.assertEqual(steps, kpi_dist)
        self.assertAlmostEqual(t, kpi_time, places=1)

    def test_events_stream_in_order(self):
        m, ids = ro.make_store(4, "open", 12, 8, 20, 5)
        store = ro.parse_map(m)
        _, best = ro.solve(store, ids)
        times = [e["time_s"] for e in ro.simulate(store, best, STEP, PICK)]
        self.assertEqual(times, sorted(times))
        events = list(ro.simulate(store, best, STEP, PICK))
        k = next(i for i, e in enumerate(events) if e["event"] == "step")
        picks_before = sum(e["event"] == "pick" for e in events[:k])
        self.assertAlmostEqual(events[k]["time_s"], STEP + picks_before * PICK)


class Compare(unittest.TestCase):
    def test_cli_compare_both_routes_and_saving(self):
        m, ids = ro.make_store(5, "aisles", 30, 20, 60, 15)
        with tempfile.TemporaryDirectory() as d:
            mp = write_json(d, m, "map.json")
            lp = write_text(d, "".join(f"{i}:x\n" for i in ids), "list.txt")
            out = cli("compare", mp, lp)
        self.assertEqual(out.returncode, 0, out.stderr)
        rows = {ln.split()[0]: ln.split() for ln in out.stdout.splitlines() if ln.startswith(("list-order", "optimized"))}
        self.assertEqual(rows["list-order"][1], "15")
        self.assertEqual(rows["optimized"][1], "15")
        t_list, t_opt = float(rows["list-order"][3]), float(rows["optimized"][3])
        self.assertLessEqual(t_opt, t_list)
        saving = re.search(r"time-to-prepare-basket saving: (-?[\d.]+)%", out.stdout)
        self.assertIsNotNone(saving)
        self.assertAlmostEqual(float(saving[1]), 100 * (t_list - t_opt) / t_list, delta=0.06)

    def test_optimizer_beats_list_order_on_a_zigzag_list(self):
        rows = ["#######", "#E....#", "#.....#", "#######"]
        products = [{"id": "A", "name": "a", "cell": [1, 5]}, {"id": "B", "name": "b", "cell": [1, 2]},
                    {"id": "C", "name": "c", "cell": [2, 5]}, {"id": "D", "name": "d", "cell": [2, 1]}]
        store = ro.parse_map({"rows": rows, "products": products})
        res = ro.compare(store, ["A", "B", "C", "D"], STEP, PICK)
        self.assertLess(res["optimized"]["distance_covered"], res["list-order"]["distance_covered"])


class BadInput(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.d = self.dir.name
        self.map = {"rows": ["#####", "#E..#", "#...#", "#####"],
                    "products": [{"id": "P1", "name": "milk", "cell": [1, 2]},
                                 {"id": "P2", "name": "eggs", "cell": [2, 3]}]}
        self.list = write_text(self.d, "P1:milk\nP2:eggs\n", "list.txt")

    def tearDown(self):
        self.dir.cleanup()

    def assert_clean_error(self, out):
        self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
        self.assertNotIn("Traceback", out.stderr)
        lines = [ln for ln in out.stderr.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1, out.stderr)
        self.assertTrue(lines[0].startswith("routeopt: error:"), lines[0])
        return lines[0]

    def run_with(self, map_obj=None, list_path=None, map_path=None):
        mp = map_path or write_json(self.d, self.map if map_obj is None else map_obj, "map.json")
        return cli("compare", mp, list_path or self.list)

    def test_missing_map(self):
        self.assert_clean_error(self.run_with(map_path=os.path.join(self.d, "nope.json")))

    def test_map_is_a_directory(self):
        self.assert_clean_error(self.run_with(map_path=self.d))

    def test_malformed_json(self):
        p = write_text(self.d, "{not json", "bad.json")
        self.assert_clean_error(self.run_with(map_path=p))

    def test_wrong_type_rows(self):
        self.assert_clean_error(self.run_with(map_obj={"rows": "#E#", "products": []}))

    def test_no_entrance_and_two_entrances(self):
        self.assert_clean_error(self.run_with(map_obj={"rows": ["#...#"], "products": []}))
        self.assert_clean_error(self.run_with(map_obj={"rows": ["E.E"], "products": []}))

    def test_unknown_character(self):
        self.assert_clean_error(self.run_with(map_obj={"rows": ["E?."], "products": []}))

    def test_unknown_product_id_in_list(self):
        lp = write_text(self.d, "P1:milk\nP9:ghost\n", "l.txt")
        msg = self.assert_clean_error(self.run_with(list_path=lp))
        self.assertIn("P9", msg)

    def test_empty_list_and_bad_line(self):
        self.assert_clean_error(self.run_with(list_path=write_text(self.d, "\n# nothing\n", "e.txt")))
        self.assert_clean_error(self.run_with(list_path=write_text(self.d, "P1 milk\n", "n.txt")))

    def test_binary_list(self):
        path = os.path.join(self.d, "bin.txt")
        with open(path, "wb") as f:
            f.write(b"\xff\xfe\x00\x81")
        self.assert_clean_error(self.run_with(list_path=path))

    def test_requested_product_on_a_wall_or_outside(self):
        m = json.loads(json.dumps(self.map))
        m["products"][0]["cell"] = [0, 0]
        self.assert_clean_error(self.run_with(map_obj=m))
        m["products"][0]["cell"] = [9, 9]
        self.assert_clean_error(self.run_with(map_obj=m))

    def test_requested_product_unreachable(self):
        m = {"rows": ["#####", "#E#.#", "#####"],
             "products": [{"id": "P1", "name": "milk", "cell": [1, 3]}]}
        lp = write_text(self.d, "P1:milk\n", "u.txt")
        msg = self.assert_clean_error(self.run_with(map_obj=m, list_path=lp))
        self.assertIn("cannot be reached", msg)

    def test_unrequested_broken_entry_is_skipped_with_warning(self):
        m = json.loads(json.dumps(self.map))
        m["products"].append({"id": "P7", "name": "broken", "cell": [7, 7]})  # outside the map
        m["products"].append({"id": "P8", "name": "twin", "cell": [1, 1]})
        m["products"].append({"id": "P8", "name": "twin", "cell": [2, 2]})  # duplicate, not requested
        out = self.run_with(map_obj=m)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("warning: skipped map entry P7", out.stderr)
        self.assertIn("warning: skipped map entry P8", out.stderr)
        self.assertNotIn("Traceback", out.stderr)
        self.assertIn("optimized", out.stdout)


class BadArguments(unittest.TestCase):
    """Regression tests for gaps the break-it pass found in argument handling."""

    def test_negative_time_is_rejected(self):
        m, ids = ro.make_store(1, "open", 8, 6, 5, 3)
        with tempfile.TemporaryDirectory() as d:
            mp = write_json(d, m, "map.json")
            lp = write_text(d, "".join(f"{i}:x\n" for i in ids), "list.txt")
            out = cli("compare", mp, lp, "--step-s", "-1")
            self.assertEqual(out.returncode, 2)
            self.assertIn("routeopt: error:", out.stderr)
            self.assertNotIn("Traceback", out.stderr)

    def test_bench_with_zero_seeds_is_a_clean_error(self):
        out = cli("bench", "--seeds", "0")
        self.assertEqual(out.returncode, 2)
        self.assertNotIn("Traceback", out.stderr)

    def test_gen_with_empty_list_is_a_clean_error(self):
        with tempfile.TemporaryDirectory() as d:
            out = cli("gen", "open", "--list-size", "0", "--map-out", os.path.join(d, "m.json"),
                      "--list-out", os.path.join(d, "l.txt"))
            self.assertEqual(out.returncode, 2)
            self.assertNotIn("Traceback", out.stderr)


class Collision(unittest.TestCase):
    def test_two_products_on_one_cell_are_both_picked(self):
        m = {"rows": ["#####", "#E..#", "#####"],
             "products": [{"id": "A", "name": "same", "cell": [1, 2]},
                          {"id": "B", "name": "same", "cell": [1, 2]}]}
        store = ro.parse_map(m)
        _, best = ro.solve(store, ["A", "B"])
        ev = list(ro.simulate(store, best, STEP, PICK))
        self.assertEqual(sorted(e["item"] for e in ev if e["event"] == "pick"), ["A", "B"])
        self.assertEqual(ro.kpis(ev)["picks"], 2)

    def test_repeated_list_lines_are_counted_each_time(self):
        m = {"rows": ["#####", "#E..#", "#####"],
             "products": [{"id": "A", "name": "milk", "cell": [1, 2]}]}
        with tempfile.TemporaryDirectory() as d:
            mp = write_json(d, m, "map.json")
            lp = write_text(d, "A:milk\nA:milk\n", "list.txt")
            out = cli("compare", mp, lp)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("optimized", out.stdout)
        rows = {ln.split()[0]: ln.split() for ln in out.stdout.splitlines() if ln.startswith(("list-order", "optimized"))}
        self.assertEqual(rows["list-order"][1], "2")

    def test_duplicate_product_id_on_map_is_unusable_when_requested(self):
        m = {"rows": ["#####", "#E..#", "#####"],
             "products": [{"id": "A", "name": "milk", "cell": [1, 2]},
                          {"id": "A", "name": "milk", "cell": [1, 3]}]}
        with self.assertRaises(ro.RouteError):
            ro.solve(ro.parse_map(m), ["A"])


if __name__ == "__main__":
    unittest.main()
