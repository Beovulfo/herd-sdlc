"""C4: step-by-step simulation of the walk, with live KPIs that match a separate recount."""
import json
import os
import random
import re
import tempfile
import unittest

from route_optimizer import CELL_M, PICK_S, WALK_M_PER_S, make_store, parse_store, plan_route, simulate
from tests.support import run_cli


class SimulationTest(unittest.TestCase):
    def test_steps_are_adjacent_walkable_cells_and_kpis_recount(self):
        store = parse_store(make_store(50, 40, 120, seed=5))
        ids = random.Random(5).sample(list(store.products), 15)
        plan = plan_route(store, ids, "optimized")
        steps = list(simulate(plan))

        # recount from the trace alone, without the planner's distance table
        prev, walked, picks, seconds, last_time, last_dist = None, 0, 0, 0.0, 0.0, 0.0
        for s in steps:
            self.assertTrue(store.walkable(s.cell))
            if prev is not None:
                self.assertLessEqual(abs(s.cell[0] - prev[0]) + abs(s.cell[1] - prev[1]), 1)
            if s.kind == "walk":
                walked += 1
                seconds += CELL_M / WALK_M_PER_S
                self.assertEqual(s.distance_m, walked * CELL_M)
            elif s.kind == "pick":
                picks += 1
                seconds += PICK_S
                self.assertEqual(s.picked, picks)
            self.assertGreaterEqual(s.seconds, last_time - 1e-9)
            self.assertGreaterEqual(s.distance_m, last_dist - 1e-9)
            self.assertAlmostEqual(s.seconds, seconds, places=6)
            last_time, last_dist, prev = s.seconds, s.distance_m, s.cell

        kpis = plan.kpis()
        self.assertEqual(picks, len(ids))
        self.assertAlmostEqual(kpis["distance_covered_m"], walked * CELL_M)
        self.assertAlmostEqual(kpis["time_to_prepare_s"], seconds, places=6)

    def test_cli_run_prints_live_kpis_matching_the_plan(self):
        data = make_store(30, 20, 15, seed=2)
        store = parse_store(data)
        ids = random.Random(2).sample(list(store.products), 6)
        expected = plan_route(store, ids, "optimized").kpis()
        with tempfile.TemporaryDirectory() as d:
            mp, bp = os.path.join(d, "m.json"), os.path.join(d, "b.txt")
            with open(mp, "w") as f:
                json.dump(data, f)
            with open(bp, "w") as f:
                f.write("".join(f"{i}:name\n" for i in ids))
            proc = run_cli("run", mp, bp)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = proc.stdout.strip().splitlines()
        self.assertGreater(len(lines), 2)  # one line per step
        m = re.search(r"time-to-prepare-basket: ([\d.]+) s; distance-covered: ([\d.]+) m", lines[-1])
        self.assertIsNotNone(m, lines[-1])
        self.assertAlmostEqual(float(m.group(1)), expected["time_to_prepare_s"], places=1)
        self.assertAlmostEqual(float(m.group(2)), expected["distance_covered_m"], places=1)


if __name__ == "__main__":
    unittest.main()
