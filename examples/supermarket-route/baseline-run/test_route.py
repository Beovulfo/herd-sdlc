"""Run: python3 test_route.py  (exits non-zero on failure)"""
import random

import route

grid, start = route.load_map("store.txt")
products = route.load_products("products.csv")
order = route.load_order("order.txt", products)


def valid(path):
    assert path[0] == start and path[-1] == start, "route must start and end at S"
    for a, b in zip(path, path[1:]):
        assert route.walkable(grid, b), f"walks into shelf at {b}"
        assert abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1, f"teleport {a}->{b}"


opt = route.optimized_route(grid, start, products, order)
valid(opt)
od, ot = route.kpis(opt, products, order)  # raises if any item is missed

# Optimizer must beat >20% on 50 random baskets, against every random-walk seed tried.
rng = random.Random(42)
worst = 1.0
for basket in range(50):
    o = rng.sample(sorted(products), rng.randint(3, 20))
    _, t_opt = route.kpis(route.optimized_route(grid, start, products, o), products, o)
    for seed in range(5):
        rw = route.random_walk(grid, start, products, o, seed)
        valid(rw)
        _, t_rw = route.kpis(rw, products, o)
        worst = min(worst, 1 - t_opt / t_rw)
assert worst > 0.20, f"worst-case saving {worst:.1%} <= 20%"
print(f"OK: default order {od:.0f} m / {ot:.0f} s; worst-case time saving over 250 runs = {worst:.1%}")
