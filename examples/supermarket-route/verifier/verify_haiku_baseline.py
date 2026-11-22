#!/usr/bin/env python3
"""Independent check of the Haiku no-workflow solution (route_optimizer.py).

Adapter for this solution's formats (entrance, checkout and products with x, y). Generates its own
stores and baskets from unseen seeds, validates every leg of every route, recomputes the KPIs,
and checks the claim of this experiment: optimized saves more than 30 percent of time against
the list-order route. Standard library only.

Usage: verify_haiku_baseline.py PROJECT_DIR [--baskets N] [--seed-base S] [--target 30]
"""
import argparse
import itertools
import statistics
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from verify_independent import make_list, make_store  # noqa: E402


def bfs(grid, src):
    d, q = {src: 0}, deque([src])
    while q:
        x, y = q.popleft()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if grid[n[1]][n[0]] == "." and n not in d:
                d[n] = d[(x, y)] + 1
                q.append(n)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--baskets", type=int, default=20)
    ap.add_argument("--seed-base", type=int, default=9001)
    ap.add_argument("--target", type=float, default=30.0)
    a = ap.parse_args()
    sys.path.insert(0, str(a.project))
    import route_optimizer as ro

    rows, exact_n, exact_ok, gaps = [], 0, 0, []
    for b in range(a.baskets):
        seed = a.seed_base + b
        store, k = make_store(seed), 6 + b % 10
        items = make_list(store, seed, k)["items"]
        grid = store["grid"]
        start = tuple(store["start"])
        prods = [{"id": pid, "name": p["name"], "x": p["cell"][0], "y": p["cell"][1]}
                 for pid, p in store["products"].items()]
        pm = {p["id"]: p for p in prods}
        ids = [i["id"] for i in items]
        n = len(ids)
        stops = [start] + [(pm[i]["x"], pm[i]["y"]) for i in ids] + [start]
        names = ["ENTRANCE"] + [pm[i]["name"] for i in ids] + ["CHECKOUT"]
        D, P = ro.distances(grid, stops)
        results = {}
        for label, route in (("list", list(range(n + 2))), ("opt", ro.two_opt(ro.nearest_neighbour(D, n), D))):
            assert route[0] == 0 and route[-1] == n + 1 and sorted(route[1:-1]) == list(range(1, n + 1)), \
                f"{label}: route must start at the entrance, end at checkout and visit every item once"
            paths = [P[x][y] for x, y in zip(route, route[1:])]
            for leg, (x, y) in zip(paths, zip(route, route[1:])):
                assert leg[0] == stops[x] and leg[-1] == stops[y], f"{label}: leg does not join its stops"
                for u, v in zip(leg, leg[1:]):
                    assert abs(u[0] - v[0]) + abs(u[1] - v[1]) == 1 and grid[v[1]][v[0]] == ".", f"{label}: illegal move"
            dist = sum(len(leg) - 1 for leg in paths)
            time_s = dist / ro.WALK_MPS + ro.PICK_S * n
            last = list(ro.run_route(route, paths, names, n))[-1]
            assert abs(last.t - time_s) < 1e-6 and abs(last.dist_m - dist) < 1e-6, f"{label}: reported KPIs differ"
            results[label] = (time_s, dist)
        if n <= 7:
            dm = {s: bfs(grid, s) for s in set(stops)}
            cells = stops[1:-1]
            best = min(sum(dm[x][y] for x, y in zip((start,) + perm, perm + (start,))) for perm in itertools.permutations(cells))
            exact_n += 1
            exact_ok += results["opt"][1] == best
            gaps.append(results["opt"][1] / best - 1)
        rows.append(results)
    mean = lambda key, i: statistics.mean(r[key][i] for r in rows)
    save = [1 - r["opt"][0] / r["list"][0] for r in rows]
    print(f"baskets: {len(rows)} stores and lists from seeds {a.seed_base}.., all routes valid, KPIs recomputed")
    print("| route | mean time (s) | mean distance (m) |\n| --- | --- | --- |")
    for name, key in (("optimized", "opt"), ("list order", "list")):
        print(f"| {name} | {mean(key, 0):.1f} | {mean(key, 1):.1f} |")
    below = sum(s * 100 <= a.target for s in save)
    print(f"time saved vs list order: mean {statistics.mean(save):.1%}, smallest {min(save):.1%}, "
          f"baskets at or below {a.target:.0f}%: {below} of {len(rows)}")
    print(f"brute-force optimum on small baskets: exact on {exact_ok} of {exact_n}; largest gap {max(gaps, default=0):.1%}")
    ok = statistics.mean(save) * 100 > a.target
    print("RESULT:", "PASS" if ok else "FAIL", "(mean saving above target)")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(f"RESULT: INVALID, {e}")
        sys.exit(2)
