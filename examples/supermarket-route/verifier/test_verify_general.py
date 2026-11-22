"""Tests for verify_general.py using its reference adapter and two broken variants."""
import subprocess
import sys
import unittest
from pathlib import Path

import verify_general as vg

HERE = Path(__file__).parent


def run(*extra):
    p = subprocess.run([sys.executable, str(HERE / "verify_general.py"), "reference", str(HERE), "--tiers", "S",
                        "--seeds", "1", *extra], capture_output=True, text=True)
    return p.returncode, p.stdout


class TestGeneral(unittest.TestCase):
    def test_every_family_makes_a_connected_instance_at_each_small_tier(self):
        for tier in ("S", "M"):
            for fam in vg.FAMILIES:
                c = vg.make_instance(fam, tier, 7000)
                self.assertEqual(len(c["ids"]), vg.TIERS[tier][2], fam)
                rows, (sr, sc) = c["grid"], c["station"]
                h, w = len(rows), len(rows[0])
                reach = vg.bfs_flat(rows, w, h, [sr * w + sc])
                for pid in c["ids"]:
                    self.assertTrue(any(reach[a[0] * w + a[1]] >= 0 for a in c["products"][pid]["access"]), (fam, pid))

    def test_instances_are_deterministic(self):
        self.assertEqual(vg.make_instance("maze", "S", 7000), vg.make_instance("maze", "S", 7000))
        self.assertNotEqual(vg.make_instance("maze", "S", 7000)["grid"], vg.make_instance("maze", "S", 7001)["grid"])

    def test_exact_optimum_on_a_corridor(self):
        canon = {"grid": ["#######", "#.....#", "#######"], "station": [1, 1],
                 "products": {"A": {"access": [[1, 3]]}, "B": {"access": [[1, 5]]}}, "ids": ["A", "B"]}
        self.assertEqual(vg.exact_optimum(canon, True), 8)   # out to the far end and back
        self.assertEqual(vg.exact_optimum(canon, False), 4)

    def test_lower_bound_never_exceeds_the_exact_optimum(self):
        for fam in vg.FAMILIES:
            c = vg.make_instance(fam, "S", 7000)
            self.assertLessEqual(vg.one_tree_bound(c), vg.exact_optimum(c, True), fam)

    def test_nearest_neighbour_distance_is_at_least_the_exact_optimum(self):
        for fam in vg.FAMILIES:
            c = vg.make_instance(fam, "S", 7000)
            self.assertGreaterEqual(vg.nn_distance(c), vg.exact_optimum(c, True), fam)

    def test_reference_passes_every_family(self):
        rc, out = run()
        self.assertEqual(rc, 0, out)
        self.assertIn("RESULT: PASS", out)
        for fam in vg.FAMILIES:
            self.assertIn(f"- {fam}:", out)

    def test_teleporting_route_is_invalid(self):
        rc, out = run("--break", "teleport")
        self.assertEqual(rc, 1, out)
        self.assertIn("non-adjacent", out)

    def test_route_that_skips_items_is_invalid(self):
        rc, out = run("--break", "skip_item")
        self.assertEqual(rc, 1, out)
        self.assertRegex(out, "never reached|non-adjacent|reported distance")

    def test_trace_validation_catches_walls_and_wrong_distance(self):
        canon = {"grid": ["#####", "#...#", "#####"], "station": [1, 1], "products": {"A": {"shelf": [1, 3]}}, "ids": ["A"]}
        good = {"trace": [[1, 2], [1, 3], [1, 2], [1, 1]], "dist": 4, "speed": 1.0, "pick": 5.0, "time": 9.0}
        self.assertEqual(vg.validate_trace(canon, "x", good, True), 4)
        for bad in (dict(good, trace=[[0, 1]] + good["trace"][1:]), dict(good, dist=3), dict(good, time=4.0)):
            with self.assertRaises(AssertionError):
                vg.validate_trace(canon, "x", bad, True)


if __name__ == "__main__":
    unittest.main()
