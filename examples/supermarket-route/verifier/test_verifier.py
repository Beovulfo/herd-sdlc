"""Tests for verify_independent.py using the reference CLI and two broken variants."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).parent
VERIFIER = HERE / "verify_independent.py"
REFERENCE = (HERE / "reference_cli.py").read_text()


def verify(source, baskets=3):
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "supermarket.py").write_text(source)
        p = subprocess.run([sys.executable, str(VERIFIER), d, "--baskets", str(baskets)],
                           capture_output=True, text=True)
    return p.returncode, p.stdout


class TestVerifier(unittest.TestCase):
    def test_reference_passes(self):
        rc, out = verify(REFERENCE)
        self.assertEqual(rc, 0, out)
        self.assertIn("RESULT: PASS", out)
        self.assertIn("stronger baseline", out)

    def test_teleporting_walk_is_invalid(self):
        src = REFERENCE.replace("    return out[::-1]", "    return [b]")  # jumps straight to the target
        rc, out = verify(src)
        self.assertEqual(rc, 2, out)
        self.assertIn("not adjacent", out)

    def test_optimizer_that_is_just_a_random_walk_fails_the_claim(self):
        src = REFERENCE.replace('if a.algo == "random":', 'if a.algo in ("random", "optimized"):')
        rc, out = verify(src)
        self.assertEqual(rc, 1, out)
        self.assertIn("RESULT: FAIL", out)

    def test_missing_item_is_invalid(self):
        src = REFERENCE.replace("while left:", "while len(left) > 1:")  # leaves one item unpicked
        rc, out = verify(src)
        self.assertEqual(rc, 2, out)
        self.assertIn("picked", out)


if __name__ == "__main__":
    unittest.main()
