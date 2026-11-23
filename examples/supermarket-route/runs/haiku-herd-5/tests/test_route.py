"""C3: the delivery guy visits every basket stop once, on the best walk found."""
import random
import unittest

from route_optimizer import make_store, parse_store, plan_route
from tests.support import COMB, MAZE, store_from


class BestRouteTest(unittest.TestCase):
    def test_every_stop_once_and_never_longer_than_list_order(self):
        wins = 0
        for seed in range(6):
            store = parse_store(make_store(40, 30, 80, seed))
            rng = random.Random(seed)
            ids = rng.sample(list(store.products), 12)
            opt = plan_route(store, ids, "optimized")
            base = plan_route(store, ids, "list")
            self.assertEqual(sorted(opt.seq), list(range(len(opt.nodes))))
            self.assertLessEqual(opt.kpis()["distance_covered_m"], base.kpis()["distance_covered_m"] + 1e-9)
            if opt.kpis()["distance_covered_m"] < base.kpis()["distance_covered_m"]:
                wins += 1
        self.assertGreater(wins, 0)

    def test_reversed_list_is_improved(self):
        store = store_from(COMB, (1, 3), [("A", "a", 1, 1), ("B", "b", 3, 1), ("C", "c", 8, 1), ("D", "d", 7, 3)])
        ids = ["D", "C", "B", "A"]  # worst order for this list
        opt = plan_route(store, ids, "optimized").kpis()["distance_covered_m"]
        base = plan_route(store, ids, "list").kpis()["distance_covered_m"]
        self.assertLess(opt, base)

    def test_maze_route_is_optimal_on_small_case(self):
        store = store_from(MAZE, (1, 1), [("A", "a", 7, 5), ("B", "b", 3, 5), ("C", "c", 5, 4)])
        opt = plan_route(store, ["A", "B", "C"], "optimized").kpis()["distance_covered_m"]
        best = min(
            plan_route(store, list(p), "list").kpis()["distance_covered_m"]
            for p in ([a, b, c] for a in "ABC" for b in "ABC" for c in "ABC" if len({a, b, c}) == 3)
        )
        self.assertLessEqual(opt, best + 1e-9)

    def test_collision_same_cell_counted_twice(self):
        store = store_from(COMB, (1, 3), [("A", "a", 3, 1), ("B", "b", 3, 1), ("C", "c", 8, 1)])
        plan = plan_route(store, ["A", "B", "C"], "optimized")
        self.assertEqual(sum(plan.picks), 3)
        self.assertIn(2, plan.picks)  # both items at one stop


if __name__ == "__main__":
    unittest.main()
