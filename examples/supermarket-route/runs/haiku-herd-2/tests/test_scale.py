import time
import unittest

from route_optimizer import plan_route
from tests.support import assert_valid_route, sample_case


class ScaleTest(unittest.TestCase):
    def test_very_big_store_with_60_items_plans_in_under_30_seconds(self):
        _, store, items = sample_case("aisles", 7, 300, 300, 60, n_products=200)
        started = time.monotonic()
        plan = plan_route(store, items)
        elapsed = time.monotonic() - started
        assert_valid_route(self, store, plan, items)
        print(f"\n300x300 store, 60 items: planned in {elapsed:.2f} s", flush=True)
        self.assertLess(elapsed, 30.0)


if __name__ == "__main__":
    unittest.main()
