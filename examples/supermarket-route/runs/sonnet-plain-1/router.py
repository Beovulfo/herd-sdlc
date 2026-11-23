#!/usr/bin/env python3
"""Supermarket pick-route optimizer + step-by-step simulator. Stdlib only.

  python3 router.py gen --out store.json --list list.txt   # sample big store + list
  python3 router.py run store.json list.txt [--steps]      # optimize, simulate, compare

Map JSON: {"grid": ["#..#", ...], "start": [x,y], "end": [x,y],
           "products": [{"id": "P1", "name": "milk", "x": 3, "y": 5}, ...]}
Grid: '#' = shelf/wall (blocked), anything else walkable. A product on a blocked
cell is picked from a walkable neighbour (the one nearest the start).
List file: one "id:short name" per line (only the id is used for lookup).
"""
import argparse, json, random, sys
from collections import deque

WALK_MPS, CELL_M, PICK_S = 1.2, 1.0, 5.0  # walking speed, metres per cell, seconds per pick (tunable)
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def bfs(grid, src):
    """Distance map (dict cell->steps) and parents from src over walkable cells."""
    h, w = len(grid), len(grid[0])
    dist, par, q = {src: 0}, {src: None}, deque([src])
    while q:
        c = q.popleft()
        for dx, dy in DIRS:
            n = (c[0] + dx, c[1] + dy)
            if 0 <= n[0] < w and 0 <= n[1] < h and grid[n[1]][n[0]] != '#' and n not in dist:
                dist[n], par[n] = dist[c] + 1, c
                q.append(n)
    return dist, par


def load(map_path, list_path):
    m = json.load(open(map_path))
    grid = m["grid"]
    start, end = tuple(m["start"]), tuple(m["end"])
    prods = {p["id"]: p for p in m["products"]}
    d0, _ = bfs(grid, start)
    items = []
    for line in open(list_path):
        line = line.strip()
        if not line:
            continue
        pid = line.split(":", 1)[0].strip()
        if pid not in prods:
            sys.exit(f"unknown product id: {pid}")
        p = prods[pid]
        cell = (p["x"], p["y"])
        if grid[cell[1]][cell[0]] == '#':
            opts = [(cell[0] + dx, cell[1] + dy) for dx, dy in DIRS]
            opts = [o for o in opts if o in d0]  # in-bounds, walkable, reachable
            if not opts:
                sys.exit(f"product {pid} not reachable")
            cell = min(opts, key=d0.get)
        elif cell not in d0:
            sys.exit(f"product {pid} not reachable")
        items.append((pid, p["name"], cell))
    return grid, start, end, items


def dist_matrix(grid, pts):
    d = []
    for p in pts:
        dm, _ = bfs(grid, p)
        d.append([dm[q] for q in pts])
    return d


def optimize(d):
    """Order of items 1..n-2 between fixed node 0 (start) and n-1 (end): NN + 2-opt + or-opt.
    ponytail: local search, not exact; add Held-Karp/LKH only if quality matters at <15 items."""
    n = len(d)
    left, tour = set(range(1, n - 1)), [0]
    while left:
        nxt = min(left, key=lambda j: d[tour[-1]][j])
        tour.append(nxt); left.remove(nxt)
    tour.append(n - 1)
    cost = lambda t: sum(d[a][b] for a, b in zip(t, t[1:]))
    best, improved = cost(tour), True
    while improved:
        improved = False
        for i in range(1, n - 1):
            for j in range(i + 1, n - 1):  # 2-opt: reverse tour[i..j]
                t = tour[:i] + tour[i:j + 1][::-1] + tour[j + 1:]
                if cost(t) < best:
                    tour, best, improved = t, cost(t), True
        for i in range(1, n - 1):  # or-opt: move one node elsewhere
            for j in range(1, n - 1):
                if i == j:
                    continue
                t = tour[:]; v = t.pop(i); t.insert(j, v)
                if cost(t) < best:
                    tour, best, improved = t, cost(t), True
    return tour


