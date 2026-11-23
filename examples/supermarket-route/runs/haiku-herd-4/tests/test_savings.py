import json
import os
import random
import statistics
import unittest

from route_optimizer import Store, compare
from tests import layouts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class SavingsTests(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "examples", "demo_store.json")) as f:
            self.store = Store.from_dict(json.load(f))
        with open(os.path.join(ROOT, "examples", "demo_basket.txt")) as f:
            self.basket = [line.split(":")[0].strip() for line in f if line.strip()]

    def test_demo_basket_saves_more_than_30_percent(self):
        result = compare(self.store, self.basket)
        self.assertGreater(result["saving_pct"], 30, result)

    def test_generated_baskets_on_demo_store_save_more_than_30_percent(self):
        rng = random.Random(5)
        savings = []
        for _ in range(20):
            ids = layouts.random_basket(self.store, 10, rng)
            savings.append(compare(self.store, ids)["saving_pct"])
        self.assertGreater(statistics.mean(savings), 30, savings)


if __name__ == "__main__":
    unittest.main()
