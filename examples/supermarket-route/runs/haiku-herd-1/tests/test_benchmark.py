import unittest

from supermarket_route.gen import generate_store, random_basket
from supermarket_route.layout import parse_list
from supermarket_route.planner import build_model
from supermarket_route.simulate import compare


class BenchmarkTest(unittest.TestCase):
    def test_optimized_route_saves_more_than_30_percent_of_time(self):
        savings = []
        for seed in range(1, 6):
            store = generate_store("aisles", width=41, height=31, seed=seed, products=120)
            for basket_seed in range(20):
                lines = random_basket(store, 12, seed=seed * 100 + basket_seed)
                model = build_model(store, parse_list(lines, store))
                result = compare(model)
                savings.append(result["saving_pct"])
        mean = sum(savings) / len(savings)
        self.assertGreater(mean, 30.0, f"mean saving {mean:.1f}% over {len(savings)} baskets")
        self.assertGreaterEqual(min(savings), 0.0)


if __name__ == "__main__":
    unittest.main()
