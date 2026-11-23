import random
import unittest

from route_optimizer import Store, compare, plan_list_order, simulate
from tests import layouts


class CompareTests(unittest.TestCase):
    def setUp(self):
        rng = random.Random(11)
        self.data = layouts.open_hall(40, 30, 25, rng)
        self.store = Store.from_dict(self.data)
        self.ids = layouts.random_basket(self.store, 10, rng)

    def test_list_order_keeps_customer_order(self):
        self.assertEqual(plan_list_order(self.store, self.ids).stops, tuple(self.ids))

    def test_both_routes_report_both_kpis(self):
        result = compare(self.store, self.ids)
        for key in ("list", "optimized"):
            self.assertIn("time_s", result[key])
            self.assertIn("distance_m", result[key])
        self.assertIn("saving_pct", result)

    def test_saving_is_computed_from_the_two_times(self):
        result = compare(self.store, self.ids)
        expected = (result["list"]["time_s"] - result["optimized"]["time_s"]) / result["list"]["time_s"] * 100
        self.assertAlmostEqual(result["saving_pct"], expected)
        self.assertLessEqual(result["optimized"]["distance_m"], result["list"]["distance_m"])

    def test_list_route_simulation_matches_comparison(self):
        result = compare(self.store, self.ids)
        last = list(simulate(self.store, plan_list_order(self.store, self.ids)))[-1]
        self.assertEqual(last.distance, result["list"]["distance_m"])
        self.assertAlmostEqual(last.time_s, result["list"]["time_s"])


if __name__ == "__main__":
    unittest.main()
