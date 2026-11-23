import itertools
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import unittest
from collections import deque

import route_optimizer as ro

KINDS = ["aisles", "islands", "open", "maze"]
CLI = [sys.executable, "route_optimizer.py"]


def store(kind, seed, h=40, w=60, n=200):
    s = ro.gen_store(kind, seed, h, w, n)
    return s, ro.load_map(write(json.dumps(s)))


def write(text, suffix=".json"):
    f = tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False)
    f.write(text)
    f.close()
    return f.name


def pick_ids(m, k, seed):
    reach, _ = ro.bfs(m, m["entrance"])
    ok = [i for i, p in m["products"].items()
          if "cell" in p and ro.access_cell(m, p["cell"], reach) is not None]
    return random.Random(seed).sample(ok, min(k, len(ok)))


def steps(grid, a, b):
    """Reference BFS written separately from the module: shortest steps a to b (row, col)."""
    h, w = len(grid), len(grid[0])
    d, q = {a: 0}, deque([a])
    while q:
        r, c = q.popleft()
        if (r, c) == b:
            return d[b]
        for n in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
            if 0 <= n[0] < h and 0 <= n[1] < w and grid[n[0]][n[1]] != "#" and n not in d:
                d[n] = d[(r, c)] + 1
                q.append(n)


class Saving(unittest.TestCase):
    def test_over_30_percent_every_layout(self):
        for kind in KINDS:
            for seed in range(1, 6):
                s, m = store(kind, seed)
                ids = pick_ids(m, random.Random(seed).randint(10, 40), seed)
                res = ro.compare(m, ids)
                self.assertGreater(res["time_saving_pct"], 30, (kind, seed, len(ids)))

    def test_optimal_on_small_lists(self):
        for kind in KINDS:
            for seed in range(1, 4):
                s, m = store(kind, seed, 25, 35, 60)
                ids = pick_ids(m, 6, seed)
                res = ro.compare(m, ids)
                grid, w = s["grid"], m["w"]
                reach, _ = ro.bfs(m, m["entrance"])
                cells = [divmod(ro.access_cell(m, m["products"][i]["cell"], reach), w) for i in ids]
                ent, chk = tuple(s["entrance"]), tuple(s["checkout"])
                best = min(sum(steps(grid, a, b) for a, b in zip((ent,) + p, p + (chk,)))
                           for p in itertools.permutations(cells))
                self.assertLessEqual(res["optimized"]["distance_m"], best * 1.02 + 1e-9, (kind, seed))


    def test_heuristic_close_to_optimal(self):
        for kind in KINDS:
            _, m = store(kind, 4, 30, 40, 80)
            ids = pick_ids(m, 9, 4)
            exact = ro.compare(m, ids)["optimized"]["distance_m"]
            old, ro.EXACT_MAX = ro.EXACT_MAX, 0
            try:
                heur = ro.compare(m, ids)["optimized"]["distance_m"]
            finally:
                ro.EXACT_MAX = old
            self.assertLessEqual(heur, exact * 1.08, kind)


class Simulation(unittest.TestCase):
    def test_trace_recount(self):
        """Recompute distance and time from the event trace with separate code."""
        for kind in KINDS:
            s, m = store(kind, 3)
            ids = pick_ids(m, 15, 3)
            for visits in ro.visits_for(m, ids):
                ev = list(ro.simulate(m, visits))
                w, grid = m["w"], s["grid"]
                self.assertEqual(divmod(ev[0]["cell"], w), tuple(s["entrance"]))
                self.assertEqual(divmod(ev[-1]["cell"], w), tuple(s["checkout"]))
                moves = [e for e in ev if e["kind"] == "move"]
                prev = divmod(ev[0]["cell"], w)
                for e in moves:
                    cur = divmod(e["cell"], w)
                    self.assertEqual(abs(cur[0] - prev[0]) + abs(cur[1] - prev[1]), 1)
                    self.assertNotEqual(grid[cur[0]][cur[1]], "#")
                    prev = cur
                picks = [e["id"] for e in ev if e["kind"] == "pick"]
                self.assertEqual(sorted(picks), sorted(ids))
                self.assertAlmostEqual(ev[-1]["distance_m"], len(moves) * m["cell_m"])
                self.assertAlmostEqual(ev[-1]["time_s"], len(moves) / 1.2 + 5.0 * len(ids))
                self.assertTrue(all(a["time_s"] <= b["time_s"] for a, b in zip(ev, ev[1:])))


class Scale(unittest.TestCase):
    def test_big_stores_in_time(self):
        for kind, size, n in (("aisles", 300, 60), ("maze", 301, 40), ("islands", 300, 50)):
            s = ro.gen_store(kind, 7, size, size, 3000)
            m = ro.load_map(write(json.dumps(s)))
            ids = pick_ids(m, n, 7)
            t0 = time.time()
            res = ro.compare(m, ids)
            self.assertLess(time.time() - t0, 30, kind)
            self.assertGreater(res["time_saving_pct"], 30, kind)


