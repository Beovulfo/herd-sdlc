"""Behaviour tests for the supermarket route optimizer. Run: python3 -m unittest test_routeopt"""
import contextlib
import io
import itertools
import json
import os
import tempfile
import time
import unittest

import gen_map as gm
import routeopt as ro

KINDS = ("aisles", "open", "random", "winding")


def build(kind, seed, w, h, n_products, n_items):
    raw = gm.make_store(kind, seed, w, h, n_products)
    lines = gm.make_list(raw, n_items, seed)
    return ro.load_map(raw), ro.parse_list("\n".join(lines)), raw, lines


def assert_valid_route(tc, store, items, route):
    ids = [i for i, _ in items]
    tc.assertEqual(sorted(set(ids)), sorted(route.stops), "every requested product visited exactly once")
    tc.assertEqual(route.cells[0], store.start)
    tc.assertEqual(route.cells[-1], store.end)
    for a, b in zip(route.cells, route.cells[1:]):
        tc.assertEqual(abs(a[0] - b[0]) + abs(a[1] - b[1]), 1, "steps are to adjacent cells")
        tc.assertTrue(store.walkable(*b), "steps stay on walkable cells")
    tc.assertEqual(route.distance, len(route.cells) - 1)
    for pid, idx in zip(route.stops, route.pick_at):
        _, px, py = store.products[pid]
        cx, cy = route.cells[idx]
        tc.assertLessEqual(abs(cx - px) + abs(cy - py), 1, "picked from the cell next to the product")


class TestLayouts(unittest.TestCase):
    def test_any_layout_gives_valid_route(self):
        for kind in KINDS:
            for seed in (1, 2):
                with self.subTest(kind=kind, seed=seed):
                    store, items, _, _ = build(kind, seed, 41, 31, 300, 15)
                    assert_valid_route(self, store, items, ro.plan(store, items))

    def test_route_goes_around_walls(self):
        raw = {"grid": ["######",
                        "#.##.#",
                        "#.##.#",
                        "#....#",
                        "######"],
               "start": [1, 1], "end": [1, 1],
               "products": [{"id": "A", "name": "apple", "x": 3, "y": 1}]}
        store = ro.load_map(raw)
        route = ro.plan(store, [("A", "apple")])
        assert_valid_route(self, store, [("A", "apple")], route)
        self.assertEqual(route.distance, 14)  # the shelf is only reachable from (4,1): 7 steps there, 7 back

    def test_shared_shelf_and_duplicate_request(self):
        raw = {"grid": ["#####", "#...#", "#####"], "start": [1, 1], "end": [3, 1],
               "products": [{"id": "A", "name": "a", "x": 2, "y": 0}, {"id": "B", "name": "b", "x": 2, "y": 2}]}
        store = ro.load_map(raw)
        items = ro.parse_list("A:a\nB:b\nA:a")
        route = ro.plan(store, items)
        self.assertEqual(sorted(route.stops), ["A", "B"])
        self.assertEqual(route.distance, 2)


class TestScale(unittest.TestCase):
    def test_very_big_store_within_time_bound(self):
        store, items, _, _ = build("aisles", 7, 250, 250, 4000, 60)
        t0 = time.time()
        route = ro.plan(store, items)
        elapsed = time.time() - t0
        assert_valid_route(self, store, items, route)
        self.assertLess(elapsed, 60, f"planning took {elapsed:.1f}s")

    def test_long_list(self):
        store, items, _, _ = build("random", 3, 120, 120, 2000, 150)
        assert_valid_route(self, store, items, ro.plan(store, items))


class TestSimulation(unittest.TestCase):
    def setUp(self):
        self.store, self.items, self.raw, self.lines = build("aisles", 5, 41, 31, 300, 12)
        self.route = ro.plan(self.store, self.items)
        self.events = list(ro.simulate(self.store, self.route))

    def test_one_event_per_step_and_per_pick(self):
        kinds = [e.kind for e in self.events]
        self.assertEqual(kinds.count("move"), self.route.distance)
        self.assertEqual(kinds.count("pick"), len(self.route.stops))
        self.assertEqual(kinds[-1], "done")
        picks = [e for e in self.events if e.kind == "pick"]
        self.assertEqual([e.item for e in picks], self.route.stops)
        self.assertEqual([e.picked for e in picks], list(range(1, len(picks) + 1)))

    def test_running_kpis_never_decrease_and_match_report(self):
        ts = [e.t for e in self.events]
        ds = [e.dist_m for e in self.events]
        self.assertEqual(ts, sorted(ts))
        self.assertEqual(ds, sorted(ds))
        rep = ro.compare(self.store, self.items)["optimized"]
        self.assertAlmostEqual(self.events[-1].t, rep["time_s"], places=6)
        self.assertAlmostEqual(self.events[-1].dist_m, rep["distance_m"], places=6)

    def test_cli_live_prints_running_kpis(self):
        with tempfile.TemporaryDirectory() as d:
            mp, lp = os.path.join(d, "map.json"), os.path.join(d, "list.txt")
            with open(mp, "w") as f:
                json.dump(self.raw, f)
            with open(lp, "w") as f:
                f.write("\n".join(self.lines))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = ro.main(["run", mp, lp, "--live", "--speedup", "1e9"])
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                ro.main(["run", mp, lp, "--live", "--json"])
        text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertGreaterEqual(text.count("picked"), len(self.items))
        for needle in ("time-to-prepare-basket", "distance-covered", "list-order", "saving"):
            self.assertIn(needle, text)


