"""C5: the optimized walk saves more than 30 percent of time over the list-order walk."""
import statistics
import unittest

from route_optimizer import benchmark
from tests.support import run_cli


class SavingTest(unittest.TestCase):
    def test_saving_above_thirty_percent_on_seeded_baskets(self):
        savings = benchmark(200, 200, 400, 25, 50, seed=1)
        self.assertEqual(len(savings), 50)
        self.assertGreater(statistics.median(savings), 0.30)
        self.assertGreater(min(savings), 0.30)

    def test_cli_benchmark_reports_the_saving(self):
        proc = run_cli("benchmark", "--width", "60", "--height", "60", "--products", "120",
                       "--items", "10", "--baskets", "5")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("median=", proc.stdout)


if __name__ == "__main__":
    unittest.main()
