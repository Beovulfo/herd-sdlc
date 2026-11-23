import itertools
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import unittest

import routeopt as r

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def items_for(m, k, seed):
    ids = sorted(m["products"], key=lambda s: int(s[1:]))
    return [(i, m["products"][i][0]) for i in random.Random(seed).sample(ids, k)]


def store(w, h, n, seed, layout):
    return r.parse_map(r.generate(w, h, n, seed, layout))


def cli(*args):
    p = subprocess.run([sys.executable, os.path.join(ROOT, "routeopt.py"), *args], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


class Savings(unittest.TestCase):
    def test_saves_over_30pct_time_on_every_layout_family(self):
        for layout in ("aisles", "rooms", "open"):
            saved = []
            for seed in range(15):
                m = store(41, 31, 120, seed, layout)
                saved.append(r.compare(m, items_for(m, 25, seed))["time_saved_pct"])
            mean = sum(saved) / len(saved)
            print(f"{layout}: mean time saved {mean:.1f}% min {min(saved):.1f}%")
            self.assertGreater(mean, 30, layout)
            self.assertGreater(min(saved), 20, layout)  # no single list collapses

    def test_never_worse_than_list_order_distance(self):
        for seed in range(20):
            m = store(21, 15, 40, seed, "aisles")
            c = r.compare(m, items_for(m, 6, seed))
            self.assertLessEqual(c["optimized"]["distance_m"], c["naive"]["distance_m"] * 1.0001)

    def test_near_optimal_vs_brute_force_on_small_lists(self):
        for seed in range(10):
            m = store(21, 15, 30, seed, "rooms")
            items = items_for(m, 6, seed)
            cells = r.pick_cells(m, items)
            uniq = sorted(set(cells.values()))
            nodes = [m["start"]] + uniq + [m["end"]]
            D = [[r.bfs(m, a)[b[1] * m["w"] + b[0]] for b in nodes] for a in nodes]
            opt = min(r._cost([0, *p, len(uniq) + 1], D) for p in itertools.permutations(range(1, len(uniq) + 1)))
            got = r.final(r.simulate(m, r.plan(m, items)[1]))["cells"]
            self.assertLessEqual(got, opt * 1.1)


class Simulation(unittest.TestCase):
    def test_trace_is_walkable_and_kpis_recompute_from_trace(self):
        for layout in ("aisles", "rooms"):
            m = store(31, 21, 60, 3, layout)
            items = items_for(m, 12, 3)
            _, best = r.plan(m, items)
            ev = list(r.simulate(m, best, speed=1.5, cell_m=2.0, pick_s=5.0))
            moves = [e for e in ev if e["event"] == "move"]
            picks = [e for e in ev if e["event"].startswith("pick")]
            prev = m["start"]
            for e in moves:  # separate recount: adjacency + walkable, one cell per step
                x, y = e["pos"]
                self.assertEqual(abs(x - prev[0]) + abs(y - prev[1]), 1)
                self.assertNotEqual(m["grid"][y][x], "#")
                prev = e["pos"]
            self.assertEqual(prev, m["end"])
            self.assertEqual(len(picks), 12)
            last = ev[-1]
            self.assertEqual(last["distance_m"], len(moves) * 2.0)
            self.assertAlmostEqual(last["time_s"], len(moves) * 2.0 / 1.5 + 12 * 5.0)
            times = [e["time_s"] for e in ev]
            self.assertEqual(times, sorted(times))  # KPIs only grow
            self.assertEqual(sorted(e["event"].split()[1] for e in picks), sorted(i[0] for i in items))


class Scale(unittest.TestCase):
    def test_very_big_store_within_time_limit(self):
        m = store(300, 300, 3000, 1, "aisles")
        items = items_for(m, 40, 1)
        t = time.time()
        c = r.compare(m, items)
        el = time.time() - t
        print(f"300x300, 40 items: {el:.1f}s, saved {c['time_saved_pct']:.1f}%")
        self.assertLess(el, 60)
        self.assertGreater(c["time_saved_pct"], 30)


class Edges(unittest.TestCase):
    def test_collision_same_cell_and_repeated_item_all_counted(self):
        m = r.parse_map({"grid": ["E..C"], "products": [
            {"id": "A", "name": "a", "x": 2, "y": 0}, {"id": "B", "name": "b", "x": 2, "y": 0}]})
        _, best = r.plan(m, [("A", "a"), ("B", "b"), ("A", "a")])
        last = r.final(r.simulate(m, best, pick_s=1.0))
        self.assertEqual(last["picked"], 3)
        self.assertEqual(last["cells"], 3)

    def test_unrequested_unreachable_product_is_ignored_requested_one_fails(self):
        mp = {"grid": ["E.#.C"], "products": [
            {"id": "A", "name": "a", "x": 1, "y": 0}, {"id": "Z", "name": "z", "x": 3, "y": 0}]}
        m = r.parse_map(mp)
        with self.assertRaises(r.RouteError):  # checkout itself is cut off here
            r.plan(m, [("A", "a")])
        mp["grid"] = ["E.#.", "...C"]
        m = r.parse_map(mp)
        r.plan(m, [("A", "a")])
        mp["grid"] = ["E.#C", "..#."]
        with self.assertRaisesRegex(r.RouteError, "Z cannot be reached"):
            r.plan(r.parse_map(mp), [("Z", "z")])

    def test_single_item_and_item_at_entrance(self):
        m = r.parse_map({"grid": ["E.C"], "products": [{"id": "A", "name": "a", "x": 0, "y": 0}]})
        c = r.compare(m, [("A", "a")])
        self.assertEqual(c["optimized"]["picked"], 1)

    def test_bad_input_every_entry_point(self):
        d = tempfile.mkdtemp()

        def w(name, text):
            p = os.path.join(d, name)
            with open(p, "w") as f:
                f.write(text)
            return p
        good = w("good.json", json.dumps({"grid": ["E.C"], "products": [{"id": "A", "name": "a", "x": 1, "y": 0}]}))
        gl = w("good.txt", "A:a\n")
        maps = {"missing": os.path.join(d, "nope.json"), "empty": w("e.json", ""), "notjson": w("n.json", "{"),
                "list": w("l.json", "[]"), "nogrid": w("g.json", "{}"), "ragged": w("r.json", '{"grid":["E.","."]}'),
                "badchar": w("c.json", '{"grid":["EX"]}'), "noentrance": w("ne.json", '{"grid":["..C"]}'),
                "dupid": w("d.json", json.dumps({"grid": ["E.."], "products": [{"id": "A", "x": 1, "y": 0}] * 2})),
                "oob": w("o.json", json.dumps({"grid": ["E.."], "products": [{"id": "A", "x": 9, "y": 0}]})),
                "badprod": w("b.json", json.dumps({"grid": ["E.."], "products": [{"id": "A", "x": "1", "y": 0}]})),
                "binary": w("bin.json", "\x00")}
        for name, p in maps.items():
            code, out, err = cli(p, gl)
            self.assertEqual(code, 2, name)
            self.assertTrue(err.startswith("error:") and "Traceback" not in err, (name, err))
        lists = {"missing": os.path.join(d, "x.txt"), "empty": w("e.txt", ""), "nocolon": w("nc.txt", "A\n"),
                 "noid": w("ni.txt", ":milk\n"), "unknown": w("u.txt", "ZZ:q\n")}
        for name, p in lists.items():
            code, out, err = cli(good, p)
            self.assertEqual(code, 2, name)
            self.assertTrue(err.startswith("error:") and "Traceback" not in err, (name, err))
        with open(os.path.join(d, "bin.txt"), "wb") as f:
            f.write(b"\xff\xfe\x00")
        code, _, err = cli(good, os.path.join(d, "bin.txt"))
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)
        for flag in ("--speed", "--pick-s", "--cell-m"):
            code, _, err = cli(good, gl, flag, "-1")
            self.assertEqual(code, 2, flag)
            self.assertNotIn("Traceback", err)
        code, out, _ = cli(good, gl)
        self.assertEqual(code, 0)
        self.assertIn("time-to-prepare-basket", out)

    def test_cli_simulate_prints_each_step_with_live_kpis(self):
        d = tempfile.mkdtemp()
        mp, lp = os.path.join(d, "m.json"), os.path.join(d, "l.txt")
        json.dump(r.generate(15, 11, 20, 2), open(mp, "w"))
        open(lp, "w").write("P1:item1\nP5:item5\nP9:item9\n")
        code, out, _ = cli(mp, lp, "--simulate")
        self.assertEqual(code, 0)
        self.assertIn("[list-order] start", out)
        self.assertIn("[optimized] pick P", out)
        self.assertIn("time saved", out)


if __name__ == "__main__":
    unittest.main()
