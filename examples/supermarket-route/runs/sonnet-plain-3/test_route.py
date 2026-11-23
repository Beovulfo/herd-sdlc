import random, unittest
import route


class T(unittest.TestCase):
    def test_saves_over_30pct_on_big_stores(self):
        for seed, aisles, length, k in [(1, 12, 60, 25), (2, 30, 120, 40), (3, 8, 30, 15)]:
            m = route.gen(aisles, length, seed)
            items = random.Random(seed).sample(m["products"], k)
            nodes, D = route.build(m, items)
            ev = list(route.simulate(m, items, route.optimize(D), nodes))
            base = list(route.simulate(m, items, list(range(len(nodes))), nodes))
            self.assertEqual(sum(1 for e in ev if e[4]), k)   # every item picked
            self.assertGreater(1 - ev[-1][3] / base[-1][3], 0.30, (seed, ev[-1], base[-1]))

    def test_weird_layout_and_walls(self):
        m = {"grid": ["S.....", ".####.", ".#..#.", ".#.##.", "......"], "start": [0, 0], "end": [5, 0],
             "products": [{"id": "A", "name": "a", "x": 2, "y": 2}, {"id": "B", "name": "b", "x": 4, "y": 3}]}
        nodes, D = route.build(m, m["products"])
        self.assertEqual(len(list(e for e in route.simulate(m, m["products"], route.optimize(D), nodes) if e[4])), 2)


if __name__ == "__main__":
    unittest.main()
