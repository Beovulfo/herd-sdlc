#!/usr/bin/env python3
"""Independent check of the routeopt.py solution produced in the live Herd run.

Adapter version of verify_independent.py: this solution has its own formats (positions are
(row, col), products are a list), so it is imported as a module. It still generates its own
stores and baskets from unseen seeds, validates every step stream itself, compares against
a stronger baseline (list order) and a brute-force optimum, and checks the 20 percent claim.

Usage: verify_routeopt.py PROJECT_DIR [--baskets N] [--seed-base S]
"""
import argparse
import itertools
import statistics
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from verify_independent import make_list, make_store  # noqa: E402

PICK_S, STEP_S = 5.0, 1.0


def bfs(grid, src):
    d, q = {src: 0}, deque([src])
    while q:
        r, c = q.popleft()
        for n in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
            if grid[n[0]][n[1]] == "." and n not in d:
                d[n] = d[(r, c)] + 1
                q.append(n)
    return d


def validate(grid, start, cells, steps, algo):
    pos, dist, last_t, picked = start, 0, -1e-9, set()
    for s in steps:
        if s.pos != pos:
            assert abs(s.pos[0] - pos[0]) + abs(s.pos[1] - pos[1]) == 1, f"{algo}: non-adjacent move"
            assert grid[s.pos[0]][s.pos[1]] == ".", f"{algo}: walked into a wall"
            dist += 1
        assert s.dist == dist, f"{algo}: distance wrong"
        assert s.t >= last_t, f"{algo}: time went backwards"
        last_t, pos = s.t, s.pos
        if s.event.startswith("pick "):
            pid = s.event.split()[1]
            assert cells[pid] == pos, f"{algo}: {pid} picked away from its cell"
            picked.add(pid)
    assert picked == set(cells), f"{algo}: picked {len(picked)} of {len(cells)}"
    return steps[-1].t, steps[-1].dist


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--baskets", type=int, default=20)
    ap.add_argument("--seed-base", type=int, default=9001)
    a = ap.parse_args()
    sys.path.insert(0, str(Path(a.project)))
    import routeopt

    rows, exact_checked, exact_ok = [], 0, 0
    for b in range(a.baskets):
        seed = a.seed_base + b
        store, k = make_store(seed), 6 + b % 10
        items = make_list(store, seed, k)["items"]
        grid = store["grid"]
        start = (store["start"][1], store["start"][0])
        prods = [{"id": pid, "name": p["name"], "pos": [p["cell"][1], p["cell"][0]]}
                 for pid, p in store["products"].items()]
        st = routeopt.Store.from_dict({"grid": grid, "start": list(start), "products": prods})
        ids = [i["id"] for i in items]
        cells = {pid: (store["products"][pid]["cell"][1], store["products"][pid]["cell"][0]) for pid in ids}
        t_opt, d_opt = validate(grid, start, cells, list(routeopt.simulate(st, ids, "optimized")), "optimized")
        rnd = [validate(grid, start, cells, list(routeopt.simulate(st, ids, "random", s)), "random")
               for s in range(5)]
        # stronger baseline: items in list order by shortest paths
        stops, d_lst = [start] + [cells[i] for i in ids], 0
        for x, y in zip(stops, stops[1:]):
            d_lst += bfs(grid, x)[y]
        t_lst = d_lst * STEP_S + PICK_S * len(ids)
        # brute-force optimum for small baskets
        if k <= 7:
            dm = {p: bfs(grid, p) for p in set(stops)}
            best = min(sum(dm[x][y] for x, y in zip((start,) + perm, perm))
                       for perm in itertools.permutations([cells[i] for i in ids]))
            exact_checked += 1
            exact_ok += d_opt == best
        rows.append({"k": k, "opt": (t_opt, d_opt), "rnd": (statistics.mean(r[0] for r in rnd),
                                                          statistics.mean(r[1] for r in rnd)), "lst": (t_lst, d_lst)})
    m = lambda key, i: statistics.mean(r[key][i] for r in rows)
    save_r, save_l = 1 - m("opt", 0) / m("rnd", 0), 1 - m("opt", 0) / m("lst", 0)
    worse = sum(r["opt"][0] > r["lst"][0] for r in rows)
    per_basket_min = min(1 - r["opt"][0] / r["rnd"][0] for r in rows)
    print(f"baskets: {len(rows)} stores and lists (6 to 15 items) from seeds {a.seed_base}.., all step streams valid")
    print("| algorithm | mean time (s) | mean distance (cells) |\n| --- | --- | --- |")
    for name, key in (("optimized", "opt"), ("random walk (mean of 5 seeds)", "rnd"), ("list order", "lst")):
        print(f"| {name} | {m(key, 0):.1f} | {m(key, 1):.1f} |")
    print(f"time saved vs random walk: {save_r:.1%} (smallest per-basket saving {per_basket_min:.1%}); threshold 20%")
    print(f"time saved vs list order (stronger baseline): {save_l:.1%}; optimized slower than list order on {worse} baskets")
    print(f"optimal on brute-force check: {exact_ok} of {exact_checked} small baskets")
    ok = save_r > 0.20 and exact_ok == exact_checked and worse == 0
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(f"RESULT: INVALID, {e}")
        sys.exit(2)
