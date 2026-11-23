import random
import time
import unittest

from route_optimizer import PlanError, Store, plan_optimized, simulate
from tests import layouts


class LayoutTests(unittest.TestCase):
    def check_plan(self, data, ids):
        store = Store.from_dict(data)
        route = plan_optimized(store, ids)
        self.assertEqual(sorted(route.stops), sorted(ids))
        frames = list(simulate(store, route))
        self.assertEqual(frames[-1].distance, route.distance)
        self.assertEqual(frames[-1].picked, len(ids))
        return route

    def test_shapes(self):
        rng = random.Random(1)
        shapes = [
            layouts.open_hall(30, 20, 25, rng),
            layouts.aisles(40, 25, 5, 30, rng),
            layouts.maze(31, 21, 20, rng),
            layouts.rooms(40, 24, 20, rng),
        ]
        for data in shapes:
            for _ in range(3):
                self.check_plan(data, layouts.random_basket(Store.from_dict(data), 10, rng))

    def test_big_store_within_time_limit(self):
        rng = random.Random(2)
        data = layouts.aisles(300, 300, 6, 300, rng)
        ids = layouts.random_basket(Store.from_dict(data), 80, rng)
        started = time.monotonic()
        self.check_plan(data, ids)
        self.assertLess(time.monotonic() - started, 60)

    def test_unreachable_product_is_rejected(self):
        data = layouts.open_hall(10, 10, 3, random.Random(3))
        data["grid"][5] = "#" * 10
        data["products"][0].update(x=0, y=9)
        store = Store.from_dict(data)
        with self.assertRaises(PlanError):
            plan_optimized(store, [data["products"][0]["id"]])


if __name__ == "__main__":
    unittest.main()
