import contextlib
import io
import json
import os
import random
import tempfile
import unittest

from route_optimizer import PlanError, Store, compare, main, parse_basket, plan_optimized

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class EdgeTests(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "examples", "demo_store.json")) as f:
            self.store = Store.from_dict(json.load(f))

    def test_empty_list_gives_empty_route(self):
        route = plan_optimized(self.store, [])
        self.assertEqual(route.stops, ())
        self.assertEqual(route.distance, 0)
        self.assertEqual(route.time_s(), 0)

    def test_unknown_id_is_a_clear_error(self):
        with self.assertRaisesRegex(PlanError, "NOPE"):
            plan_optimized(self.store, ["P001", "NOPE"])

    def test_duplicate_id_is_rejected(self):
        with self.assertRaises(PlanError):
            plan_optimized(self.store, ["P001", "P001"])

    def test_parse_basket_takes_the_id_before_the_colon(self):
        self.assertEqual(parse_basket(["P001:milk\n", "\n", " P002 : bread "]), ["P001", "P002"])

    def run_cli(self, map_text, basket_text):
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for name, text in (("map.json", map_text), ("basket.txt", basket_text)):
                path = os.path.join(d, name)
                with open(path, "w") as f:
                    f.write(text)
                paths.append(path)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = main(["route_optimizer", *paths])
            return code, err.getvalue()

    def test_cli_bad_files_give_one_clear_message_and_exit_1(self):
        good = json.dumps({"grid": ["..."], "start": [0, 0], "products": []})
        for map_text in ("{bad", "[]", json.dumps({"grid": ["..."], "start": [0, 0], "products": 5})):
            code, err = self.run_cli(map_text, "")
            self.assertEqual(code, 1, map_text)
            self.assertTrue(err.startswith("error: "), err)
        code, err = self.run_cli(good, "NOPE:x\n")
        self.assertEqual(code, 1)
        self.assertIn("NOPE", err)

    def test_unrequested_unreachable_product_does_not_reject_the_basket(self):
        data = {"grid": ["..#", "##."], "start": [0, 0], "products": [
            {"id": "P1", "name": "x", "x": 1, "y": 0},
            {"id": "P2", "name": "y", "x": 2, "y": 1},
        ]}
        store = Store.from_dict(data)
        self.assertEqual(plan_optimized(store, ["P1"]).stops, ("P1",))
        with self.assertRaisesRegex(PlanError, "P2"):
            plan_optimized(store, ["P2"])

    def test_two_products_on_one_cell_are_both_counted(self):
        store = Store.from_dict({"grid": ["..."], "start": [0, 0], "products": [
            {"id": "A", "name": "milk", "x": 2, "y": 0},
            {"id": "B", "name": "milk", "x": 2, "y": 0},
        ]})
        route = plan_optimized(store, ["A", "B"])
        self.assertEqual(sorted(route.stops), ["A", "B"])
        self.assertEqual(route.distance, 2)


if __name__ == "__main__":
    unittest.main()
