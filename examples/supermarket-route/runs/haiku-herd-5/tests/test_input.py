"""C2: map with localised products and a basket of id:short name lines; bad files fail cleanly."""
import json
import os
import tempfile
import unittest

from route_optimizer import RouteError, load_basket, load_store, plan_route
from tests.support import ROOT, run_cli

GOOD_MAP = {
    "grid": ["#####", "#...#", "#.#.#", "#...#", "#####"],
    "entrance": {"x": 1, "y": 1},
    "products": [{"id": "P1", "name": "milk", "x": 3, "y": 1}, {"id": "P2", "name": "bread", "x": 1, "y": 3}],
}


class InputTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def write(self, name, content):
        path = os.path.join(self.dir.name, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content if isinstance(content, str) else json.dumps(content))
        return path

    def test_valid_map_and_basket_load(self):
        store = load_store(self.write("map.json", GOOD_MAP))
        self.assertEqual(store.products["P1"], ((3, 1), "milk"))
        self.assertEqual(load_basket(self.write("b.txt", "P1:milk\nP2:bread\n")), ["P1", "P2"])

    def test_bad_store_maps_fail_with_clear_message(self):
        bad = {
            "uneven rows": dict(GOOD_MAP, grid=["#####", "#..#", "#####", "#...#", "#####"]),
            "bad character": dict(GOOD_MAP, grid=["#####", "#.x.#", "#.#.#", "#...#", "#####"]),
            "entrance on wall": dict(GOOD_MAP, entrance={"x": 0, "y": 0}),
            "entrance missing": {k: v for k, v in GOOD_MAP.items() if k != "entrance"},
            "not json": "{ nope",
            "not object": [1, 2],
        }
        for label, data in bad.items():
            with self.subTest(label):
                path = self.write("bad.json", data)
                with self.assertRaises(RouteError):
                    load_store(path)

    def test_broken_product_entries_fail_only_the_basket_that_asks_for_them(self):
        broken = dict(GOOD_MAP, products=GOOD_MAP["products"] + [
            {"id": "W1", "name": "wall", "x": 2, "y": 2},          # on a wall
            {"id": "N1", "x": 3, "y": 3},                          # no short name
            {"id": "P1", "name": "dup", "x": 1, "y": 1},           # duplicate id
        ])
        store = load_store(self.write("map.json", broken))
        self.assertEqual(sorted(store.products), ["P2"])
        for pid in ("W1", "N1", "P1"):
            with self.subTest(pid):
                with self.assertRaises(RouteError) as ctx:
                    plan_route(store, [pid], "optimized")
                self.assertIn(f"basket product {pid} is broken", str(ctx.exception))
        self.assertEqual(sum(plan_route(store, ["P2"], "optimized").picks), 1)

    def test_bad_basket_lines_fail(self):
        for content in ("P1 milk\n", ":milk\n", "\n\n", ""):
            with self.subTest(content=content):
                with self.assertRaises(RouteError):
                    load_basket(self.write("b.txt", content))

    def test_missing_files_fail(self):
        with self.assertRaises(RouteError):
            load_store(os.path.join(self.dir.name, "nope.json"))
        with self.assertRaises(RouteError):
            load_basket(os.path.join(self.dir.name, "nope.txt"))

    def test_cli_bad_input_exits_2_without_traceback(self):
        map_path = self.write("map.json", GOOD_MAP)
        cases = [
            (os.path.join(self.dir.name, "missing.json"), self.write("b.txt", "P1:milk\n")),
            (self.write("junk.json", "{"), self.write("b.txt", "P1:milk\n")),
            (map_path, self.write("empty.txt", "")),
            (map_path, self.write("malformed.txt", "P1 milk\n")),
            (map_path, self.write("unknown.txt", "ZZ:nothing\n")),
            (map_path, self.write("blankid.txt", ":milk\n")),
        ]
        for store_path, basket_path in cases:
            with self.subTest(basket=basket_path, store=store_path):
                proc = run_cli("compare", store_path, basket_path)
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertTrue(proc.stderr.startswith("error: "), proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main()
