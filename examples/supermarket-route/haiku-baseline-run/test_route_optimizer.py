"""Self-check: run with `python3 test_route_optimizer.py` (or pytest)."""
import random

from route_optimizer import distances, nearest_neighbour, two_opt, route_steps, make_sample


def test_corridor_distance():
    # 1x5 corridor, stops at x=0 and x=4 must be 4 steps apart
    D, P = distances(["....."], [(0, 0), (4, 0)])
    assert D[0][1] == 4 and len(P[0][1]) == 5


def test_two_opt_is_permutation_and_not_worse():
    rng = random.Random(0)
    pts = [(rng.randrange(40), rng.randrange(40)) for _ in range(12)]
    grid = ["." * 40 for _ in range(40)]
    D, _ = distances(grid, [(0, 0)] + pts + [(39, 39)])
    n = len(pts)
    nn = nearest_neighbour(D, n)
    opt = two_opt(list(nn), D)
    assert sorted(opt) == list(range(n + 2))
    assert opt[0] == 0 and opt[-1] == n + 1
    assert route_steps(opt, D) <= route_steps(nn, D)


def test_sample_store_has_reachable_products():
    m, order = make_sample(1)
    assert len(m["products"]) == 120 and len(order) == 25
    for p in m["products"]:
        assert m["grid"][p["y"]][p["x"]] == "."


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