def run_cli(map_text, list_text, map_name="m.json"):
    d = tempfile.mkdtemp()
    mp = os.path.join(d, map_name)
    lp = os.path.join(d, "l.txt")
    for path, text in ((mp, map_text), (lp, list_text)):
        if text is not None:
            with open(path, "w") as f:
                f.write(text)
    return subprocess.run(CLI + ["run", mp, lp], capture_output=True, text=True)


GOOD = {"grid": ["....", ".##.", "...."], "entrance": [2, 0], "checkout": [2, 3], "cell_m": 1,
        "products": [{"id": "A", "name": "milk", "row": 1, "col": 1},
                     {"id": "B", "name": "eggs", "row": 1, "col": 2}]}


def good(**over):
    return json.dumps({**GOOD, **over})


class BadInput(unittest.TestCase):
    def clear_failure(self, r):
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertTrue(r.stderr.startswith("error:"), r.stderr)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)

    def test_map_problems(self):
        cases = ["", "not json", "[]", "{}", good(grid=[]), good(grid=["..", "."]), good(grid=[1]),
                 good(entrance=[9, 9]), good(entrance="x"), good(entrance=[0.5, 1]),
                 good(checkout=[1, 1]), good(cell_m=0), good(cell_m="a"), good(products="x"),
                 good(grid=["....", ".##.", "...#"], checkout=[2, 3])]
        for c in cases:
            self.clear_failure(run_cli(c, "A\n"))

    def test_missing_files(self):
        self.clear_failure(subprocess.run(CLI + ["run", "/nonexistent/m.json", "/nonexistent/l"],
                                          capture_output=True, text=True))
        d = tempfile.mkdtemp()
        mp = os.path.join(d, "m.json")
        with open(mp, "w") as f:
            f.write(good())
        self.clear_failure(subprocess.run(CLI + ["run", mp, d + "/missing.txt"],
                                          capture_output=True, text=True))
        self.clear_failure(subprocess.run(CLI + ["run", d, mp], capture_output=True, text=True))
        with open(d + "/bin.txt", "wb") as f:
            f.write(b"\xff\xfe\x00")
        self.clear_failure(subprocess.run(CLI + ["run", mp, d + "/bin.txt"],
                                          capture_output=True, text=True))

    def test_list_problems(self):
        for lst in ("", "\n\n# only a comment\n", "ZZZ:nothing\n", ":nameonly\n"):
            self.clear_failure(run_cli(good(), lst))

    def test_gen_bad_output_path(self):
        r = subprocess.run(CLI + ["gen", "aisles", "--out", "/nonexistent/x"], capture_output=True, text=True)
        self.clear_failure(r)


class Collision(unittest.TestCase):
    def test_same_cell_and_repeated_ids_all_counted(self):
        prods = GOOD["products"] + [{"id": "C", "name": "milk", "row": 1, "col": 1}]  # same cell as A, same name
        out = run_cli(good(products=prods), "A:milk\nC:milk\nA:milk\nB\n")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("items=4/4", out.stdout)
        self.assertEqual(out.stdout.count(" pick "), 4)

    def test_duplicate_id_same_place_ok_different_place_fails_only_if_requested(self):
        prods = GOOD["products"] + [{"id": "A", "name": "milk", "row": 1, "col": 2}]
        self.assertEqual(run_cli(good(products=prods), "B\n").returncode, 0)
        r = run_cli(good(products=prods), "A\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("twice", r.stderr)


class OneBadPart(unittest.TestCase):
    def test_unrequested_broken_or_unreachable_entries_do_not_reject(self):
        prods = GOOD["products"] + [
            {"id": "X", "name": "bad", "row": 99, "col": 0}, {"id": "Y"}, 7, {"id": "Z", "name": "n", "row": "a", "col": 1}]
        r = run_cli(good(products=prods), "A\nB\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("items=2/2", r.stdout)

    def test_unreachable_product_not_requested_ok_requested_fails(self):
        m = {"grid": ["...#.", "...#."], "entrance": [0, 0], "checkout": [1, 2],
             "products": [{"id": "A", "name": "a", "row": 0, "col": 1}, {"id": "F", "name": "far", "row": 0, "col": 4}]}
        self.assertEqual(run_cli(json.dumps(m), "A\n").returncode, 0)
        r = run_cli(json.dumps(m), "A\nF\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("F", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_requested_broken_record_fails_clearly(self):
        prods = GOOD["products"] + [{"id": "X", "name": "bad", "row": 99, "col": 0}]
        r = run_cli(good(products=prods), "A\nX\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("X", r.stderr)

    def test_walled_off_checkout_fails_clearly(self):
        self.assertEqual(run_cli(good(grid=["....", ".##.", "...#"], checkout=[2, 3]), "A\n").returncode, 2)


class Cli(unittest.TestCase):
    def test_gen_then_run_shows_kpis(self):
        d = tempfile.mkdtemp()
        subprocess.run(CLI + ["gen", "aisles", "--out", d + "/s"], check=True, capture_output=True)
        r = subprocess.run(CLI + ["run", d + "/s.json", d + "/s.txt"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("time-to-prepare-basket", r.stdout)
        self.assertIn("distance-covered", r.stdout)
        self.assertRegex(r.stdout, r"saving\s+: time \d+\.\d%")


if __name__ == "__main__":
    unittest.main()
