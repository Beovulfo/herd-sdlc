import random
import unittest

from route_optimizer import Store, plan_optimized, simulate
from tests import layouts


class SimulateTests(unittest.TestCase):
    def setUp(self):
        rng = random.Random(7)
        self.data = layouts.aisles(30, 20, 5, 12, rng)
        self.store = Store.from_dict(self.data)
        self.ids = layouts.random_basket(self.store, 8, rng)
        self.route = plan_optimized(self.store, self.ids)
        self.frames = list(simulate(self.store, self.route))

    def test_moves_one_cell_per_step(self):
        prev = self.frames[0]
        for frame in self.frames[1:]:
            moved = abs(frame.x - prev.x) + abs(frame.y - prev.y)
            self.assertIn(moved, (0, 1))
            if moved == 0:
                self.assertIsNotNone(frame.picked_id)
            prev = frame

    def test_kpis_grow_monotonically(self):
        for a, b in zip(self.frames, self.frames[1:]):
            self.assertLessEqual(a.distance, b.distance)
            self.assertLessEqual(a.time_s, b.time_s)
            self.assertLessEqual(a.picked, b.picked)

    def test_final_kpis_match_route(self):
        last = self.frames[-1]
        self.assertEqual(last.distance, self.route.distance)
        self.assertEqual(last.picked, len(self.ids))
        self.assertAlmostEqual(last.time_s, self.route.time_s())

    def test_every_item_picked_in_order_on_its_cell(self):
        picks = [f for f in self.frames if f.picked_id is not None]
        self.assertEqual([f.picked_id for f in picks], list(self.route.stops))
        for f in picks:
            self.assertEqual((f.x, f.y), self.store.products[f.picked_id].cell)


if __name__ == "__main__":
    unittest.main()
