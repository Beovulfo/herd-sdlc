# ruff: noqa: E741
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from itertools import permutations

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import router  # noqa: E402


def store_for(layout, w, h, n, seed):
    return router.Store(router.gen_map(layout, w, h, n, seed))


def ids_of(data, k, seed):
    return [s.split(":")[0] for s in router.gen_list(data, k, seed)]


def replay(store, ids, optimize, prods):
    """Independent recount: events -> cells; check adjacency/walkability and recompute KPIs."""
    evs = list(router.simulate(store, ids, optimize))
    cells = [(e["x"], e["y"]) for e in evs if e["kind"] in ("start", "step")]
    for (x0, y0), (x1, y1) in zip(cells, cells[1:]):
        assert abs(x0 - x1) + abs(y0 - y1) == 1, "non-adjacent step"
        assert store.rows[y1][x1] != "#", "walked through a shelf"
    steps = len(cells) - 1
    picks = [e for e in evs if e["kind"] == "pick"]
    assert len(picks) == len(ids)
    for e in picks:  # each pick happens on or next to the product's own map cell
        pr = next(q for q in prods if q["id"] == e["item"])
        assert abs(pr["x"] - e["x"]) + abs(pr["y"] - e["y"]) <= 1, "picked from afar"
    end = evs[-1]
    assert end["steps"] == steps and abs(end["distance_m"] - steps * store.cell_m) < 1e-9
    t = steps * store.cell_m / store.walk_speed_mps + len(ids) * store.pick_s
    assert abs(end["time_s"] - t) < 1e-6
    assert sorted(e["item"] for e in picks) == sorted(ids)
    return evs, steps


class Layouts(unittest.TestCase):  # C1: any layout, very big
    def test_many_layouts_valid_and_not_worse(self):
        for layout in ("aisles", "islands", "random", "open"):
            for seed in range(3):
                for (w, h) in ((15, 9), (40, 30), (7, 40)):
                    d = router.gen_map(layout, w, h, 60, seed)
                    if not d["products"]:
                        continue
                    st = router.Store(d)
                    ids = ids_of(d, 15, seed)
                    _, s_opt = replay(st, ids, True, d['products'])
                    _, s_base = replay(st, ids, False, d['products'])
                    self.assertLessEqual(s_opt, s_base, (layout, seed, w, h))

    def test_very_big_store_within_time_limit(self):
        t0 = time.time()
        d = router.gen_map("aisles", 200, 200, 2000, 1)
        st = router.Store(d)
        ids = ids_of(d, 60, 1)
        r = router.compare(st, ids)
        self.assertLess(time.time() - t0, 60)
        self.assertGreater(r["time_saved_pct"], 30)

    def test_hostile_random_maze_with_100_items(self):
        t0 = time.time()
        d = router.gen_map("random", 200, 200, 3000, 1)
        r = router.compare(router.Store(d), ids_of(d, 100, 1))
        self.assertLess(time.time() - t0, 60)
        self.assertGreater(r["time_saved_pct"], 30)

    def test_corridor_and_single_item(self):
        st = router.Store({"rows": ["S.....C"], "products": [{"id": "A", "name": "a", "x": 3, "y": 0}]})
        evs, steps = replay(st, ["A"], True, [{"id": "A", "x": 3, "y": 0}])
        self.assertEqual(steps, 6)

    def test_disconnected_store_unrequested_pocket_ignored(self):
        rows = ["S...#..", ".##.#..", "...C#.."]
        prods = [{"id": "A", "name": "a", "x": 1, "y": 1}, {"id": "Z", "name": "z", "x": 6, "y": 1}]
        st = router.Store({"rows": rows, "products": prods})
        self.assertIn("Z", st.bad)
        router.compare(st, ["A"])
        with self.assertRaises(router.RouteError):
            router.plan(st, ["Z"])


