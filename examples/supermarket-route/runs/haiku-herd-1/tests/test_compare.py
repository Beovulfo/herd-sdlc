import json
import os
import tempfile
import unittest

from supermarket_route.layout import parse_list, parse_map
from supermarket_route.planner import build_model
from supermarket_route.simulate import compare
from tests.support import HANDMADE, HANDMADE_LIST, kpis_from_output, run_cli


class CompareTest(unittest.TestCase):
    def test_compare_reports_both_routes_for_the_same_basket(self):
        store = parse_map(HANDMADE)
        model = build_model(store, parse_list(HANDMADE_LIST, store))
        result = compare(model, walk_seconds=1.0, pick_seconds=3.0)
        self.assertEqual(result["list_order"], {"time_to_prepare_basket": 14, "distance_covered": 5})
        self.assertEqual(result["optimized"], {"time_to_prepare_basket": 13, "distance_covered": 4})
        self.assertAlmostEqual(result["saving_pct"], 100.0 / 14, places=6)

    def test_cli_compare_prints_list_order_and_optimized_kpis(self):
        with tempfile.TemporaryDirectory() as tmp:
            map_path = os.path.join(tmp, "map.json")
            list_path = os.path.join(tmp, "list.txt")
            with open(map_path, "w") as f:
                json.dump(HANDMADE, f)
            with open(list_path, "w") as f:
                f.write(HANDMADE_LIST)
            result = run_cli("--map", map_path, "--list", list_path, "--mode", "compare")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(kpis_from_output(result.stdout, "list-order"), (14.0, 5))
        self.assertEqual(kpis_from_output(result.stdout, "optimized"), (13.0, 4))
        self.assertIn("7.1%", result.stdout)


if __name__ == "__main__":
    unittest.main()