def simulate(grid, stops):
    """Yield (step_no, cell, event, dist_cells, seconds) one cell at a time. stops = [(label, cell)].
    Walking and picking advance the clock; event is None while walking, else the pick label."""
    pos, dist, t, k = stops[0][1], 0, 0.0, 0
    for label, cell in stops[1:]:
        _, par = bfs(grid, cell)  # parents point toward `cell`
        while pos != cell:
            pos = par[pos]; dist += 1; t += CELL_M / WALK_MPS; k += 1
            yield k, pos, None, dist, t
        if label:
            t += PICK_S
            yield k, pos, label, dist, t


def route_stops(start, end, items, order):
    return [("", start)] + [(f"{items[i][0]}:{items[i][1]}", items[i][2]) for i in order] + [("", end)]


def run_route(grid, stops, name, show_steps):
    last = (0, 0, 0)
    for k, cell, ev, dist, t in simulate(grid, stops):
        last = (k, dist, t)
        if ev:
            print(f"[{name}] t={t:8.1f}s  dist={dist * CELL_M:7.1f}m  picked {ev}")
        elif show_steps:
            print(f"[{name}] step {k:6d} at {cell}  t={t:8.1f}s  dist={dist * CELL_M:7.1f}m")
    return last[1] * CELL_M, last[2]


def cmd_run(a):
    grid, start, end, items = load(a.map, a.list)
    pts = [start] + [c for _, _, c in items] + [end]
    d = dist_matrix(grid, pts)
    opt = optimize(d)[1:-1]
    base = list(range(1, len(items) + 1))
    res = {}
    for name, order in (("list-order", base), ("optimized", opt)):
        res[name] = run_route(grid, route_stops(start, end, items, [i - 1 for i in order]), name, a.steps)
    (d0, t0), (d1, t1) = res["list-order"], res["optimized"]
    print(f"\nitems={len(items)} map={len(grid[0])}x{len(grid)}")
    print(f"{'':12}{'distance-covered':>18}{'time-to-prepare-basket':>26}")
    for n, (dd, tt) in res.items():
        print(f"{n:12}{dd:16.1f} m{tt:22.1f} s ({tt / 60:.1f} min)")
    sav = 100 * (t0 - t1) / t0
    print(f"time saved: {sav:.1f}%  distance saved: {100 * (d0 - d1) / d0:.1f}%  "
          f"{'PASS' if sav > 30 else 'FAIL'} (target >30%)")
    return sav


def cmd_gen(a):
    rnd = random.Random(a.seed)
    W, H = a.width, a.height
    grid = [["."] * W for _ in range(H)]
    shelf = []
    for y in range(2, H - 2):
        if (y - 2) % 3 == 2:
            continue  # aisle row
        for x in range(2, W - 2):
            if (x - 2) % 25 not in (23, 24):  # vertical cross aisles
                grid[y][x] = '#'; shelf.append((x, y))
    cells = rnd.sample(shelf, min(a.products, len(shelf)))
    prods = [{"id": f"P{i}", "name": f"item{i}", "x": x, "y": y} for i, (x, y) in enumerate(cells)]
    json.dump({"grid": ["".join(r) for r in grid], "start": [0, H - 1], "end": [W - 1, H - 1],
               "products": prods}, open(a.out, "w"))
    with open(a.list, "w") as f:
        for p in rnd.sample(prods, a.items):
            f.write(f"{p['id']}:{p['name']}\n")
    print(f"wrote {a.out} ({W}x{H}, {len(prods)} products) and {a.list} ({a.items} items)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen")
    g.add_argument("--out", default="store.json"); g.add_argument("--list", default="list.txt")
    g.add_argument("--width", type=int, default=200); g.add_argument("--height", type=int, default=120)
    g.add_argument("--products", type=int, default=3000); g.add_argument("--items", type=int, default=40)
    g.add_argument("--seed", type=int, default=1); g.set_defaults(f=cmd_gen)
    r = sub.add_parser("run")
    r.add_argument("map"); r.add_argument("list")
    r.add_argument("--steps", action="store_true", help="print every single step, not just picks")
    r.set_defaults(f=cmd_run)
    a = ap.parse_args(); a.f(a)
