import contextlib
import io
import os
import tempfile
import unittest

from optimizer.cli import main
from optimizer.plan import optimized_route
from optimizer.store import StoreError, load_store, parse_list, parse_store
from optimizer.simulate import kpis, run

# Row 0 is "S.#.": the product X at (0, 3) is walled off, A at (1, 1) is reachable.
MAP = {
    "layout": ["S.#.", "..##"],
    "products": [
        {"id": "A", "name": "milk", "row": 1, "col": 1},
        {"id": "X", "name": "ice", "row": 0, "col": 3},
    ],
}


def _run_cli(map_text, list_text):
    with tempfile.TemporaryDirectory() as d:
        map_path = os.path.join(d, "map.json")
        list_path = os.path.join(d, "list.txt")
        with open(map_path, "w") as f:
            f.write(map_text)
        with open(list_path, "w") as f:
            f.write(list_text)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["compare", map_path, list_path])
        return code, out.getvalue(), err.getvalue()


class InputTests(unittest.TestCase):
    def test_bad_inputs_give_one_error_line_and_exit_2(self):
        import json
        good = json.dumps(MAP)
        cases = {
            "malformed json": ("{not json", "A:milk\n"),
            "unknown map char": (json.dumps({"layout": ["Sx"], "products": []}), "A:milk\n"),
            "no start": (json.dumps({"layout": ["..", ".."], "products": []}), "A:milk\n"),
            "two starts": (json.dumps({"layout": ["SS"], "products": []}), "A:milk\n"),
            "product on wall": (json.dumps({"layout": ["S#"], "products": [
                {"id": "A", "name": "milk", "row": 0, "col": 1}]}), "A:milk\n"),
            "duplicate product id": (json.dumps({"layout": ["S."], "products": [
                {"id": "A", "name": "milk", "row": 0, "col": 1},
                {"id": "A", "name": "bread", "row": 0, "col": 0}]}), "A:milk\n"),
            "unknown list id": (good, "Z:nothing\n"),
            "list line without colon": (good, "A milk\n"),
            "empty list": (good, "\n"),
            "unreachable requested product": (good, "X:ice\n"),
        }
        for name, (map_text, list_text) in cases.items():
            with self.subTest(case=name):
                code, out, err = _run_cli(map_text, list_text)
                self.assertEqual(code, 2)
                self.assertTrue(err.startswith("error: "), err)
                self.assertNotIn("Traceback", err)
                self.assertEqual(err.count("\n"), 1)

    def test_missing_files_exit_2(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["compare", "/no/such/map.json", "/no/such/list.txt"])
        self.assertEqual(code, 2)
        self.assertIn("error:", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_unused_unreachable_product_does_not_block_the_plan(self):
        code, out, err = _run_cli(__import__("json").dumps(MAP), "A:milk\n")
        self.assertEqual(code, 0, err)

    def test_broken_unrequested_product_does_not_reject_the_map(self):
        # Regression: a wall product that the list does not ask for used to reject the whole map.
        data = {"layout": ["S.#", "..."], "products": [
            {"id": "A", "name": "milk", "row": 1, "col": 1},
            {"id": "W", "name": "wall", "row": 0, "col": 2}]}
        code, out, err = _run_cli(__import__("json").dumps(data), "A:milk\n")
        self.assertEqual(code, 0, err)

    def test_requested_broken_product_fails_with_its_reason(self):
        data = {"layout": ["S.#"], "products": [{"id": "W", "name": "wall", "row": 0, "col": 2}]}
        code, out, err = _run_cli(__import__("json").dumps(data), "W:wall\n")
        self.assertEqual(code, 2)
        self.assertIn("unusable in the map", err)
        self.assertIn("wall cell", err)

    def test_products_must_be_a_list(self):
        # Regression: a non-list 'products' raised a TypeError traceback.
        for value in (5, None, "A"):
            with self.subTest(products=value):
                code, out, err = _run_cli(__import__("json").dumps({"layout": ["S."], "products": value}), "A:milk\n")
                self.assertEqual(code, 2)
                self.assertTrue(err.startswith("error: "), err)
                self.assertNotIn("Traceback", err)

    def test_duplicate_list_entries_are_each_counted(self):
        store = parse_store(MAP)
        items = parse_list("A:milk\nA:milk\n", store)
        events = list(run(store, items, optimized_route(store, items)))
        self.assertEqual(kpis(events)["items_picked"], 2)

    def test_two_products_on_one_cell_are_each_counted(self):
        data = {"layout": ["S."], "products": [
            {"id": "A", "name": "milk", "row": 0, "col": 1},
            {"id": "B", "name": "bread", "row": 0, "col": 1}]}
        store = parse_store(data)
        items = parse_list("A:milk\nB:bread\n", store)
        events = list(run(store, items, optimized_route(store, items)))
        self.assertEqual(kpis(events)["items_picked"], 2)

    def test_store_error_is_raised_for_missing_map(self):
        with self.assertRaises(StoreError):
            load_store("/no/such/map.json")


if __name__ == "__main__":
    unittest.main()
