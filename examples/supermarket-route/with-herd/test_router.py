import json, os, subprocess, sys, tempfile, time, unittest
import router, storegen

FAMS = sorted(storegen.FAMILIES)


def store(fam, R, C, n, seed, isolate=0):
    m, ids = storegen.make(fam, R, C, n, seed, isolate)
    m["grid"] = [list(r) for r in m["grid"]]
    return router.Store(m), ids, m


def walk_ok(st, order):
    """Replay the sim: every step is 1 adjacent walkable cell, every item picked at its position, ends at start."""
    prev, picked = None, []
    for e in router.simulate(st, order):
        r, c = e["cell"]
        assert st.grid[r][c] != "#", "walked into shelf"
        if prev and e["kind"] == "move":
            assert abs(prev[0] - r) + abs(prev[1] - c) == 1, "teleport"
        if e["kind"] == "pick":
            assert e["cell"] == st.pos[e["item"]]
            picked.append(e["item"])
        prev = e["cell"]
    assert prev == st.start and sorted(picked) == sorted(order)


class AnyLayout(unittest.TestCase):  # C1
    def test_all_families_and_seeds(self):
        for fam in FAMS:
            for seed in range(6):
                st, ids, _ = store(fam, 41, 51, 25, seed)
                ok, unk, unr = st.split(ids)
                self.assertEqual(sorted(router.optimize(st, ok)), sorted(ok), (fam, seed))
                walk_ok(st, router.optimize(st, ok))

    def test_extremes(self):
        st, ids, _ = store("aisles", 21, 21, 5, 0)
        self.assertEqual(router.optimize(st, []), [])
        self.assertEqual(router.compare(st, [])["optimized"]["distance_m"], 0)
        one = ids[:1]
        self.assertEqual(router.optimize(st, one), one)
        tiny = router.Store(dict(grid=[list("..")], start=[0, 0], products=[dict(id="A", name="a", pos=[0, 1])]))
        self.assertEqual(router.compare(tiny, ["A"])["optimized"]["distance_m"], 2)

    def test_disconnected_unknown_duplicates(self):
        st, ids, _ = store("open", 41, 51, 20, 3, isolate=3)
        r = router.compare(st, ids + [ids[0], "NOPE"])
        self.assertEqual(r["unknown"], ["NOPE"])
        self.assertGreaterEqual(len(r["unreachable"]), 1)
        self.assertEqual(len(r["order"]) + len(r["unreachable"]), 20)  # duplicate dropped
        walk_ok(st, r["order"])

    def test_malformed_map_rejected_cleanly(self):
        for bad in (dict(grid=[list("..."), list("..")], start=[0, 0], products=[]),
                    dict(grid=[], start=[0, 0], products=[]),
                    dict(grid=[list("..")], start=[3, 3], products=[]),
                    dict(grid=[list("#.")], start=[0, 0], products=[])):
            with self.assertRaises(ValueError):
                router.Store(bad)
        off = router.Store(dict(grid=[list("..")], start=[0, 0], products=[dict(id="A", name="a", pos=[0, 5])]))
        self.assertEqual(router.compare(off, ["A"])["unreachable"], ["A"])

    def test_big_store_time_limit(self):
        t = time.time()
        st, ids, _ = store("aisles", 250, 250, 120, 7)
        r = router.compare(st, ids)
        self.assertLess(time.time() - t, 60)
        self.assertEqual(r["unreachable"], [])
        self.assertGreater(r["time_saving"], 0.30)
        walk_ok(st, r["order"])


class Cli(unittest.TestCase):  # C2
    def test_cli_map_and_list_files(self):
        st, ids, m = store("aisles", 31, 41, 12, 2)
        d = tempfile.mkdtemp()
        json.dump(m, open(d + "/m.json", "w"))
        open(d + "/l.txt", "w").write("\n".join("%s:%s" % (i, st.name[i]) for i in ids))
        p = subprocess.run([sys.executable, "router.py", d + "/m.json", d + "/l.txt"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("time saving", p.stdout)
        json.dump(dict(grid=[], start=[0, 0], products=[]), open(d + "/empty.json", "w"))
        p = subprocess.run([sys.executable, "router.py", d + "/empty.json", d + "/l.txt"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn("bad map", p.stderr)
        open(d + "/bad.txt", "w").write("ZZZ:ghost\n")
        p = subprocess.run([sys.executable, "router.py", d + "/m.json", d + "/bad.txt"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn("unknown", p.stderr)


class Simulation(unittest.TestCase):  # C3
    def test_live_kpis_are_monotonic_and_final_matches(self):
        st, ids, _ = store("open", 31, 41, 10, 4)
        order = router.optimize(st, st.split(ids)[0])
        ev = list(router.simulate(st, order))
        self.assertGreater(len(ev), 10)  # step by step, not one summary
        for a, b in zip(ev, ev[1:]):
            self.assertGreaterEqual(b["dist"], a["dist"])
            self.assertGreaterEqual(b["time"], a["time"])
        self.assertEqual(sum(e["kind"] == "move" for e in ev), ev[-1]["dist"])
        self.assertEqual(sum(e["kind"] == "pick" for e in ev), len(order))
        self.assertEqual(router.kpis(st, order)["distance_m"], ev[-1]["dist"])
        want = ev[-1]["dist"] / router.SPEED + len(order) * router.PICK_S
        self.assertAlmostEqual(ev[-1]["time"], want, places=6)

    def test_trace_prints_both_kpis(self):
        st, ids, m = store("aisles", 21, 31, 6, 1)
        d = tempfile.mkdtemp()
        json.dump(m, open(d + "/m.json", "w"))
        open(d + "/l.txt", "w").write("\n".join(ids))
        p = subprocess.run([sys.executable, "router.py", d + "/m.json", d + "/l.txt", "--trace"], capture_output=True, text=True)
        self.assertIn("[list-order]", p.stdout)
        self.assertIn("[optimized]", p.stdout)
        self.assertIn("distance-covered=", p.stdout)
        self.assertIn("time-to-prepare-basket=", p.stdout)


class Saving(unittest.TestCase):  # C4
    def test_over_30_percent_every_family(self):
        for fam in FAMS:
            sv = []
            for seed in range(12):
                st, ids, _ = store(fam, 61, 81, 30, seed)
                sv.append(router.compare(st, ids)["time_saving"])
            print(fam, "min %.3f mean %.3f" % (min(sv), sum(sv) / len(sv)))
            self.assertGreater(sum(sv) / len(sv), 0.30, fam)
            self.assertGreater(min(sv), 0.30, fam)

    def test_never_worse_than_list_order(self):
        for fam in FAMS:
            for seed in range(8):
                st, ids, _ = store(fam, 31, 41, 8, seed)
                r = router.compare(st, ids)
                self.assertLessEqual(r["optimized"]["time_s"], r["baseline"]["time_s"] + 1e-9)


if __name__ == "__main__":
    unittest.main()
