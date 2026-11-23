import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from route_optimizer import CELL_M, Store, demo_map, parse_order, plan, run, shortest_path  # noqa: E402


class RouteTests(unittest.TestCase):
    def test_path_goes_around_wall(self):
        store = Store({"layout": ["...", ".#.", "..."], "start": [0, 1], "products": {}})
        self.assertEqual(len(shortest_path(store, (0, 1), (2, 1))) - 1, 4)

    def test_unreachable_product_is_an_error(self):
        store = Store({"layout": [".#.", ".#.", ".#."], "start": [0, 0],
                       "products": {"P1": {"name": "milk", "at": [2, 0]}}})
        with self.assertRaises(ValueError):
            plan(store, ["P1"])

    def test_optimized_route_is_not_longer_and_kpis_add_up(self):
        rng = random.Random(3)
        data = demo_map(40, 30, 60, rng)
        store = Store(data)
        pids = rng.sample(sorted(data["products"]), 12)
        listed, optimized = plan(store, pids)
        base = run(store, pids, listed)
        opt = run(store, pids, optimized)
        self.assertLessEqual(opt["distance_m"], base["distance_m"])
        self.assertEqual(opt["picks"], 12)
        self.assertAlmostEqual(opt["distance_m"], opt["steps"] * CELL_M)

    def test_order_parsing(self):
        store = Store({"layout": ["..."], "start": [0, 0],
                       "products": {"P1": {"name": "milk", "at": [1, 0]}}})
        self.assertEqual(parse_order("# list\nP1:milk\n", store), ["P1"])
        with self.assertRaises(ValueError):
            parse_order("P9:bread", store)


if __name__ == "__main__":
    unittest.main()
