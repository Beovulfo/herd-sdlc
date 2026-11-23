import json
import os
import tempfile
import unittest

from tests.support import HANDMADE, HANDMADE_LIST, kpis_from_output, run_cli

# Product P9 sits behind a wall: its only neighbour (3, 3) cannot reach the entrance.
ENCLOSED = {
    "grid": ["#######", "#E....#", "#######", "###.###"],
    "products": [
        {"id": "A1", "short_name": "apples", "row": 0, "col": 2},
        {"id": "P9", "short_name": "lost", "row": 3, "col": 2},
    ],
}
# Two products on the same shelf cell: both must still be counted.
COLLIDING = {
    "grid": HANDMADE["grid"],
    "products": HANDMADE["products"][:1] + [
        {"id": "A2", "short_name": "pears", "row": 0, "col": 2},
    ],
}


class BadInputTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name

    def write(self, name, content):
        path = os.path.join(self.dir, name)
        with open(path, "w") as f:
            f.write(content if isinstance(content, str) else json.dumps(content))
        return path

    def run_with(self, map_content=HANDMADE, list_text=HANDMADE_LIST):
        return run_cli("--map", self.write("map.json", map_content),
                       "--list", self.write("list.txt", list_text))

    def assert_clean_error(self, result, expect=None):
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        lines = result.stderr.strip().splitlines()
        self.assertEqual(len(lines), 1, result.stderr)
        self.assertTrue(lines[0].startswith("error:"), lines[0])
        if expect:
            self.assertIn(expect, lines[0])

    def test_missing_files_fail_with_one_message(self):
        result = run_cli("--map", os.path.join(self.dir, "nope.json"),
                         "--list", self.write("list.txt", HANDMADE_LIST))
        self.assert_clean_error(result)
        result = run_cli("--map", self.write("map.json", HANDMADE),
                         "--list", os.path.join(self.dir, "nope.txt"))
        self.assert_clean_error(result)

    def test_malformed_maps_fail_with_one_message(self):
        bad_maps = {
            "not json": "{not json",
            "root not an object": "[]",
            "grid not a list": {"grid": "#####", "products": []},
            "no entrance": {"grid": ["#####", "#...#", "#####"], "products": []},
            "two entrances": {"grid": ["#####", "#EE.#", "#####"], "products": []},
            "ragged grid": {"grid": ["#####", "#E#", "#####"], "products": []},
            "products not a list": {"grid": HANDMADE["grid"], "products": {"A1": 1}},
            "product missing a field": {"grid": HANDMADE["grid"], "products": [{"id": "A1"}]},
            "product outside grid": {"grid": HANDMADE["grid"], "products": [
                {"id": "A1", "short_name": "apples", "row": 9, "col": 9}]},
        }
        for name, content in bad_maps.items():
            with self.subTest(name=name):
                self.assert_clean_error(self.run_with(map_content=content))

    def test_bad_lists_fail_with_one_message(self):
        self.assert_clean_error(self.run_with(list_text="ZZ9:nope\n"), expect="ZZ9")
        self.assert_clean_error(self.run_with(list_text="A1 apples\n"))
        self.assert_clean_error(self.run_with(list_text=""))

    def test_requested_unreachable_product_fails_with_its_id(self):
        self.assert_clean_error(self.run_with(map_content=ENCLOSED, list_text="P9:lost\n"), expect="P9")

    def test_unrequested_unreachable_product_does_not_reject_the_basket(self):
        result = self.run_with(map_content=ENCLOSED, list_text="A1:apples\n")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_duplicate_list_lines_are_each_counted(self):
        result = self.run_with(list_text="A1:apples\nA1:apples\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        # walk 1 step to (1, 2), then pick twice (3 s each): 1 + 3 + 3 = 7 s
        self.assertEqual(kpis_from_output(result.stdout, "list-order"), (7.0, 1))

    def test_colliding_products_on_one_cell_are_each_counted(self):
        result = self.run_with(map_content=COLLIDING, list_text="A1:apples\nA2:pears\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(kpis_from_output(result.stdout, "list-order"), (7.0, 1))


if __name__ == "__main__":
    unittest.main()
