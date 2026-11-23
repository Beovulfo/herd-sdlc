import random, unittest
from router import Store, generate, optimize, simulate, compare


class T(unittest.TestCase):
    def test_tiny_exact(self):  # items on a line; optimum walks straight, list order zigzags
        m = {"grid": ["........."], "start": [0, 0], "end": [8, 0],
             "products": {str(i): {"name": "p", "x": i, "y": 0} for i in range(1, 8)}}
        s = Store(m); order = optimize(s, ["7", "1", "5", "2"])
        self.assertEqual(order, ["1", "2", "5", "7"])
        self.assertEqual(simulate(s, order, out=lambda *_: 0)[0], 8)

    def test_big_stores_save_over_30pct(self):
        for cols, rows, items, seed in [(101, 61, 40, 1), (201, 121, 80, 2), (61, 31, 15, 3), (301, 181, 120, 4)]:
            m, lst = generate(cols, rows, items, seed); s = Store(m)
            r = compare(s, [l.split(":")[0] for l in lst], every=0, out=lambda *_: 0)
            self.assertGreater(r["time_saved"], 30, (cols, rows, items, r["time_saved"]))
            self.assertEqual(sorted(r["order"]), sorted(l.split(":")[0] for l in lst))

    def test_unreachable_product(self):
        s = Store({"grid": ["..#", ".##"], "start": [0, 0], "end": [1, 0], "products": {"a": {"name": "x", "x": 2, "y": 1}}})
        self.assertRaises(ValueError, optimize, s, ["a"])


if __name__ == "__main__":
    unittest.main()
