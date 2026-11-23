"""C1: works in any supermarket, very big ones included, whatever its layout."""
import random
import time
import unittest

from route_optimizer import make_store, parse_store, plan_route, simulate
from tests.support import COMB, MAZE, store_from


def assert_valid(tc, store, ids):
    plan = plan_route(store, ids, "optimized")
    tc.assertEqual(sorted(plan.seq), list(range(len(plan.nodes))))  # every stop once
    tc.assertEqual(plan.seq[0], 0)  # starts at the entrance
    tc.assertLessEqual(plan.kpis()["distance_covered_m"],
                       plan_route(store, ids, "list").kpis()["distance_covered_m"] + 1e-9)
    steps = list(simulate(plan))
    tc.assertEqual(sum(p for p in plan.picks), len(ids))
    tc.assertEqual(steps[-1].picked, len(ids))
    return plan


class LayoutFamiliesTest(unittest.TestCase):
    def test_open_hall_aisles_and_hand_made_layouts(self):
        for seed in range(4):
            for width, height in ((12, 9), (30, 25), (61, 40)):
                for shelves in (True, False):
                    data = make_store(width, height, 20, seed, shelves=shelves)
                    store = parse_store(data)
                    rng = random.Random(seed)
                    ids = rng.sample(list(store.products), 8)
                    assert_valid(self, store, ids)
        comb = store_from(COMB, (1, 3), [("A", "a", 1, 1), ("B", "b", 3, 1), ("C", "c", 8, 1), ("D", "d", 7, 3)])
        assert_valid(self, comb, ["A", "B", "C", "D"])
        maze = store_from(MAZE, (1, 1), [("A", "a", 7, 5), ("B", "b", 3, 5), ("C", "c", 5, 4), ("D", "d", 1, 5)])
        assert_valid(self, maze, ["A", "B", "C", "D"])

    def test_single_product_in_entrance_cell(self):
        store = store_from(COMB, (1, 3), [("A", "a", 1, 3)])
        plan = assert_valid(self, store, ["A"])
        self.assertEqual(plan.kpis()["distance_covered_m"], 0.0)


class ScaleTest(unittest.TestCase):
    def test_very_big_store_with_forty_items_under_a_minute(self):
        data = make_store(300, 300, 400, seed=3)
        store = parse_store(data)
        ids = random.Random(9).sample(list(store.products), 40)
        start = time.monotonic()
        plan = plan_route(store, ids, "optimized")
        list_plan = plan_route(store, ids, "list")
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 60.0)
        self.assertEqual(sorted(plan.seq), list(range(len(plan.nodes))))
        self.assertLessEqual(plan.kpis()["distance_covered_m"], list_plan.kpis()["distance_covered_m"])


if __name__ == "__main__":
    unittest.main()
