import types
import unittest

from supermarket_route.layout import parse_list, parse_map
from supermarket_route.planner import build_model
from supermarket_route.simulate import kpis, simulate
from tests.support import HANDMADE, HANDMADE_LIST


class SimulationTest(unittest.TestCase):
    def setUp(self):
        store = parse_map(HANDMADE)
        self.model = build_model(store, parse_list(HANDMADE_LIST, store))

    def test_simulation_is_a_step_by_step_generator(self):
        self.assertIsInstance(simulate(self.model, [1, 2, 3]), types.GeneratorType)

    def test_list_order_trace_has_each_step_with_its_clock_and_distance(self):
        steps = list(simulate(self.model, [1, 2, 3], walk_seconds=1.0, pick_seconds=3.0))
        self.assertEqual(
            [s["event"] for s in steps],
            ["start", "move", "pick", "move", "move", "move", "pick", "move", "pick"],
        )
        self.assertEqual([s["t"] for s in steps], [0, 1, 4, 5, 6, 7, 10, 11, 14])
        self.assertEqual([s["distance_covered"] for s in steps], [0, 1, 1, 2, 3, 4, 4, 5, 5])
        picks = [s for s in steps if s["event"] == "pick"]
        self.assertEqual([p["product_id"] for p in picks], ["A1", "B2", "C3"])
        self.assertEqual([(p["row"], p["col"]) for p in picks], [(1, 2), (1, 5), (1, 4)])

    def test_final_kpis_match_a_recount_from_the_trace(self):
        steps = list(simulate(self.model, [1, 2, 3], walk_seconds=1.0, pick_seconds=3.0))
        moves = sum(1 for s in steps if s["event"] == "move")
        last_pick = max(s["t"] for s in steps if s["event"] == "pick")
        self.assertEqual(moves, 5)
        self.assertEqual(kpis(steps), {"time_to_prepare_basket": last_pick, "distance_covered": moves})
        self.assertEqual(kpis(steps), {"time_to_prepare_basket": 14, "distance_covered": 5})


if __name__ == "__main__":
    unittest.main()
