import itertools
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import route_optimizer as ro  # noqa: E402


def path_length(D, order):
    return sum(D[a][b] for a, b in zip(order, order[1:]))


class RouteOptimizerTests(unittest.TestCase):
    def test_bfs_walks_around_walls(self):
        store = ro.Store({"layout": ["....", ".##.", "...."], "entrance": [0, 0],
                          "products": []})
        dist, _ = ro.bfs(store, (0, 0))
        self.assertEqual(dist[(3, 0)], 3)
        self.assertEqual(dist[(0, 1)], 1)
        self.assertNotIn((1, 1), dist)  # blocked cells are never visited
        self.assertNotIn((2, 1), dist)

    def test_held_karp_matches_brute_force(self):
        rng = random.Random(3)
        pts = [(rng.randint(0, 30), rng.randint(0, 30)) for _ in range(7)]
        D = [[abs(a[0] - b[0]) + abs(a[1] - b[1]) for b in pts] for a in pts]
        best = min(path_length(D, (0,) + p + (6,))
                   for p in itertools.permutations(range(1, 6)))
        self.assertEqual(path_length(D, ro.held_karp(D)), best)

    def test_two_opt_never_worse_than_nearest_neighbour(self):
        rng = random.Random(5)
        pts = [(rng.randint(0, 80), rng.randint(0, 80)) for _ in range(30)]
        D = [[abs(a[0] - b[0]) + abs(a[1] - b[1]) for b in pts] for a in pts]
        order = ro.nearest_neighbour_2opt(D)
        self.assertEqual(order[0], 0)
        self.assertEqual(order[-1], len(pts) - 1)
        self.assertEqual(sorted(order), list(range(len(pts))))
        greedy = [0] + list(range(1, 29)) + [29]
        self.assertLessEqual(path_length(D, order), path_length(D, greedy))

    def test_simulated_distance_equals_planned_distance(self):
        store = ro.Store(ro.gen_store(40, 24, 60, seed=2))
        pids = list(store.products)[:12]
        base, opt = ro.plan(store, pids)
        cells = [c for c, _ in base]
        D = ro.distance_matrix(store, cells)
        final = ro.run_route(store, base)
        self.assertEqual(final["distance_m"], path_length(D, range(len(cells))) * store.cell_m)
        self.assertEqual(final["picked"], 12)
        final_opt = ro.run_route(store, opt)
        self.assertLessEqual(final_opt["t_s"], final["t_s"] + 1e-6)
        self.assertEqual(final_opt["picked"], 12)


if __name__ == "__main__":
    unittest.main()
