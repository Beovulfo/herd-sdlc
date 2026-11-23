import json
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import supermarket_route as sr  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def store_from(grid, products, start):
    return sr.Store({"grid": grid, "start": list(start), "products": products})


class RouteTests(unittest.TestCase):
    def test_bfs_walks_around_shelves(self):
        # Shelf in column 1 on rows 0-1: the only way to (0,0)->(2,0) is down and around.
        s = store_from([".#.", ".#.", "..."], [], (0, 0))
        dist, _ = s.bfs(s.start)
        self.assertEqual(dist[s.index((2, 0))], 6)

    def test_unreachable_product_is_an_error(self):
        s = store_from(["...", "###", "..."], [{"id": "A", "x": 0, "y": 2}], (0, 0))
        with self.assertRaises(ValueError):
            sr.plan(s, ["A"])

    def test_optimized_order_is_valid_and_never_worse(self):
        rng = random.Random(3)
        grid = ["".join("#" if rng.random() < 0.15 else "." for _ in range(20)) for _ in range(12)]
        grid[0] = "." * 20  # keep an open border so everything is reachable
        open_cells = [(x, y) for y in range(12) for x in range(20) if grid[y][x] == "."]
        spots = rng.sample(open_cells, 10)
        prods = [{"id": f"P{k}", "x": x, "y": y} for k, (x, y) in enumerate(spots)]
        s = store_from(grid, prods, (0, 0))
        p = sr.plan(s, [f"P{k}" for k in range(10)])
        self.assertEqual(sorted(p["optimized"]), list(range(11)))
        self.assertEqual(p["optimized"][0], 0)
        self.assertLessEqual(sr.path_cost(p["mat"], p["optimized"]),
                             sr.path_cost(p["mat"], p["list"]))

    def test_simulation_matches_planned_distance_and_time(self):
        s = store_from(["......", ".####.", "......"], [{"id": "A", "x": 5, "y": 2},
                                                          {"id": "B", "x": 0, "y": 2}], (0, 0))
        p = sr.plan(s, ["A", "B"])
        for order in (p["list"], p["optimized"]):
            kpi = sr.run_route(s, p, order)
            self.assertEqual(kpi["distance"], sr.path_cost(p["mat"], order))
            self.assertEqual(kpi["picked"], 2)
            self.assertAlmostEqual(kpi["time_s"], kpi["distance"] * sr.STEP_SECONDS
                                   + 2 * sr.PICK_SECONDS)

    def test_sample_store_optimized_beats_list_order(self):
        with open(os.path.join(HERE, "examples", "store.json")) as f:
            s = sr.Store(json.load(f))
        with open(os.path.join(HERE, "examples", "request.txt")) as f:
            ids = sr.parse_request(f.read(), s)
        p = sr.plan(s, ids)
        base = sr.run_route(s, p, p["list"])
        opt = sr.run_route(s, p, p["optimized"])
        self.assertLess(opt["time_s"], base["time_s"])


if __name__ == "__main__":
    unittest.main()
