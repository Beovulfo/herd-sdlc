import json
import os
import subprocess
import sys
import tempfile
import unittest

import route_optimizer as ro

HERE = os.path.dirname(os.path.abspath(__file__))


def write_inputs(store_data, basket_ids):
    shorts = {p["id"]: p["short"] for p in store_data["products"]}
    d = tempfile.mkdtemp()
    map_path = os.path.join(d, "map.json")
    basket_path = os.path.join(d, "basket.txt")
    with open(map_path, "w") as f:
        json.dump(store_data, f)
    with open(basket_path, "w") as f:
        f.write("\n".join(f"{pid}:{shorts.get(pid, 'ghost')}" for pid in basket_ids))
    return map_path, basket_path


def run_cli(*args):
    return subprocess.run([sys.executable, os.path.join(HERE, "route_optimizer.py"), *args],
                          capture_output=True, text=True, cwd=HERE)


class TestSimulation(unittest.TestCase):
    def setUp(self):
        self.store = ro.Store(ro.demo_store())
        self.ids = ro.demo_basket(1)

    def test_steps_are_monotonic_and_end_at_checkout(self):
        events = list(ro.simulate(self.store, self.ids, "optimized"))
        self.assertEqual(len(events), len(self.ids) + 1)
        dists = [e["distance_covered"] for e in events]
        times = [e["time_to_prepare_s"] for e in events]
        self.assertEqual(dists, sorted(dists))
        self.assertEqual(times, sorted(times))
        self.assertEqual(events[-1]["stop"], "checkout")
        visited = [e["stop"] for e in events[:-1]]
        self.assertEqual(sorted(visited), sorted(self.store.products[p][0] for p in self.ids))

    def test_every_event_has_both_kpis(self):
        for e in ro.simulate(self.store, self.ids, "list-order"):
            self.assertIn("distance_covered", e)
            self.assertIn("time_to_prepare_s", e)

    def test_cli_simulate_prints_one_line_per_step(self):
        map_path, basket_path = write_inputs(ro.demo_store(), self.ids)
        r = run_cli("simulate", map_path, basket_path)
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = [ln for ln in r.stdout.splitlines() if ln.startswith("step")]
        self.assertEqual(len(lines), len(self.ids) + 1)
        self.assertIn("distance", lines[0])
        self.assertIn("time", lines[0])


class TestCompare(unittest.TestCase):
    def setUp(self):
        self.store = ro.Store(ro.demo_store())
        self.ids = ro.demo_basket(1)

    def test_both_routes_pick_the_same_items(self):
        res = ro.compare(self.store, self.ids)
        for name in ("list-order", "optimized"):
            self.assertEqual(len(res[name]["order"]), len(self.ids))
            self.assertEqual(sorted(res[name]["order"]), sorted(self.ids))

    def test_optimized_is_never_longer_than_list_order(self):
        res = ro.compare(self.store, self.ids)
        self.assertLessEqual(res["optimized"]["distance_covered"], res["list-order"]["distance_covered"])

    def test_cli_compare_prints_both_routes_and_saving(self):
        map_path, basket_path = write_inputs(ro.demo_store(), self.ids)
        r = run_cli("compare", map_path, basket_path)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("list-order", r.stdout)
        self.assertIn("optimized", r.stdout)
        self.assertIn("saving", r.stdout)


class TestSavings(unittest.TestCase):
    def test_aggregate_saving_over_thirty_percent(self):
        store = ro.Store(ro.demo_store())
        base_total = opt_total = 0.0
        for seed in range(1, 31):
            res = ro.compare(store, ro.demo_basket(seed))
            base_total += res["list-order"]["time_to_prepare_s"]
            opt_total += res["optimized"]["time_to_prepare_s"]
        saving = 1 - opt_total / base_total
        print(f"\nsaving over 30 baskets: {saving:.1%}")
        self.assertGreater(saving, 0.30, f"time-to-prepare saving {saving:.1%} is not above 30%")


class TestEdges(unittest.TestCase):
    def setUp(self):
        self.data = ro.demo_store()
        self.store = ro.Store(self.data)

    def test_unknown_product_is_rejected(self):
        with self.assertRaises(ValueError):
            ro.compare(self.store, ["P99"])

    def test_duplicate_product_is_rejected(self):
        with self.assertRaises(ValueError):
            ro.compare(self.store, ["P01", "P01"])

    def test_product_on_shelf_cell_is_rejected(self):
        data = ro.demo_store()
        data["products"].append({"id": "PX", "short": "bad", "x": 5, "y": 2})  # y=2 is a shelf row
        with self.assertRaises(ValueError):
            ro.compare(ro.Store(data), ["PX"])

    def test_cli_unknown_product_exits_1_without_route(self):
        map_path, basket_path = write_inputs(ro.demo_store(), ["P01"])
        with open(basket_path, "w") as f:
            f.write("P99:ghost")
        r = run_cli("simulate", map_path, basket_path)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout.strip(), "")
        self.assertIn("error", r.stderr)

    def test_empty_basket_only_walks_to_checkout(self):
        events = list(ro.simulate(self.store, [], "optimized"))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["stop"], "checkout")
        self.assertGreater(events[0]["distance_covered"], 0)


if __name__ == "__main__":
    unittest.main()
