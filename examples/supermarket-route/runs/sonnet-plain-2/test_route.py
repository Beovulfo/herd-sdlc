import itertools, unittest
import route


def store_from(make):
    s, lst = make
    st = route.Store(s)
    return st, route.parse_list("\n".join(lst), st)


class T(unittest.TestCase):
    def test_optimal_small(self):  # heuristic matches brute force on a tiny list
        st, ids = store_from(route.make_demo(40, 20, 7, seed=3))
        pl = route.Planner(st, ids)
        k = len(ids)
        best = min(pl.cost([0, *p, k + 1]) for p in itertools.permutations(range(1, k + 1)))
        self.assertEqual(pl.cost(pl.optimize()), best)

    def test_big_store_saves_30pct(self):
        for kw in ({}, {"obstacles": 0.05}):  # regular aisles, and a messy layout
            st, ids = store_from(route.make_demo(150, 70, 30, seed=5, **kw))
            res = route.compare(st, ids, emit=lambda *_: None)
            self.assertGreater(res["time_saved"], 0.30, kw)

    def test_both_shelf_sides(self):  # product between two aisles is picked from the near side
        st = route.Store({"grid": ["S....", "..#..", ".....", "....E"],
                          "products": [{"id": "a", "name": "a", "x": 2, "y": 1}]})
        self.assertEqual(len(st.access("a")), 4)

    def test_errors(self):
        st = route.Store({"grid": ["S.E"], "products": []})
        with self.assertRaises(ValueError):
            route.parse_list("zzz:nope", st)


if __name__ == "__main__":
    unittest.main()
