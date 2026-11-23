import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import make_store  # noqa: E402
import route_optimizer as ro  # noqa: E402


def tiny_store(grid, products, entrance=(0, 0), checkout=None):
    checkout = checkout or (len(grid) - 1, len(grid[0]) - 1)
    return ro.Store(tuple(grid), 1.0, entrance, checkout,
                    {p[0]: ro.Product(p[0], p[1], p[2]) for p in products})


class RouteOptimizerTests(unittest.TestCase):
    def test_bfs_detours_around_wall(self):
        store = tiny_store([".#.", ".#.", "..."], [])
        dist, _ = ro.bfs(store, (0, 0), [(0, 2)])
        self.assertEqual(dist[(0, 2)], 6)  # must go down and around the wall

    def test_unreachable_target_raises(self):
        store = tiny_store([".#.", ".#."], [])
        with self.assertRaises(ValueError):
            ro.bfs(store, (0, 0), [(0, 2)])

    def test_two_opt_never_longer_than_nearest_neighbour(self):
        rng = random.Random(3)
        d = [[0] * 9 for _ in range(9)]
        for i in range(9):
            for j in range(i + 1, 9):
                d[i][j] = d[j][i] = rng.randint(1, 50)
        seq = ro.nearest_neighbour(d, 0, 8, list(range(1, 8)))
        length = lambda s: sum(d[a][b] for a, b in zip(s, s[1:]))  # noqa: E731
        improved = ro.two_opt(d, list(seq))
        self.assertLessEqual(length(improved), length(seq))
        self.assertEqual(improved[0], 0)
        self.assertEqual(improved[-1], 8)

    def test_simulation_matches_planned_distance_and_time(self):
        store_dict = make_store.build(30, 40, 30, seed=2)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "store.json"
            path.write_text(json.dumps(store_dict))
            store = ro.load_store(path)
        ids = sorted(store.products)[:6]
        order = ro.optimized_order(store, ids)
        cells = [store.entrance] + [store.products[p].cell for p in order] + [store.checkout]
        planned = sum(ro.bfs(store, a, [b])[0][b] for a, b in zip(cells, cells[1:]))
        result = ro.run(store, order, walk=1.2, pick=5.0)
        self.assertAlmostEqual(result.distance_m, planned * store.cell_size_m)
        self.assertAlmostEqual(result.time_s, planned / 1.2 + 5.0 * len(order))

    def test_optimized_is_not_slower_than_list_order(self):
        store = ro.load_store(self._store_file())
        rng = random.Random(11)
        for _ in range(3):
            ids = rng.sample(sorted(store.products), 10)
            base, opt = ro.compare(store, ids, 1.2, 5.0)
            self.assertLessEqual(opt.time_s, base.time_s + 1e-9)

    def _store_file(self):
        if not hasattr(self, "_path"):
            self._tmp = tempfile.TemporaryDirectory()
            self._path = Path(self._tmp.name) / "store.json"
            self._path.write_text(json.dumps(make_store.build(60, 80, 120, seed=5)))
            self.addCleanup(self._tmp.cleanup)
        return self._path


if __name__ == "__main__":
    unittest.main()
