import itertools
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import unittest

import routeopt as ro

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tmp(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    f.write(text)
    f.close()
    return f.name


def random_case(kind, size, n, seed):
    m = ro.gen_map(kind, size, n * 2, seed)
    rnd = random.Random(seed)
    ps = rnd.sample(m["products"], min(n, len(m["products"])))
    return m, [(p["id"], p["name"]) for p in ps]


def cli(*args):
    return subprocess.run([sys.executable, os.path.join(HERE, "routeopt.py"), *args], capture_output=True, text=True)


class Savings(unittest.TestCase):
    def test_saves_over_30_percent_on_many_layouts(self):
        for kind in ("aisles", "open", "maze"):
            for seed in range(5):
                m, items = random_case(kind, 50, 20, seed)
                res = ro.run(m, items)
                self.assertGreater(res["time_saved_pct"], 30, (kind, seed, res))

    def test_never_worse_than_list_order(self):
        for seed in range(10):
            m, items = random_case("maze", 20, 6, seed)
            res = ro.run(m, items)
            self.assertLessEqual(res["optimized"]["time_s"], res["list-order"]["time_s"] + 1e-9)

    def test_near_optimal_vs_brute_force(self):
        for seed in range(5):
            m, items = random_case("aisles", 30, 7, seed)
            grid, start, stops, _, opt = ro.plan(m, items)
            nodes = [start] + [s[1] for s in stops]
            d = [[ro.bfs(grid, a)[0][b] for b in nodes] for a in nodes]
            best = min(ro.tour_len([0, *p, 0], d) for p in itertools.permutations(range(1, len(nodes))))
            got = ro.tour_len([0, *opt, 0], d)
            self.assertLessEqual(got, best * 1.1, (seed, got, best))


class Recount(unittest.TestCase):
    def test_trace_replay_matches_reported_kpis(self):
        m, items = random_case("aisles", 40, 12, 3)
        events = {"list-order": [], "optimized": []}
        res = ro.run(m, items, lambda n, k, c, l, dm, t: events[n].append((k, c, l, dm, t)))
        grid, start = m["grid"], tuple(m["start"])
        for name, ev in events.items():
            pos, steps, picks = start, 0, 0
            for k, c, label, dm, t in ev:
                if k == "move":
                    self.assertEqual(abs(c[0] - pos[0]) + abs(c[1] - pos[1]), 1)
                    self.assertNotEqual(grid[c[0]][c[1]], "#")
                    steps += 1
                    pos = c
                else:
                    picks += 1
                self.assertAlmostEqual(dm, steps)
                self.assertAlmostEqual(t, steps / 1.2 + picks * 5.0)
            self.assertEqual(pos, start)
            self.assertEqual(picks, len(items))
            self.assertAlmostEqual(res[name]["distance_m"], steps)
            self.assertAlmostEqual(res[name]["time_s"], steps / 1.2 + picks * 5.0)

    def test_every_requested_product_is_picked(self):
        m, items = random_case("maze", 30, 10, 2)
        seen = []
        ro.run(m, items, lambda n, k, c, l, dm, t: n == "optimized" and k == "pick" and seen.append(l))
        self.assertEqual(sorted(seen), sorted(i for i, _ in items))


class Collisions(unittest.TestCase):
    def test_same_cell_and_repeated_ids_all_counted(self):
        m = {"grid": ["....", "....", "...."], "start": [0, 0],
             "products": [{"id": "A", "name": "a", "pos": [2, 3]}, {"id": "B", "name": "b", "pos": [2, 3]}]}
        picks = []
        res = ro.run(m, [("A", "a"), ("B", "b"), ("A", "a")], lambda n, k, c, l, dm, t: n == "optimized" and k == "pick" and picks.append(l))
        self.assertEqual(sorted(picks), ["A", "A", "B"])
        self.assertAlmostEqual(res["optimized"]["time_s"], 8 / 1.2 + 15)


class OneBadPart(unittest.TestCase):
    def setUp(self):
        self.m = {"grid": ["..#..", "..#..", "..#.."], "start": [0, 0], "products": [
            {"id": "OK", "name": "ok", "pos": [2, 1]},
            {"id": "FAR", "name": "far", "pos": [0, 4]},     # cut off by the wall
            {"id": "BAD", "pos": "nowhere"},                 # malformed, not requested
            {"id": "OUT", "name": "o", "pos": [9, 9]}]}      # outside, not requested

    def test_unrequested_broken_products_are_ignored(self):
        res = ro.run(self.m, [("OK", "ok")])
        self.assertGreater(res["optimized"]["distance_m"], 0)

    def test_requested_broken_products_fail_clearly(self):
        for pid in ("FAR", "BAD", "OUT", "NOPE"):
            with self.assertRaises(ro.Err):
                ro.run(self.m, [("OK", "ok"), (pid, "")])


class BadInput(unittest.TestCase):
    def check_fail(self, *args, msg):
        r = cli(*args)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn(msg, r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_entry_points(self):
        good = tmp(json.dumps({"grid": ["..."], "start": [0, 0], "products": [{"id": "A", "name": "a", "pos": [0, 2]}]}))
        lst = tmp("A:a\n")
        self.check_fail("run", "/no/such/map.json", lst, msg="cannot read map")
        self.check_fail("run", tmp("{not json"), lst, msg="not valid JSON")
        self.check_fail("run", tmp("[]"), lst, msg="map needs")
        self.check_fail("run", tmp("{}"), lst, msg="map needs")
        self.check_fail("run", tmp(json.dumps({"grid": ["..", "."], "start": [0, 0], "products": []})), lst, msg="equal length")
        self.check_fail("run", tmp(json.dumps({"grid": ["#."], "start": [0, 0], "products": []})), lst, msg="not a walkable")
        self.check_fail("run", good, "/no/such/list", msg="cannot read list")
        self.check_fail("run", good, tmp(""), msg="empty")
        self.check_fail("run", good, tmp("no colon here\n"), msg="expected 'id:short name'")
        self.check_fail("run", good, tmp("Z:zed\n"), msg="not in the map")
        self.check_fail("run", good, tmp("A:wrong\n"), msg="list says")
        with open(tmp(""), "wb") as f:
            pass
        bin_list = tempfile.NamedTemporaryFile("wb", delete=False)
        bin_list.write(b"\xff\xfe\x00")
        bin_list.close()
        self.check_fail("run", good, bin_list.name, msg="not text")
        self.check_fail("gen", "--kind", "zzz", "--out", os.devnull, msg="unknown layout")
        self.check_fail("gen", "--size", "1", "--out", os.devnull, msg="--size")

    def test_duplicate_map_id_fails_only_when_requested(self):
        m = {"grid": ["..."], "start": [0, 0], "products": [{"id": "A", "pos": [0, 1]}, {"id": "A", "pos": [0, 2]}, {"id": "B", "pos": [0, 2]}]}
        ro.run(m, [("B", "")])
        with self.assertRaises(ro.Err):
            ro.run(m, [("A", "")])


class Scale(unittest.TestCase):
    def test_big_store_within_time_limit(self):
        m, items = random_case("aisles", 400, 40, 1)
        t0 = time.time()
        res = ro.run(m, items)
        self.assertLess(time.time() - t0, 60)
        self.assertGreater(res["time_saved_pct"], 30)

    def test_cli_end_to_end(self):
        mp = tempfile.mktemp(suffix=".json")
        self.assertEqual(cli("gen", "--size", "40", "--products", "100", "--out", mp).returncode, 0)
        with open(mp) as f:
            m = json.load(f)
        lst = tmp("\n".join(f"{p['id']}:{p['name']}" for p in random.Random(1).sample(m["products"], 15)))
        r = cli("run", mp, lst, "--min-saving", "30")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("time-to-prepare-basket", r.stdout)
        r = cli("run", mp, lst, "--trace")
        self.assertIn("pick", r.stdout)


if __name__ == "__main__":
    unittest.main()
