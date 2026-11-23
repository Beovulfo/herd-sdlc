import unittest, route

class T(unittest.TestCase):
    def test_tiny_exact(self):
        # one aisle; list order goes far-near-far, optimum is a straight sweep
        g = {"grid": ["S.......E", ".#######.", ".........",], "products": [
            {"id": "a", "name": "a", "x": 7, "y": 1}, {"id": "b", "name": "b", "x": 1, "y": 1},
            {"id": "c", "name": "c", "x": 4, "y": 1}]}
        s = route.Store(g)
        order, naive, rt = route.solve(s, ["a", "b", "c"])
        self.assertEqual(order, [1, 2, 0])
        self.assertLess(len(rt(order)[1]), len(rt(naive)[1]))

    def test_big_store_saves_over_30pct(self):
        for seed in range(5):
            data, ids = route.gen(aisles=20, length=60, items=40, seed=seed)
            sv_t, sv_d = route.compare(route.Store(data), ids, out=lambda *_: None)
            self.assertGreater(sv_t, 30)

    def test_bad_map(self):
        with self.assertRaises(ValueError):
            route.Store({"grid": ["S#.", "###"], "products": [{"id": "x", "name": "x", "x": 2, "y": 0}]})

if __name__ == "__main__":
    unittest.main()
