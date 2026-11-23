import sys
import unittest

from route_optimizer import benchmark


class SavingTest(unittest.TestCase):
    def test_optimized_route_saves_more_than_30_percent_of_basket_time(self):
        rows, saving = benchmark(range(20))
        print("\nseed layout  size     list_s  optimized_s  saving_pct", file=sys.stderr)
        for r in rows:
            print(
                f"{r['seed']:>4} {r['layout']:<7} {r['size']:<8} {r['list_time_s']:>7.1f} "
                f"{r['optimized_time_s']:>12.1f} {r['saving_pct']:>10.1f}",
                file=sys.stderr,
            )
        print(f"aggregate saving over {len(rows)} stores: {saving:.1f}%", file=sys.stderr)
        self.assertGreater(saving, 30.0)


if __name__ == "__main__":
    unittest.main()
