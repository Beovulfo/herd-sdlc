import contextlib
import io
import os
import tempfile
import unittest

from optimizer.cli import main
from optimizer.plan import distance_matrix, list_order_route, optimized_route, tour_cost
from optimizer.simulate import PICK_SECONDS, STEP_SECONDS, compare, kpis, run
from tests.gen import make_case, make_map
import random


class SimulateTests(unittest.TestCase):
    def setUp(self):
        self.store, self.items = make_case("maze", 21, 21, 30, 8, seed=3)
        self.order = optimized_route(self.store, self.items)
        self.events = list(run(self.store, self.items, self.order))

    def test_each_move_is_one_free_adjacent_cell(self):
        for prev, e in zip([None] + self.events, self.events):
            if e.kind != "move":
                continue
            before = prev.cell if prev else self.store.start
            self.assertEqual(abs(before[0] - e.cell[0]) + abs(before[1] - e.cell[1]), 1)
            self.assertTrue(self.store.free[self.store.index(e.cell)])

    def test_kpis_update_at_every_event_and_never_decrease(self):
        last = (0.0, 0, 0)
        for e in self.events:
            current = (e.time_s, e.distance, e.picked_count)
            self.assertTrue(all(a <= b for a, b in zip(last, current)))
            last = current

    def test_basket_ready_back_at_start_with_every_item(self):
        self.assertEqual(self.events[-1].kind, "ready")
        self.assertEqual(self.events[-1].cell, self.store.start)
        picked = sorted(e.picked_id for e in self.events if e.kind == "pick")
        self.assertEqual(picked, sorted(i.id for i in self.items))

    def test_recount_kpis_from_the_trace(self):
        # Separate code: rebuild the KPIs from the trace alone, without kpis().
        moves = sum(1 for e in self.events if e.kind == "move")
        picks = sum(1 for e in self.events if e.kind == "pick")
        final = self.events[-1]
        self.assertEqual(final.distance, moves)
        self.assertEqual(final.picked_count, picks)
        self.assertAlmostEqual(final.time_s, moves * STEP_SECONDS + picks * PICK_SECONDS)
        self.assertEqual(kpis(self.events)["distance_steps"], moves)
        self.assertAlmostEqual(kpis(self.events)["time_to_prepare_basket_s"], final.time_s)

    def test_distance_matches_planned_tour_cost(self):
        D = distance_matrix(self.store, self.items)
        for order in (list_order_route(self.items), self.order):
            events = list(run(self.store, self.items, order))
            self.assertEqual(kpis(events)["distance_steps"], tour_cost(D, order))

    def test_cli_run_streams_steps_and_compare_prints_saving(self):
        with tempfile.TemporaryDirectory() as d:
            map_path = os.path.join(d, "map.json")
            list_path = os.path.join(d, "list.txt")
            import json
            rng = random.Random(3)
            with open(map_path, "w") as f:
                json.dump(make_map("open", 15, 15, 20, rng), f)
            with open(list_path, "w") as f:
                f.write("P000:item0\nP001:item1\nP002:item2\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["run", map_path, list_path, "--route", "list"]), 0)
            self.assertIn("ready", out.getvalue())
            self.assertIn("time_s=", out.getvalue())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["compare", map_path, list_path]), 0)
            self.assertIn("saving", out.getvalue())

    def test_compare_reports_both_routes(self):
        result = compare(self.store, self.items)
        self.assertIn("saving_pct", result)
        for name in ("list", "optimized"):
            self.assertGreater(result[name]["distance_steps"], 0)


if __name__ == "__main__":
    unittest.main()
