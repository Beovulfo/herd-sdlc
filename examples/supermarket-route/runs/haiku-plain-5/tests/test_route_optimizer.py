import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import route_optimizer as ro  # noqa: E402


class RouteTest(unittest.TestCase):
    def test_bfs_goes_around_wall(self):
        s = ro.Store({"grid": ["...", "##.", "..."], "entrance": [0, 0], "checkout": [0, 2], "products": []})
        dist, _ = ro.bfs(s, s.entrance)
        self.assertEqual(dist[s.checkout], 6)  # wall forces a detour via the gap at x=2

    def test_shelf_product_is_picked_from_aisle(self):
        s = ro.Store({"grid": ["...", ".#.", "..."], "entrance": [0, 0], "checkout": [2, 0],
                      "products": [{"id": "A", "name": "Milk", "x": 1, "y": 1}]})
        self.assertEqual(s.products["A"][1], 1 * 3 + 2)  # (2, 1) is the first open neighbour

    def test_optimized_route_is_shorter_and_simulation_matches(self):
        W, H = 16, 9
        grid = [["."] * W for _ in range(H)]
        for y in (2, 5):  # two shelf rows, open at both ends
            for x in range(1, W - 1):
                grid[y][x] = "#"
        rng = random.Random(7)
        shelves = [(x, y) for y in (2, 5) for x in range(1, W - 1)]
        picks = rng.sample(shelves, 12)
        products = [{"id": f"P{i}", "name": f"Item {i}", "x": x, "y": y} for i, (x, y) in enumerate(picks)]
        s = ro.Store({"grid": ["".join(r) for r in grid], "entrance": [0, H - 1],
                      "checkout": [W - 1, H - 1], "products": products})
        basket = [f"P{i}" for i in rng.sample(range(12), 8)]
        cells = [s.entrance] + [s.products[p][1] for p in basket] + [s.checkout]
        labels = [None] + basket + [None]
        trees = {c: ro.bfs(s, c) for c in set(cells)}

        def cost(tour):
            return sum(trees[cells[a]][0][cells[b]] for a, b in zip(tour, tour[1:]))

        base = list(range(len(cells)))
        opt = ro.order_stops(cells, trees)
        self.assertEqual(sorted(opt), base)
        self.assertLessEqual(cost(opt), cost(base))

        snaps = list(ro.simulate(s, trees, cells, labels, opt))
        final = snaps[-1]
        self.assertEqual(final["event"], "basket ready")
        self.assertEqual(final["picked"], len(basket))
        self.assertAlmostEqual(final["distance_m"], cost(opt) * ro.CELL_M)
        self.assertAlmostEqual(final["elapsed_s"],
                               cost(opt) * ro.CELL_M / ro.WALK_MPS + len(basket) * ro.PICK_S)


if __name__ == "__main__":
    unittest.main()
