import ast, io, itertools, json, os, random, subprocess, sys, tempfile, unittest

import supermarket as sm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP, LIST = os.path.join(ROOT, "examples", "map.json"), os.path.join(ROOT, "examples", "list.json")
BASKETS, BASKET_SIZE = 30, 8

SMALL = {
    "grid": ["#######",
             "#S....#",
             "#.###.#",
             "#.....#",
             "#######"],
    "start": [1, 1],
    "products": {"A": {"name": "milk", "cell": [5, 1]}, "B": {"name": "eggs", "cell": [1, 3]},
                 "C": {"name": "tea", "cell": [5, 3]}, "D": {"name": "rice", "cell": [3, 1]}},
}


def jread(path):
    with open(path) as f:
        return json.load(f)


def items(ids, mp):
    return {"items": [{"id": i, "name": mp["products"][i]["name"]} for i in ids]}


def cli(mp, lst, algo="optimized", seed=0):
    """Run the real command on dicts; returns CompletedProcess."""
    with tempfile.TemporaryDirectory() as d:
        mpath, lpath = os.path.join(d, "m.json"), os.path.join(d, "l.json")
        for path, obj in ((mpath, mp), (lpath, lst)):
            with open(path, "w") as f:
                json.dump(obj, f)
        return subprocess.run([sys.executable, os.path.join(ROOT, "supermarket.py"), "simulate", "--map", mpath,
                               "--list", lpath, "--algo", algo, "--seed", str(seed)],
                              capture_output=True, text=True, cwd=ROOT)


def lines(p):
    return [json.loads(l) for l in p.stdout.splitlines()]


def run_algo(store, ids, algo, seed=0):
    steps = list(sm.simulate(store, ids, algo, seed))
    return steps, sm.summary(steps)


def basket(store, seed):
    return random.Random(seed).sample(sorted(store.products), BASKET_SIZE)


class StdoutProtocolTests(unittest.TestCase):
    def check(self, algo):
        mp = jread(MAP)
        ids = [i["id"] for i in jread(LIST)["items"]]
        p = cli(mp, jread(LIST), algo, seed=4)
        self.assertEqual(p.returncode, 0, p.stderr)
        out = lines(p)
        steps, final = out[:-1], out[-1]
        self.assertTrue(all(s["type"] == "step" for s in steps))
        self.assertEqual([s["n"] for s in steps], list(range(1, len(steps) + 1)))
        self.assertEqual(set(final), {"type", "algo", "time_to_prepare", "distance", "picked"})
        self.assertEqual((final["type"], final["algo"], final["picked"]), ("final", algo, len(ids)))
        got = [i for s in steps for i in s["picked"]]
        self.assertEqual(sorted(got), sorted(ids))
        prev, dist, grid = mp["start"], 0, mp["grid"]
        for s in steps:
            x, y = s["pos"]
            self.assertNotEqual(grid[y][x], "#")
            step_len = abs(x - prev[0]) + abs(y - prev[1])
            self.assertLessEqual(step_len, 1)
            dist += step_len
            self.assertEqual(s["distance"], dist)
            for i in s["picked"]:
                self.assertEqual(mp["products"][i]["cell"], [x, y])
            prev = [x, y]
        self.assertEqual(final["distance"], dist)
        self.assertEqual(final["time_to_prepare"], sm.WALK_S * dist + sm.PICK_S * len(ids))
        self.assertEqual(steps[-1]["time"], final["time_to_prepare"])
        times = [s["time"] for s in steps]
        self.assertEqual(times, sorted(times))

    def test_optimized(self): self.check("optimized")
    def test_list_order(self): self.check("list-order")
    def test_random(self): self.check("random")

    def test_same_seed_same_output(self):
        a, b = cli(jread(MAP), jread(LIST), "random", 9), cli(jread(MAP), jread(LIST), "random", 9)
        c = cli(jread(MAP), jread(LIST), "random", 10)
        self.assertEqual(a.stdout, b.stdout)
        self.assertNotEqual(a.stdout, c.stdout)

    def test_stdlib_only(self):
        with open(os.path.join(ROOT, "supermarket.py")) as f:
            tree = ast.parse(f.read())
        mods = {n.name.split(".")[0] for x in ast.walk(tree) if isinstance(x, ast.Import) for n in x.names}
        mods |= {x.module.split(".")[0] for x in ast.walk(tree) if isinstance(x, ast.ImportFrom)}
        self.assertTrue(mods <= set(sys.stdlib_module_names), mods)


