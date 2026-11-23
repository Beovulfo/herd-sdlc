import unittest

from supermarket_route.gen import generate_store, random_basket
from supermarket_route.layout import parse_list
from supermarket_route.planner import build_model, route
from supermarket_route.simulate import compare, kpis, simulate
from tests.support import steps_between

WALKABLE = ".E"


def check_route(tc, store, lines, mode):
    """Check one route against the map, using only the trace and an independent BFS."""
    model = build_model(store, parse_list(lines, store))
    n = len(model.items)
    order = route(model, mode)
    tc.assertEqual(sorted(order), list(range(1, n + 1)))
    steps = list(simulate(model, order))

    tc.assertEqual(steps[0]["event"], "start")
    tc.assertEqual((steps[0]["row"], steps[0]["col"]), store.entrance)
    for prev, cur in zip(steps, steps[1:]):
        if cur["event"] == "move":
            tc.assertEqual(abs(prev["row"] - cur["row"]) + abs(prev["col"] - cur["col"]), 1)
            tc.assertIn(store.grid[cur["row"]][cur["col"]], WALKABLE)

    picks = [s for s in steps if s["event"] == "pick"]
    tc.assertEqual([p["product_id"] for p in picks], [model.items[i - 1].id for i in order])
    for p in picks:
        product = store.products[p["product_id"]]
        tc.assertEqual(abs(p["row"] - product.row) + abs(p["col"] - product.col), 1)

    stops = [store.entrance] + [(p["row"], p["col"]) for p in picks]
    legs = [steps_between(store.grid, a, b) for a, b in zip(stops, stops[1:])]
    tc.assertNotIn(None, legs)
    moves = sum(1 for s in steps if s["event"] == "move")
    tc.assertEqual(moves, sum(legs))
    tc.assertEqual(kpis(steps), {
        "time_to_prepare_basket": moves * 1.0 + len(picks) * 3.0,
        "distance_covered": sum(legs),
    })


class LayoutTest(unittest.TestCase):
    def test_every_layout_shape_gives_valid_routes_no_longer_than_list_order(self):
        for shape in ("aisles", "open", "maze"):
            for seed in (1, 2, 3):
                with self.subTest(shape=shape, seed=seed):
                    store = generate_store(shape, width=31, height=23, seed=seed)
                    lines = random_basket(store, 10, seed)
                    for mode in ("list", "optimized"):
                        check_route(self, store, lines, mode)
                    model = build_model(store, parse_list(lines, store))
                    result = compare(model)
                    self.assertLessEqual(
                        result["optimized"]["distance_covered"],
                        result["list_order"]["distance_covered"],
                    )


if __name__ == "__main__":
    unittest.main()
