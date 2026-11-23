import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from route_optimizer import main, plan_route, simulate
from tests.support import sample_case


class SimulationTest(unittest.TestCase):
    def setUp(self):
        data, self.store, self.items = sample_case("aisles", 3, 40, 30, 15)
        self.plan = plan_route(self.store, self.items)
        self.events = list(simulate(self.store, self.plan))

    def test_one_event_per_step_with_both_kpis_growing(self):
        self.assertEqual(len(self.events), len(self.plan.steps))
        for event, step in zip(self.events, self.plan.steps):
            self.assertEqual(event["action"], step.kind)
        for key in ("distance_m", "time_s"):
            values = [event[key] for event in self.events]
            self.assertEqual(values, sorted(values), key)

    def test_final_kpis_equal_the_planned_route(self):
        last = self.events[-1]
        self.assertEqual(last["distance_m"], self.plan.distance_m)
        self.assertEqual(last["time_s"], self.plan.time_s)

    def test_picks_happen_in_plan_order(self):
        picks = [event["item"] for event in self.events if event["action"] == "pick"]
        self.assertEqual(picks, self.plan.order)

    def test_cli_prints_both_routes_step_by_step_with_kpis(self):
        with tempfile.TemporaryDirectory() as tmp:
            map_path = Path(tmp) / "map.json"
            list_path = Path(tmp) / "list.txt"
            map_path.write_text(json.dumps(_map_of(self.store, self.items)))
            list_path.write_text("\n".join(f"{pid}:{name}" for pid, name in self.items))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main([str(map_path), str(list_path)])
        text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("== list-order route", text)
        self.assertIn("== optimized route", text)
        self.assertIn("time-to-prepare-basket", text)
        self.assertIn("distance-covered", text)
        self.assertIn("saving", text)
        self.assertGreaterEqual(text.count("time-to-prepare-basket"), 2 * len(self.plan.steps))


def _map_of(store, items):
    """Rebuild the map JSON from the store, so the CLI test reads a real file."""
    rows = []
    for y in range(store.height):
        rows.append("".join("." if store.open[y * store.width + x] else "#" for x in range(store.width)))
    products = [
        {"id": p.id, "short": p.name, "x": p.x, "y": p.y} for p in store.products.values()
    ]
    start = store.start
    return {"layout": rows, "start": [start % store.width, start // store.width], "products": products}


if __name__ == "__main__":
    unittest.main()