class StreamingTests(unittest.TestCase):
    def test_simulation_is_lazy(self):
        store = sm.Store.from_dict(jread(MAP))
        gen = sm.simulate(store, basket(store, 0), "optimized", 0)
        first = next(gen)
        self.assertEqual(first[0], 1)

    def test_main_flushes_each_line(self):
        class Out(io.StringIO):
            flushes = 0
            def flush(self):
                Out.flushes += 1
        out = Out()
        self.assertEqual(sm.main(["simulate", "--map", MAP, "--list", LIST, "--algo", "optimized"], out=out), 0)
        self.assertGreaterEqual(Out.flushes, len(out.getvalue().splitlines()))


class MeanSavingsTests(unittest.TestCase):
    def test_optimized_saves_over_20_percent_vs_random_over_seeded_baskets(self):
        store = sm.Store.from_dict(jread(MAP))
        mean = {a: 0.0 for a in ("optimized", "list-order", "random")}
        for seed in range(BASKETS):
            ids = basket(store, seed)
            for a in mean:
                mean[a] += run_algo(store, ids, a, seed)[1]["time_to_prepare"] / BASKETS
        saving = {a: 100 * (1 - mean["optimized"] / mean[a]) for a in ("random", "list-order")}
        print(f"\nmean time-to-prepare over {BASKETS} baskets of {BASKET_SIZE}: "
              + ", ".join(f"{a}={m:.1f}s" for a, m in mean.items())
              + f" | optimized saves {saving['random']:.1f}% vs random, {saving['list-order']:.1f}% vs list-order")
        self.assertGreater(saving["random"], 20)
        self.assertLess(mean["optimized"], mean["list-order"])  # also beats the stronger baseline


class OptimalityTests(unittest.TestCase):
    def test_optimized_distance_matches_brute_force_on_small_store(self):
        store = sm.Store.from_dict(SMALL)
        ids = ["A", "B", "C", "D"]

        def total(order):
            pts = [store.start] + [store.products[i][1] for i in order]
            return sum(sm.bfs(store, a)[0][b] for a, b in zip(pts, pts[1:]))
        best = min(total(p) for p in itertools.permutations(ids))
        self.assertEqual(run_algo(store, ids, "optimized")[1]["distance"], best)

    def test_item_on_start_cell_is_picked(self):
        mp = json.loads(json.dumps(SMALL))
        mp["products"]["A"]["cell"] = [1, 1]
        for algo in ("optimized", "list-order", "random"):
            out = lines(cli(mp, items(["A"], mp), algo))
            self.assertEqual(out[-1]["picked"], 1)
            self.assertEqual(out[-1]["distance"], 0)

    def test_list_order_visits_in_list_order(self):
        out = lines(cli(SMALL, items(["B", "A"], SMALL), "list-order"))
        self.assertEqual([i for s in out[:-1] for i in s["picked"]], ["B", "A"])

    def test_duplicate_list_items_counted_once(self):
        out = lines(cli(SMALL, items(["A", "A", "B"], SMALL)))
        self.assertEqual(out[-1]["picked"], 2)


class EdgeCaseTests(unittest.TestCase):
    def test_empty_list_gives_zero_kpis(self):
        for algo in ("optimized", "list-order", "random"):
            p = cli(SMALL, {"items": []}, algo)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(lines(p), [{"type": "final", "algo": algo, "time_to_prepare": 0.0, "distance": 0, "picked": 0}])

    def fails(self, mp, lst, text):
        p = cli(mp, lst)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn(text, p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        self.assertEqual(p.stdout, "")

    def test_unknown_product_id(self):
        self.fails(SMALL, {"items": [{"id": "ZZZ", "name": "ghost"}]}, "unknown product")

    def test_unreachable_product(self):
        mp = json.loads(json.dumps(SMALL))
        mp["grid"] = ["#######", "#S..#.#", "#...#.#", "#...#.#", "#######"]
        mp["products"]["B"]["cell"] = [5, 2]
        self.fails(mp, items(["B"], mp), "unreachable")

    def test_malformed_map_is_clear_error(self):
        mp = json.loads(json.dumps(SMALL))
        mp["products"]["A"]["cell"] = 5
        self.fails(mp, items(["A"], mp), "malformed input")

    def test_start_on_wall_is_clear_error(self):
        mp = json.loads(json.dumps(SMALL))
        mp["start"] = [0, 0]
        self.fails(mp, items(["A"], mp), "start")

    def test_list_item_without_id_is_clear_error(self):
        self.fails(SMALL, {"items": [{"name": "milk"}]}, "needs an id")

    def test_missing_list_key_is_clear_error(self):
        self.fails(SMALL, {}, "missing key")


if __name__ == "__main__":
    unittest.main()
