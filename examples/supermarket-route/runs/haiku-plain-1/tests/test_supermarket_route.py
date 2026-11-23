import os
import random
import tempfile
import unittest

from supermarket_route import (
    _bfs, _path, distance_matrix, cycle_cost, load_list, load_map, main, plan, saving_pct, simulate,
)

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SAMPLE_MAP = os.path.join(ROOT, "examples", "sample_map.json")
SAMPLE_LIST = os.path.join(ROOT, "examples", "sample_list.txt")


class RouteTest(unittest.TestCase):
    def test_bfs_goes_around_a_wall(self):
        grid = ["...", ".#.", "..."]
        _, parent = _bfs(grid, (0, 1), {(2, 1)})
        path = _path(parent, (2, 1))
        self.assertEqual(len(path) - 1, 4)  # must detour around the wall, not cut through it

    def test_unreachable_product_is_an_error(self):
        grid = ["E#.", "##."]
        with self.assertRaises(ValueError):
            distance_matrix(grid, [(0, 0), (2, 0)], ["ENTRANCE", "P1 Milk"])

    def test_plan_never_longer_than_list_order_on_random_maps(self):
        rng = random.Random(1)
        for _ in range(20):
            n = rng.randint(2, 12)
            pts = [(rng.randint(0, 30), rng.randint(0, 30)) for _ in range(n)]
            grid = ["." * 31 for _ in range(31)]
            grid = [list(r) for r in grid]
            for x in range(10, 20):
                grid[15][x] = "#"
            grid = ["".join(r) for r in grid]
            pts = [p for p in pts if grid[p[1]][p[0]] != "#"] or [(0, 0)]
            stops = [(0, 0)] + pts
            d = distance_matrix(grid, stops, [str(i) for i in range(len(stops))])
            self.assertLessEqual(cycle_cost(plan(d), d), cycle_cost(list(range(len(stops))), d))

    def test_unknown_product_in_list_is_rejected(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("NOPE:Ghost\n")
        try:
            with self.assertRaises(ValueError):
                load_list(f.name, {"P1": ("Milk", (1, 1))})
        finally:
            os.unlink(f.name)

    def test_sample_demo_meets_thirty_percent_target(self):
        grid, entrance, products = load_map(SAMPLE_MAP)
        picks = load_list(SAMPLE_LIST, products)
        stops = [entrance] + [products[p][1] for p in picks]
        labels = ["ENTRANCE"] + picks
        d = distance_matrix(grid, stops, labels)
        base = simulate(grid, stops, labels, list(range(len(stops))), 1.2, 5.0)
        opt = simulate(grid, stops, labels, plan(d), 1.2, 5.0)
        self.assertEqual(base["picked"], len(picks))
        self.assertAlmostEqual(opt["distance_m"], cycle_cost(plan(d), d))
        self.assertGreater(saving_pct(base["time_s"], opt["time_s"]), 30.0)

    def test_cli_runs_on_sample(self):
        self.assertEqual(main(["--map", SAMPLE_MAP, "--list", SAMPLE_LIST]), 0)


if __name__ == "__main__":
    unittest.main()
