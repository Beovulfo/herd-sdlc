#!/usr/bin/env python3
"""Independent check of the Haiku solution built with the Herd workflow (route_optimizer.py).

Adapter for this solution's formats. Generates its own stores and baskets from unseen seeds,
recomputes every distance and KPI with its own BFS, and checks the claim of this experiment:
optimized saves more than 30 percent of time against the list-order route. Also reports how
fine the simulation is (events per route), since the request asks for a step-by-step simulation.

Usage: verify_haiku_herd.py PROJECT_DIR [--baskets N] [--seed-base S] [--target 30]
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

    rows, exact_n, exact_ok, gaps, events, cells_walked = [], 0, 0, [], [], []
    for b in range(a.baskets):
        seed = a.seed_base + b
        store, k = make_store(seed), 6 + b % 10
        ids = [i["id"] for i in make_list(store, seed, k)["items"]]
        data = {"grid": store["grid"], "start": store["start"], "end": store["start"],
                "products": [{"id": pid, "short": p["name"], "x": p["cell"][0], "y": p["cell"][1]}
                             for pid, p in store["products"].items()]}
        st, grid, n = ro.Store(data), store["grid"], len(ids)
        res = {}
        for strat in ("list-order", "optimized"):
            order, cells, _ = ro.plan_route(st, ids, strat)
            assert order[0] == 0 and order[-1] == n + 1 and sorted(order[1:-1]) == list(range(1, n + 1)), \
                f"{strat}: route must start at the entrance, end at checkout and visit every item once"
            dist = sum(bfs(grid, cells[x])[cells[y]] for x, y in zip(order, order[1:]))
            evs = list(ro.simulate(st, ids, strat))
            assert evs[-1]["distance_covered"] == dist, f"{strat}: reported distance differs from mine"
            t = dist / ro.WALK_SPEED + ro.PICK_S * n
            assert abs(evs[-1]["time_to_prepare_s"] - t) < 0.06, f"{strat}: reported time differs from mine"
            res[strat] = (t, dist)
            if strat == "optimized":
                events.append(len(evs))
                cells_walked.append(dist)
        if n <= 7:
            cells = ro.stops(st, ids)
            dm = {c: bfs(grid, c) for c in set(cells)}
            mid = cells[1:-1]
            best = min(sum(dm[x][y] for x, y in zip((cells[0],) + perm, perm + (cells[-1],))) for perm in itertools.permutations(mid))
            exact_n += 1
            exact_ok += res["optimized"][1] == best
            gaps.append(res["optimized"][1] / best - 1)
        rows.append(res)
    mean = lambda key, i: statistics.mean(r[key][i] for r in rows)
    save = [1 - r["optimized"][0] / r["list-order"][0] for r in rows]
    print(f"baskets: {len(rows)} stores and lists from seeds {a.seed_base}.., all routes valid, KPIs recomputed")
    print("| route | mean time (s) | mean distance (cells) |\n| --- | --- | --- |")
    for name in ("optimized", "list-order"):
        print(f"| {name} | {mean(name, 0):.1f} | {mean(name, 1):.1f} |")
    below = sum(s * 100 <= a.target for s in save)
    print(f"time saved vs list order: mean {statistics.mean(save):.1%}, smallest {min(save):.1%}, "
          f"baskets at or below {a.target:.0f}%: {below} of {len(rows)}")
    print(f"brute-force optimum on small baskets: exact on {exact_ok} of {exact_n}; largest gap {max(gaps, default=0):.1%}")
    print(f"simulation granularity: {statistics.mean(events):.1f} events per route "
          f"(one per stop) for {statistics.mean(cells_walked):.0f} cells walked")
    ok = statistics.mean(save) * 100 > a.target
    print("RESULT:", "PASS" if ok else "FAIL", "(mean saving above target)")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(f"RESULT: INVALID, {e}")
        sys.exit(2)