class TestSavings(unittest.TestCase):
    SCENARIOS = [("aisles", 1, 41, 31, 300, 10), ("aisles", 2, 81, 51, 800, 25), ("aisles", 3, 201, 121, 3000, 60),
                 ("open", 4, 40, 40, 400, 15), ("open", 5, 100, 80, 1500, 40),
                 ("random", 6, 60, 60, 500, 20), ("random", 7, 150, 100, 2500, 80),
                 ("winding", 8, 61, 61, 400, 20)]

    def test_saves_more_than_30_percent_time_everywhere(self):
        for kind, seed, w, h, n, k in self.SCENARIOS:
            with self.subTest(kind=kind, seed=seed, items=k):
                store, items, _, _ = build(kind, seed, w, h, n, k)
                rep = ro.compare(store, items)
                self.assertGreater(rep["time_saving_pct"], 30.0, rep)
                self.assertGreaterEqual(rep["distance_saving_pct"], rep["time_saving_pct"] - 1e-9)

    def test_saves_more_than_30_percent_across_many_seeds_for_20_items(self):
        for kind in KINDS:
            worst = min(ro.compare(*build(kind, s, 61, 41, 400, 20)[:2])["time_saving_pct"] for s in range(200, 230))
            self.assertGreater(worst, 30.0, f"{kind}: worst of 30 seeds")

    def test_time_includes_walking_picking_and_return(self):
        store, items, _, _ = build("aisles", 1, 41, 31, 300, 10)
        rep = ro.compare(store, items)["list_order"]
        walk = rep["distance_m"] / store.speed_mps
        self.assertAlmostEqual(rep["time_s"], walk + len({i for i, _ in items}) * store.pick_s, places=6)


class TestInputErrors(unittest.TestCase):
    BASE = {"grid": ["#####", "#...#", "#####"], "start": [1, 1], "end": [3, 1],
            "products": [{"id": "A", "name": "a", "x": 2, "y": 0}]}

    def raw(self, **kw):
        d = json.loads(json.dumps(self.BASE))
        d.update(kw)
        return d

    def test_unknown_product_in_list(self):
        store = ro.load_map(self.raw())
        with self.assertRaisesRegex(ValueError, "unknown product"):
            ro.plan(store, ro.parse_list("ZZZ:nothing"))

    def test_unreachable_product(self):
        raw = self.raw(grid=["#####", "#.#.#", "#####"], end=[1, 1],
                       products=[{"id": "A", "name": "a", "x": 3, "y": 0}])
        with self.assertRaisesRegex(ValueError, "unreachable"):
            ro.plan(ro.load_map(raw), ro.parse_list("A:a"))

    def test_malformed_maps(self):
        bad = [self.raw(grid=["#####", "#..#", "#####"]),
               self.raw(start=[0, 0]),
               self.raw(start=[9, 9]),
               self.raw(products=[self.BASE["products"][0], self.BASE["products"][0]]),
               self.raw(products=[{"id": "A", "name": "a", "x": 50, "y": 0}]),
               self.raw(grid=["#####", "#.X.#", "#####"]),
               self.raw(speed_mps=float("nan")),
               self.raw(products=[{"id": "A", "name": "a", "x": 2.7, "y": 0}])]
        for raw in bad:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    ro.load_map(raw)

    def test_empty_list_rejected(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            ro.plan(ro.load_map(self.raw()), ro.parse_list("\n# nothing\n"))


class TestRouteQuality(unittest.TestCase):
    def test_never_worse_than_list_order_and_near_brute_force(self):
        for seed in range(1, 13):
            with self.subTest(seed=seed):
                store, items, _, _ = build(KINDS[seed % 4], seed, 31, 25, 120, 6)
                ids = [i for i, _ in items]
                cells = [store.start] + [store.access(i) for i in ids] + [store.end]
                dm = ro.distance_matrix(store, cells)
                k = len(ids)
                best = min(dm[0][p[0]] + sum(dm[a][b] for a, b in zip(p, p[1:])) + dm[p[-1]][k + 1]
                           for p in itertools.permutations(range(1, k + 1)))
                opt = ro.plan(store, items).distance
                base = ro.plan(store, items, optimize=False).distance
                self.assertLessEqual(opt, base)
                best_order = min(itertools.permutations(range(1, k + 1)),
                                 key=lambda p: dm[0][p[0]] + sum(dm[a][b] for a, b in zip(p, p[1:])) + dm[p[-1]][k + 1])
                already_best = [items[i - 1] for i in best_order]  # list order is already optimal
                self.assertEqual(ro.plan(store, already_best).distance, best)
                self.assertLessEqual(opt, best * 1.10 + 1e-9)
                self.assertGreaterEqual(opt, best)


if __name__ == "__main__":
    unittest.main()
