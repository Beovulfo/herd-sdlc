import itertools, json, os, subprocess, sys, tempfile, unittest

import routeopt as ro

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP, LIST = os.path.join(ROOT, "data", "store_map.json"), os.path.join(ROOT, "data", "list.txt")

SMALL = {
    "grid": ["#######",
             "#.....#",
             "#.###.#",
             "#.....#",
             "#######"],
    "start": [1, 1],
    "products": [{"id": "A", "name": "milk", "pos": [1, 5]},
                 {"id": "B", "name": "eggs", "pos": [3, 1]},
                 {"id": "C", "name": "tea", "pos": [3, 5]},
                 {"id": "D", "name": "rice", "pos": [1, 3]}],
}


def read(path):
    with open(path) as f:
        return f.read()


def write(path, text):
    with open(path, "w") as f:
        f.write(text)


def small():
    return ro.Store.from_dict(SMALL)


def run_cli(*args):
    return subprocess.run([sys.executable, os.path.join(ROOT, "routeopt.py"), *args],
                          capture_output=True, text=True, cwd=ROOT)


class ParseTests(unittest.TestCase):
    def test_list_parses_id_and_name(self):
        self.assertEqual(ro.parse_list("A:milk\nB:eggs\n", small()), ["A", "B"])

    def test_unknown_id_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown product"):
            ro.parse_list("Z:milk", small())

    def test_line_without_colon_rejected(self):
        with self.assertRaisesRegex(ValueError, "expected id:short name"):
            ro.parse_list("A milk", small())

    def test_name_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "name"):
            ro.parse_list("A:eggs", small())


class PlanTests(unittest.TestCase):
    def total(self, st, order):
        pts = [st.start] + [st.products[i][1] for i in order]
        return sum(len(ro.bfs_path(st, a, b)) - 1 for a, b in zip(pts, pts[1:]))

    def test_optimized_matches_brute_force_on_small_cases(self):
        st = small()
        ids = ["A", "B", "C", "D"]
        best = min(self.total(st, p) for p in itertools.permutations(ids))
        self.assertEqual(self.total(st, ro.plan_optimized(st, ids)), best)

    def test_optimized_near_brute_force_on_sample_map(self):
        st = ro.load_map(MAP)
        ids = ro.parse_list(read(LIST), st)[:7]
        best = min(self.total(st, p) for p in itertools.permutations(ids))
        self.assertEqual(self.total(st, ro.plan_optimized(st, ids)), best)

    def test_exact_planner_beats_or_ties_heuristic_on_12_items(self):
        st = ro.load_map(MAP)
        ids = ro.parse_list(read(LIST), st)
        exact = self.total(st, ro.plan_optimized(st, ids))
        ro.EXACT_MAX, saved = 0, ro.EXACT_MAX
        try:
            heur = self.total(st, ro.plan_optimized(st, ids))
        finally:
            ro.EXACT_MAX = saved
        self.assertLessEqual(exact, heur)

    def test_unreachable_item_rejected(self):
        d = json.loads(json.dumps(SMALL))
        d["grid"] = ["#######", "#.#...#", "#.#.#.#", "#.###.#", "#######"]  # now column 1 is cut off from column 5
        d["start"] = [1, 5]
        d["products"] = [{"id": "B", "name": "eggs", "pos": [3, 1]}]
        with self.assertRaisesRegex(ValueError, "unreachable"):
            ro.plan_optimized(ro.Store.from_dict(d), ["B"])

    def test_empty_list(self):
        st = small()
        self.assertEqual(ro.plan_optimized(st, []), [])
        last = list(ro.simulate(st, [], "optimized"))[-1]
        self.assertEqual((last.t, last.dist), (0.0, 0))


class SimulateTests(unittest.TestCase):
    def check_stream(self, algo):
        st = small()
        steps = list(ro.simulate(st, ["A", "B", "C", "D"], algo, seed=3))
        ts = [s.t for s in steps]
        ds = [s.dist for s in steps]
        self.assertEqual(ts, sorted(ts))
        self.assertEqual(ds, sorted(ds))
        picks = [s.event for s in steps if s.event.startswith("pick ")]
        self.assertEqual(sorted(picks), ["pick A", "pick B", "pick C", "pick D"])
        # every move is one adjacent walkable cell
        for a, b in zip(steps, steps[1:]):
            self.assertLessEqual(abs(a.pos[0] - b.pos[0]) + abs(a.pos[1] - b.pos[1]), 1)
            self.assertEqual(st.grid[b.pos[0]][b.pos[1]], ".")
        return steps[-1]

    def test_optimized_stream(self):
        last = self.check_stream("optimized")
        self.assertEqual(last.t, last.dist * ro.STEP_S + 4 * ro.PICK_S)

    def test_random_stream(self):
        self.check_stream("random")

    def test_random_is_seeded(self):
        st = small()
        a = list(ro.simulate(st, ["A", "C"], "random", seed=5))
        b = list(ro.simulate(st, ["A", "C"], "random", seed=5))
        self.assertEqual(a, b)


