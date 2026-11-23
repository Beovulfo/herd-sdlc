import unittest

from optimizer.simulate import compare
from tests.gen import SHAPES, make_case


class SavingsTests(unittest.TestCase):
    def test_optimized_route_saves_over_30_percent_of_time(self):
        list_total = 0.0
        opt_total = 0.0
        for i in range(30):  # 30 generated stores, 3 random lists each
            shape = SHAPES[i % len(SHAPES)]
            size = (30, 60, 90)[i % 3]
            for k in range(3):
                store, items = make_case(shape, size, size, 60, 15, seed=10 * i + k)
                result = compare(store, items)
                list_total += result["list"]["time_to_prepare_basket_s"]
                opt_total += result["optimized"]["time_to_prepare_basket_s"]
        saving = 1 - opt_total / list_total
        self.assertGreater(saving, 0.30, f"time saved over list order: {saving:.1%}")


if __name__ == "__main__":
    unittest.main()
