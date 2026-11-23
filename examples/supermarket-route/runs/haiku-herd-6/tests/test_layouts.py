import time
import unittest

from optimizer.plan import optimized_route
from optimizer.simulate import run
from tests.gen import SHAPES, make_case


class LayoutTests(unittest.TestCase):
    def test_every_shape_gives_a_full_valid_route(self):
        for shape in SHAPES:
            for seed in range(5):
                with self.subTest(shape=shape, seed=seed):
                    store, items = make_case(shape, 25, 25, 20, 12, seed)
                    order = optimized_route(store, items)
                    self.assertEqual(sorted(order), list(range(len(items))))
                    events = list(run(store, items, order))
                    picked = sorted(e.picked_id for e in events if e.kind == "pick")
                    self.assertEqual(picked, sorted(i.id for i in items))
                    self.assertEqual(events[-1].kind, "ready")
                    self.assertEqual(events[-1].cell, store.start)

    def test_very_big_store_within_time_limit(self):
        store, items = make_case("open", 300, 300, 200, 40, seed=1)
        began = time.monotonic()
        order = optimized_route(store, items)
        events = list(run(store, items, order))
        elapsed = time.monotonic() - began
        self.assertEqual(sorted(order), list(range(len(items))))
        self.assertEqual(events[-1].kind, "ready")
        self.assertLess(elapsed, 60, f"300x300 store took {elapsed:.1f} s")


if __name__ == "__main__":
    unittest.main()
