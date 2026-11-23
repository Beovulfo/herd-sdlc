import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from route_optimizer import RouteError, load_store, main, parse_list, plan_route
from tests.support import assert_valid_route

MAP = {
    "layout": ["......", ".##.#.", "......", ".#.##.", "......"],
    "start": [0, 0],
    "products": [
        {"id": "P1", "short": "milk", "x": 1, "y": 1},
        {"id": "P2", "short": "bread", "x": 4, "y": 1},
        {"id": "P3", "short": "eggs", "x": 2, "y": 3},
    ],
}

# The product P9 at (2, 1) opens onto a pocket of floor that the counter at (0, 4) cannot reach.
BOXED = {
    "layout": ["..#..", "..#..", "#####", ".....", "....."],
    "start": [0, 4],
    "products": [{"id": "P9", "short": "jam", "x": 2, "y": 1}],
}


class InputTest(unittest.TestCase):
    def test_map_and_list_are_read_and_every_product_is_planned(self):
        store = load_store(MAP)
        items = parse_list("P1:milk\nP3:eggs\n# comment\n\nP2:bread\n")
        self.assertEqual(items, [("P1", "milk"), ("P3", "eggs"), ("P2", "bread")])
        assert_valid_route(self, store, plan_route(store, items), items)

    def test_unknown_product_id_fails(self):
        store = load_store(MAP)
        with self.assertRaisesRegex(RouteError, "unknown product id P9"):
            plan_route(store, [("P9", "jam")])

    def test_short_name_must_match_the_map(self):
        store = load_store(MAP)
        with self.assertRaisesRegex(RouteError, "P1 is 'milk' in the map, not 'bread'"):
            plan_route(store, [("P1", "bread")])

    def test_wall_start_fails(self):
        with self.assertRaisesRegex(RouteError, "start must be a floor cell"):
            load_store(dict(MAP, start=[1, 1]))

    def test_unreachable_product_fails(self):
        store = load_store(BOXED)
        with self.assertRaisesRegex(RouteError, "P9 cannot be reached"):
            plan_route(store, [("P9", "jam")])

    def test_malformed_list_line_fails(self):
        with self.assertRaisesRegex(RouteError, "expected id:short name"):
            parse_list("P1 milk")

    def test_empty_list_fails(self):
        with self.assertRaisesRegex(RouteError, "no products"):
            parse_list("\n# only a comment\n")

    def test_map_missing_a_key_names_the_key(self):
        with self.assertRaisesRegex(RouteError, "missing key 'start'"):
            load_store({"layout": ["..."], "products": []})


class CliBadInputTest(unittest.TestCase):
    """Each bad file ends with one clear message and exit code 2, never a traceback."""

    def run_cli(self, map_text, list_text):
        """Write the files that are given; a None text leaves that file missing."""
        with tempfile.TemporaryDirectory() as tmp:
            map_path, list_path = Path(tmp) / "map.json", Path(tmp) / "list.txt"
            if map_text is not None:
                map_path.write_text(map_text)
            if list_text is not None:
                list_path.write_text(list_text)
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                code = main([str(map_path), str(list_path)])
        return code, err.getvalue()

    def assert_clean_failure(self, code, err):
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("error: "), err)
        self.assertNotIn("Traceback", err)

    def test_missing_map_file(self):
        self.assert_clean_failure(*self.run_cli(None, "P1:milk\n"))

    def test_malformed_json_map(self):
        self.assert_clean_failure(*self.run_cli("{not json", "P1:milk\n"))

    def test_missing_list_file(self):
        self.assert_clean_failure(*self.run_cli(json.dumps(MAP), None))

    def test_empty_list(self):
        code, err = self.run_cli(json.dumps(MAP), "\n# only a comment\n")
        self.assert_clean_failure(code, err)
        self.assertIn("no products", err)

    def test_map_missing_a_key(self):
        code, err = self.run_cli(json.dumps({"layout": ["..."], "products": []}), "P1:milk\n")
        self.assert_clean_failure(code, err)
        self.assertIn("missing key 'start'", err)


if __name__ == "__main__":
    unittest.main()