class CompareTests(unittest.TestCase):
    def test_optimized_saves_over_20_percent_on_sample_store(self):
        st = ro.load_map(MAP)
        ids = ro.parse_list(read(LIST), st)
        r = ro.compare(st, ids, runs=10, seed=1)
        self.assertGreater(r["savings_pct"], 20)
        self.assertLess(r["optimized"]["dist"], r["random"]["dist"])


class VisualizeTests(unittest.TestCase):
    def test_html_embeds_both_runs_with_all_picks(self):
        st = ro.load_map(MAP)
        ids = ro.parse_list(read(LIST), st)
        html = ro.build_html(st, ids, seed=1)
        data = json.loads(html.split("const D = ", 1)[1].split(", CELL", 1)[0])
        self.assertEqual(len(data["runs"]), 2)
        for run in data["runs"]:
            self.assertEqual(sum(s[4].startswith("pick ") for s in run["steps"]), 12)

    def test_cli_writes_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "s.html")
            p = run_cli("visualize", "--map", MAP, "--list", LIST, "--out", out)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("time-to-prepare-basket", read(out))


class CliTests(unittest.TestCase):
    def test_compare_passes_threshold(self):
        p = run_cli("compare", "--map", MAP, "--list", LIST, "--runs", "10", "--min-savings", "20")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("time-to-prepare-basket", p.stdout)
        self.assertIn("distance-covered", p.stdout)
        self.assertIn("savings", p.stdout)

    def test_compare_fails_impossible_threshold(self):
        p = run_cli("compare", "--map", MAP, "--list", LIST, "--runs", "3", "--min-savings", "99.99")
        self.assertEqual(p.returncode, 1)

    def test_simulate_prints_live_kpis(self):
        p = run_cli("simulate", "--map", MAP, "--list", LIST, "--algo", "optimized")
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = [l for l in p.stdout.splitlines() if l.startswith("t=")]
        self.assertGreater(len(lines), 20)
        self.assertIn("dist=", lines[0])
        self.assertEqual(sum("pick " in l for l in lines), 12)

    def cli_error(self, list_text, map_dict=None, *extra):
        with tempfile.TemporaryDirectory() as d:
            mp, lp = os.path.join(d, "m.json"), os.path.join(d, "l.txt")
            write(mp, json.dumps(map_dict or SMALL))
            write(lp, list_text)
            return run_cli("compare", "--map", mp, "--list", lp, *extra)

    def test_unknown_id_exits_2(self):
        p = self.cli_error("ZZZ:nothing\n")
        self.assertEqual(p.returncode, 2)
        self.assertIn("unknown product", p.stderr)

    def test_name_mismatch_exits_2(self):
        p = self.cli_error("A:eggs\n")
        self.assertEqual(p.returncode, 2)
        self.assertIn("does not match", p.stderr)

    def test_unreachable_exits_2(self):
        d = json.loads(json.dumps(SMALL))
        d["grid"] = ["#######", "#.#...#", "#.#.#.#", "#.###.#", "#######"]
        d["start"] = [1, 5]
        d["products"] = [{"id": "B", "name": "eggs", "pos": [3, 1]}]
        p = self.cli_error("B:eggs\n", d)
        self.assertEqual(p.returncode, 2)
        self.assertIn("unreachable", p.stderr)

    def test_zero_runs_rejected_not_crash(self):
        p = self.cli_error("A:milk\n", None, "--runs", "0")
        self.assertEqual(p.returncode, 2)
        self.assertNotIn("Traceback", p.stderr)

    def test_malformed_map_exits_2(self):
        d = json.loads(json.dumps(SMALL))
        d["products"][0]["pos"] = 5
        p = self.cli_error("A:milk\n", d)
        self.assertEqual(p.returncode, 2)
        self.assertNotIn("Traceback", p.stderr)


if __name__ == "__main__":
    unittest.main()
