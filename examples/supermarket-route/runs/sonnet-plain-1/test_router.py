import argparse, contextlib, io, os, tempfile, unittest
import router


class T(unittest.TestCase):
    def test_big_store_saves_over_30pct(self):
        with tempfile.TemporaryDirectory() as d:
            m, l = os.path.join(d, "s.json"), os.path.join(d, "l.txt")
            router.cmd_gen(argparse.Namespace(out=m, list=l, width=200, height=120, products=3000, items=40, seed=1)) if False else None
            with contextlib.redirect_stdout(io.StringIO()):
                router.cmd_gen(argparse.Namespace(out=m, list=l, width=200, height=120, products=3000, items=40, seed=1))
                for seed in (1, 2, 3):
                    router.cmd_gen(argparse.Namespace(out=m, list=l, width=200, height=120, products=3000, items=40, seed=seed))
                    out = io.StringIO()
                    with contextlib.redirect_stdout(out):
                        sav = router.cmd_run(argparse.Namespace(map=m, list=l, steps=False))
                    self.assertGreater(sav, 30)

    def test_simulation_matches_matrix_and_visits_all(self):
        grid = ["....", ".##.", "...."]
        stops = [("", (0, 0)), ("a", (3, 1)), ("b", (0, 2)), ("", (3, 2))]
        ev = list(router.simulate(grid, stops))
        self.assertEqual([e[2] for e in ev if e[2]], ["a", "b"])
        self.assertEqual(ev[-1][3], 4 + 4 + 3)  # (0,0)->(3,1)=4, ->(0,2)=4, ->(3,2)=3
        self.assertEqual(ev[-1][1], (3, 2))

    def test_optimize_not_worse_than_input_order(self):
        d = [[abs(i - j) for j in range(6)] for i in range(6)]  # line metric
        order = router.optimize(d)
        self.assertEqual(sum(d[a][b] for a, b in zip(order, order[1:])), 5)


if __name__ == "__main__":
    unittest.main()
