#!/usr/bin/env python3
"""Independent check of the no-workflow baseline solution (route.py).

Same idea as verify_routeopt.py, adapted to this solution's formats: it generates its own
stores and baskets from unseen seeds, validates every walk itself, compares against a stronger
baseline (list order) and a brute-force optimum, and checks the 20 percent claim.

Usage: verify_baseline.py PROJECT_DIR [--baskets N] [--seed-base S]
"""
import argparse
import itertools
import statistics
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from verify_independent import make_list, make_store  # noqa: E402

PICK_S, CELL_S = 15.0, 1.0  # this solution's constants


def bfs(grid, src):
    d, q = {src: 0}, deque([src])
    while q:
        r, c = q.popleft()
        for n in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
            if grid[n[0]][n[1]] == "." and n not in d:
                d[n] = d[(r, c)] + 1
                q.append(n)
    return d


def shelf_next_to(grid, cell):
    r, c = cell
    for n in ((r + 1, c), (r - 1, c)):
        if 2 <= n[0] < len(grid) - 2 and grid[n[0]][n[1]] == "#":
            return n
    return None


def validate(grid, start, shelves, path, algo):
    assert path[0] == start and path[-1] == start, f"{algo}: route must start and end at the station"
    for a, b in zip(path, path[1:]):
        assert abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1, f"{algo}: non-adjacent move"
        assert grid[b[0]][b[1]] == ".", f"{algo}: walked into a shelf"
    for pid, sh in shelves.items():
        assert any(abs(p[0] - sh[0]) + abs(p[1] - sh[1]) == 1 for p in path), f"{algo}: never reached {pid}"
    return (len(path) - 1) * CELL_S


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--baskets", type=int, default=20)
    ap.add_argument("--seed-base", type=int, default=9001)
    a = ap.parse_args()
    sys.path.insert(0, str(Path(a.project)))
    import route

    rows, opt_checked, opt_exact, gaps = [], 0, 0, []
    for b in range(a.baskets):
        seed = a.seed_base + b
        store = make_store(seed)
        grid = list(store["grid"])
        start = (store["start"][1], store["start"][0])
        k = 6 + b % 10
        items = make_list(store, seed, k)["items"]
        products, shelves = {}, {}
        for pid, p in store["products"].items():
            sh = shelf_next_to(grid, (p["cell"][1], p["cell"][0]))
            if sh:
                products[pid] = (p["name"], sh)
        ids = [i["id"] for i in items if i["id"] in products][:k]
        if len(ids) < 4:
            continue
        shelves = {pid: products[pid][1] for pid in ids}
        g = [row for row in grid]
        r0, c0 = start
        g[r0] = g[r0][:c0] + "S" + g[r0][c0 + 1:]
        rg = [row.replace("S", ".") for row in g]
        opt = route.optimized_route(g, start, products, ids)
        d_opt = validate(rg, start, shelves, opt, "optimized")
        t_opt = d_opt + PICK_S * len(ids)
        assert route.kpis(opt, products, ids) == (d_opt, t_opt), "reported KPIs differ from my recomputation"
        rnd = []
        for s in range(5):
            w = route.random_walk(g, start, products, ids, s)
            d = validate(rg, start, shelves, w, "random")
            rnd.append((d + PICK_S * len(ids), d))
        pick = {pid: next(c for c in ((sh[0] + 1, sh[1]), (sh[0] - 1, sh[1]), (sh[0], sh[1] + 1), (sh[0], sh[1] - 1))
                          if rg[c[0]][c[1]] == ".") for pid, sh in shelves.items()}
        stops = [start] + [pick[i] for i in ids] + [start]
        d_lst = sum(bfs(rg, x)[y] for x, y in zip(stops, stops[1:]))
        if len(ids) <= 7:
            cells = sorted(set(pick.values()))
            dm = {p: bfs(rg, p) for p in cells + [start]}
            best = min(sum(dm[x][y] for x, y in zip((start,) + perm, perm + (start,)))
                       for perm in itertools.permutations(cells))
            opt_checked += 1
            opt_exact += d_opt == best
            gaps.append(d_opt / best - 1)
        rows.append({"opt": (t_opt, d_opt), "rnd": (statistics.mean(r[0] for r in rnd), statistics.mean(r[1] for r in rnd)),
                     "lst": (d_lst + PICK_S * len(ids), d_lst)})
    m = lambda key, i: statistics.mean(r[key][i] for r in rows)
    save_r, save_l = 1 - m("opt", 0) / m("rnd", 0), 1 - m("opt", 0) / m("lst", 0)
    worse = sum(r["opt"][0] > r["lst"][0] for r in rows)
    print(f"baskets: {len(rows)} stores and lists from seeds {a.seed_base}.., all walks valid, KPIs recomputed")
    print("| algorithm | mean time (s) | mean distance (cells) |\n| --- | --- | --- |")
    for name, key in (("optimized", "opt"), ("random walk (mean of 5 seeds)", "rnd"), ("list order", "lst")):
        print(f"| {name} | {m(key, 0):.1f} | {m(key, 1):.1f} |")
    print(f"time saved vs random walk: {save_r:.1%} (smallest per-basket saving "
          f"{min(1 - r['opt'][0] / r['rnd'][0] for r in rows):.1%}); threshold 20%")
    print(f"time saved vs list order (stronger baseline): {save_l:.1%}; optimized slower than list order on {worse} baskets")
    print(f"brute-force optimum on small baskets: exact on {opt_exact} of {opt_checked}; "
          f"largest gap {max(gaps, default=0):.1%}")
    ok = save_r > 0.20
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(f"RESULT: INVALID, {e}")
        sys.exit(2)
