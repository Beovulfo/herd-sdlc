import unittest

from route_optimizer import plan_route
from tests.support import assert_valid_route, sample_case


class LayoutTest(unittest.TestCase):
    def test_routes_are_valid_and_never_worse_than_list_order(self):
        for kind in ("aisles", "hall", "maze"):
            for seed in range(3):
                for width, height in ((31, 21), (40, 25), (61, 33)):
                    with self.subTest(kind=kind, seed=seed, size=f"{width}x{height}"):
                        _, store, items = sample_case(kind, seed, width, height, 15)
                        list_plan = plan_route(store, items, optimize=False)
                        best = plan_route(store, items)
                        assert_valid_route(self, store, list_plan, items)
                        assert_valid_route(self, store, best, items)
                        self.assertLessEqual(best.distance_m, list_plan.distance_m)
                        self.assertLessEqual(best.time_s, list_plan.time_s)


if __name__ == "__main__":
    unittest.main()
