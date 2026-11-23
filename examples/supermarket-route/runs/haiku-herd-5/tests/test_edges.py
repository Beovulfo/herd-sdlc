"""C6: unreachable basket items fail with one clear message; unrequested unreachable products do not block."""
import json
import os
import tempfile
import unittest

from route_optimizer import RouteError, plan_route
from tests.support import run_cli, store_from

# (3, 3) is walkable but enclosed by shelves, so nothing can walk there.
ENCLOSED = [
    "#######",
    "#.....#",
    "#.###.#",
    "#.#.#.#",
    "#.###.#",
    "#.....#",
    "#######",
]


class EdgeTest(unittest.TestCase):
    def test_unreachable_basket_item_fails_clearly(self):
        store = store_from(ENCLOSED, (1, 1), [("A", "a", 5, 5), ("X", "x", 3, 3)])
        with self.assertRaises(RouteError) as ctx:
            plan_route(store, ["A", "X"], "optimized")
        self.assertIn("X", str(ctx.exception))
        self.assertIn("cannot be reached", str(ctx.exception))

    def test_unrequested_unreachable_product_does_not_block(self):
        store = store_from(ENCLOSED, (1, 1), [("A", "a", 5, 5), ("X", "x", 3, 3)])
        plan = plan_route(store, ["A"], "optimized")
        self.assertEqual(sum(plan.picks), 1)

    def test_cli_unreachable_item_exits_2(self):
        data = {"grid": ENCLOSED, "entrance": {"x": 1, "y": 1},
                "products": [{"id": "A", "name": "a", "x": 5, "y": 5}, {"id": "X", "name": "x", "x": 3, "y": 3}]}
        with tempfile.TemporaryDirectory() as d:
            mp, bp = os.path.join(d, "m.json"), os.path.join(d, "b.txt")
            with open(mp, "w") as f:
                json.dump(data, f)
            with open(bp, "w") as f:
                f.write("A:a\nX:x\n")
            proc = run_cli("compare", mp, bp)
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stderr.startswith("error: product X"), proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main()