class Inputs(unittest.TestCase):  # C2: map + id:name list from files
    def test_cli_reads_map_and_list_files(self):
        d = router.gen_map("aisles", 30, 20, 40, 2)
        with tempfile.TemporaryDirectory() as t:
            m, l = os.path.join(t, "m.json"), os.path.join(t, "l.txt")
            json.dump(d, open(m, "w"))
            open(l, "w").write("\n".join(router.gen_list(d, 8, 2)) + "\n")
            p = subprocess.run([sys.executable, os.path.join(ROOT, "router.py"), "simulate", m, l], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("time saved:", p.stdout)

    def test_list_parsing(self):
        self.assertEqual(router.parse_list("# c\nP1:milk\n\n P2 \nP1:milk\n"), ["P1", "P2", "P1"])


class Simulation(unittest.TestCase):  # C3: step by step, live KPIs
    def test_kpis_are_monotonic_and_match_recount(self):
        d = router.gen_map("islands", 40, 30, 50, 3)
        st = router.Store(d)
        evs, steps = replay(st, ids_of(d, 12, 3), True, d["products"])
        for a, b in zip(evs, evs[1:]):
            self.assertGreaterEqual(b["time_s"], a["time_s"])
            self.assertGreaterEqual(b["distance_m"], a["distance_m"])
        self.assertEqual(evs[0]["kind"], "start")
        self.assertEqual(evs[-1]["kind"], "done")
        self.assertGreater(len(evs), steps)  # one event per step plus picks

    def test_trace_prints_every_step(self):
        d = router.gen_map("open", 12, 8, 10, 0)
        with tempfile.TemporaryDirectory() as t:
            m, l = os.path.join(t, "m.json"), os.path.join(t, "l.txt")
            json.dump(d, open(m, "w"))
            open(l, "w").write("\n".join(router.gen_list(d, 4, 0)))
            out = subprocess.run([sys.executable, os.path.join(ROOT, "router.py"), "simulate", m, l, "--trace"], capture_output=True, text=True).stdout
            self.assertIn("distance-covered=", out)
            self.assertIn("time-to-prepare-basket=", out)
            self.assertGreater(out.count(" step "), 10)


class Savings(unittest.TestCase):  # C4: more than 30 percent time saved vs list order
    def test_saves_over_30_percent_on_every_layout_and_seed(self):
        for layout in ("aisles", "islands", "random", "open"):
            saved = []
            for seed in range(8):
                d = router.gen_map(layout, 60, 40, 200, seed)
                saved.append(router.compare(router.Store(d), ids_of(d, 20, seed))["time_saved_pct"])
            self.assertGreater(min(saved), 30, (layout, saved))


class Optimality(unittest.TestCase):  # C6: exact for small lists
    def test_matches_brute_force(self):
        for seed in range(5):
            d = router.gen_map("aisles", 30, 20, 30, seed)
            st = router.Store(d)
            ids = ids_of(d, 6, seed)
            p = router.plan(st, ids)
            cells = [st.products[i][1] for i in ids]
            dist = {c: st.bfs(c) for c in cells + [st.start, st.end]}
            best = min(dist[st.start][cells[a[0]]] + sum(dist[cells[x]][cells[y]] for x, y in zip(a, a[1:])) + dist[cells[a[-1]]][st.end]
                       for a in permutations(range(6)))
            self.assertEqual(p["dist"], best)


class BadInput(unittest.TestCase):  # C5 + attacks
    def run_cli(self, m, l):
        return subprocess.run([sys.executable, os.path.join(ROOT, "router.py"), "simulate", m, l], capture_output=True, text=True)

    def test_every_entry_point_fails_cleanly(self):
        good = router.gen_map("open", 8, 6, 5, 0)
        gl = "\n".join(router.gen_list(good, 2, 0))
        cases = {
            "missing map": (None, gl), "missing list": (good, None),
            "map not json": ("{oops", gl), "map not object": ("[1]", gl), "empty rows": ({"rows": [], "products": []}, gl),
            "ragged rows": ({"rows": ["S.", "."], "products": []}, "A"), "no start": ({"rows": ["..", ".."], "products": []}, "A"),
            "products wrong type": ({"rows": ["S."], "products": 5}, "A"), "bad speed": ({"rows": ["S."], "products": [], "walk_speed_mps": 0}, "A"),
            "nan speed": ('{"rows": ["S.C"], "products": [], "walk_speed_mps": NaN}', "A"),
            "empty list": (good, "\n# nothing\n"), "unknown id": (good, "NOPE:x"), "blank id": (good, ":x"),
            "unreadable list": (good, b"\xff\xfe\x00"), "walled-in checkout": ({"rows": ["S#C"], "products": []}, "A"),
        }
        with tempfile.TemporaryDirectory() as t:
            for name, (m, l) in cases.items():
                mp, lp = os.path.join(t, "m.json"), os.path.join(t, "l.txt")
                for p in (mp, lp):
                    if os.path.exists(p):
                        os.remove(p)
                if m is not None:
                    open(mp, "w").write(m if isinstance(m, str) else json.dumps(m))
                if l is not None:
                    open(lp, "wb").write(l if isinstance(l, bytes) else l.encode())
                r = self.run_cli(mp, lp)
                self.assertEqual(r.returncode, 2, (name, r.stdout, r.stderr))
                self.assertNotIn("Traceback", r.stderr, name)
                self.assertEqual(len(r.stderr.strip().splitlines()), 1, (name, r.stderr))

    def test_gen_unwritable_path_fails_cleanly(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "router.py"), "gen", "open", "/nonexistent/dir/x"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_collision_same_cell_and_duplicate_ids_all_counted(self):
        rows = ["S.....C"]
        prods = [{"id": "A", "name": "a", "x": 3, "y": 0}, {"id": "B", "name": "b", "x": 3, "y": 0}]
        st = router.Store({"rows": rows, "products": prods})
        evs, _ = replay(st, ["A", "B", "A"], True, prods)
        self.assertEqual(sum(e["kind"] == "pick" for e in evs), 3)
        self.assertEqual(evs[-1]["time_s"], evs[-1]["steps"] / 1.2 + 3 * 4.0)

    def test_one_bad_unrequested_product_does_not_reject_map(self):
        d = router.gen_map("aisles", 20, 12, 10, 0)
        good_ids = ids_of(d, 5, 0)
        d["products"] += [{"id": "X1", "x": 99, "y": 99, "name": "n"}, {"id": "X2"}, "junk", {"id": "X3", "name": "q", "x": "a", "y": 1}]
        st = router.Store(d)
        self.assertEqual({"X1", "X2", "X3", "?"} - set(st.bad), set())
        router.compare(st, good_ids)
        with self.assertRaises(router.RouteError):
            router.plan(st, ["X1"])

    def test_walled_in_requested_product_fails_clearly(self):
        st = router.Store({"rows": ["S.C#.", "..##."], "products": [{"id": "A", "name": "a", "x": 4, "y": 0}]})
        with self.assertRaises(router.RouteError):
            router.plan(st, ["A"])


if __name__ == "__main__":
    unittest.main()
