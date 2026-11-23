import time
import unittest

from supermarket_route.gen import generate_store, random_basket
from supermarket_route.layout import parse_list
from supermarket_route.planner import build_model
from supermarket_route.simulate import compare
from tests.test_layouts import check_route


class ScaleTest(unittest.TestCase):
    def test_200_by_200_store_with_60_products_plans_under_60_seconds(self):
        store = generate_store("aisles", width=200, height=200, seed=7, products=300)
        lines = random_basket(store, 60, seed=7)
        start = time.perf_counter()
        model = build_model(store, parse_list(lines, store))
        result = compare(model)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 60.0, f"planning took {elapsed:.1f} s")
        self.assertLessEqual(
            result["optimized"]["distance_covered"], result["list_order"]["distance_covered"]
        )
        check_route(self, store, lines, "optimized")


if __name__ == "__main__":
    unittest.main()
