import random, unittest
import routeopt as r


class T(unittest.TestCase):
    def test_saves_over_30pct_many_seeds(self):
        for seed in range(5):
            d = r.demo_store(10, 30, seed)
            ids = random.Random(seed).sample(list(p["id"] for p in d["products"]), 20)
            s = r.Store(d)
            nodes, m, listed, opt = r.plan(s, ids)
            d0, t0 = r.simulate(s, nodes, listed, ids)
            d1, t1 = r.simulate(s, nodes, opt, ids)
            self.assertEqual(sorted(opt), listed)           # every item visited once
            self.assertAlmostEqual(d1, sum(m[opt[i]][opt[i+1]] for i in range(len(opt)-1)))
            self.assertAlmostEqual(t1, d1 / r.WALK_SPEED + 20 * r.PICK_TIME)  # every pick counted
            self.assertGreater(1 - t1 / t0, 0.30)

    def test_arbitrary_layout_with_wall(self):
        d = {"grid": ["....", ".##.", "...."], "start": [0, 0],
             "products": [{"id": "A", "name": "a", "x": 1, "y": 1}, {"id": "B", "name": "b", "x": 2, "y": 1}]}
        s = r.Store(d)
        nodes, m, listed, opt = r.plan(s, ["A", "B"])
        self.assertEqual(r.simulate(s, nodes, opt, ["A", "B"])[0], m[0][opt[1]] + m[opt[1]][opt[2]] + m[opt[2]][3])


unittest.main() if __name__ == "__main__" else None
