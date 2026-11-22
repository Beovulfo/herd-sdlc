#!/usr/bin/env python3
"""Supermarket picking-route optimizer with step-by-step KPI simulation (stdlib only).

Map JSON:
  grid      list of strings; '#' = blocked (shelf/wall), '.' = walkable aisle
  entrance  [x, y] aisle cell where the picker starts
  checkout  [x, y] aisle cell where the basket is delivered
  products  [{"id": "P001", "name": "milk", "x": 3, "y": 1}, ...]  (x, y on an aisle cell)

Order JSON: list of product ids, e.g. ["P001", "P017"] or ["P001:milk", ...].

Usage:
  python3 route_optimizer.py MAP.json ORDER.json [--speedup 60] [--target 30]
  python3 route_optimizer.py --make-sample PREFIX [--seed 1]   # writes PREFIX-map.json, PREFIX-order.json
"""
import argparse
import json
import random
import sys
import time
from collections import deque, namedtuple

CELL_M = 1.0      # one grid cell = 1 metre
WALK_MPS = 1.2    # walking speed, metres per second
PICK_S = 6.0      # seconds to pick one item off a shelf

Tick = namedtuple("Tick", "t dist_m pos picked event")


def load_map(path):
    with open(path) as f:
        m = json.load(f)
    grid = m["grid"]
    products = {p["id"]: p for p in m["products"]}
    for p in products.values():
        if grid[p["y"]][p["x"]] == "#":
            raise ValueError(f"product {p['id']} is on a blocked cell")
    return grid, tuple(m["entrance"]), tuple(m["checkout"]), products


def load_order(path, products):
    with open(path) as f:
        raw = json.load(f)
    ids = [str(s).split(":")[0].strip() for s in raw]
    missing = [i for i in ids if i not in products]
    if missing:
        raise SystemExit(f"unknown product ids in order: {missing}")
    return ids


def bfs_parents(grid, src):
    h, w = len(grid), len(grid[0])
    parent = {src: None}
    q = deque([src])
    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and grid[ny][nx] != "#" and (nx, ny) not in parent:
                parent[(nx, ny)] = (x, y)
                q.append((nx, ny))
    return parent


def path_cells(parent, dst):
    if dst not in parent:
        raise ValueError(f"stop {dst} unreachable from aisle network")
    out, c = [], dst
    while c is not None:
        out.append(c)
        c = parent[c]
    return out[::-1]


def distances(grid, stops):
    """D[i][j] = steps between stops; P[i][j] = cell path from stop i to stop j."""
    parents = [bfs_parents(grid, s) for s in stops]
    P = [[path_cells(parents[i], stops[j]) for j in range(len(stops))] for i in range(len(stops))]
    D = [[len(P[i][j]) - 1 for j in range(len(stops))] for i in range(len(stops))]
    return D, P


def route_steps(route, D):
    return sum(D[a][b] for a, b in zip(route, route[1:]))


def nearest_neighbour(D, n):
    """Route over stop indices: 0 = entrance, 1..n = items, n+1 = checkout."""
    route, left = [0], set(range(1, n + 1))
    while left:
        nxt = min(left, key=lambda j: (D[route[-1]][j], j))
        route.append(nxt)
        left.remove(nxt)
    return route + [n + 1]


def two_opt(route, D):
    # ponytail: 2-opt local search, not provably optimal. Add exact Held-Karp if n <= 12 must be optimal.
    improved = True
    while improved:
        improved = False
        for i in range(1, len(route) - 2):
            for k in range(i + 1, len(route) - 1):
                a, b, c, d = route[i - 1], route[i], route[k], route[k + 1]
                if D[a][c] + D[b][d] < D[a][b] + D[c][d]:
                    route[i:k + 1] = route[i:k + 1][::-1]
                    improved = True
    return route


def run_route(route, paths, names, n):
    """Walk the route one grid cell at a time. Yields a Tick per step, per pick and at checkout."""
    t = dist = 0.0
    picked = 0
    pos = paths[0][0]
    for leg, path in enumerate(paths):
        for cell in path[1:]:
            t += CELL_M / WALK_MPS
            dist += CELL_M
            pos = cell
            yield Tick(t, dist, pos, picked, None)
        if leg + 1 <= n:  # arrived at an item stop (not checkout)
            t += PICK_S
            picked += 1
            yield Tick(t, dist, pos, picked, f"picked {names[route[leg + 1]]}")
    yield Tick(t, dist, pos, picked, "BASKET READY")


def play(label, route, paths, names, n, speedup):
    prev, last = 0.0, None
    for tick in run_route(route, paths, names, n):
        if speedup:
            time.sleep(max(0.0, (tick.t - prev) / speedup))
        prev = tick.t
        last = tick
        if tick.event:
            print(f"[{label:>10}] t={tick.t:7.1f}s  dist={tick.dist_m:6.1f}m  "
                  f"picked={tick.picked:2d}/{n}  {tick.event}")
    return last


def make_sample(seed):
    """Deterministic demo supermarket: 61x31 grid, shelf columns, 120 products, 25-item order."""
    rng = random.Random(seed)
    W, H = 61, 31
    grid = [["."] * W for _ in range(H)]
    shelf_xs = list(range(6, 55, 6))
    for sx in shelf_xs:
        for y in range(3, H - 3):
            if y != 15:  # cross-aisle gap
                grid[y][sx] = "#"
    cands = [(x, y) for sx in shelf_xs for x in (sx - 1, sx + 1) for y in range(2, H - 2)
             if grid[y][x] == "."]
    names_pool = ["milk", "bread", "eggs", "rice", "pasta", "tomato", "onion", "apple", "banana",
                  "cheese", "yogurt", "butter", "water", "juice", "coffee", "tea", "sugar", "flour",
                  "salt", "oil", "soap", "shampoo", "paper", "detergent", "chicken", "beef", "fish",
                  "carrot", "potato", "lettuce", "lemon", "cereal", "honey", "jam", "chips",
                  "cookies", "beans", "corn", "ham", "wine"]
    spots = rng.sample(cands, 120)
    products = [{"id": f"P{i + 1:03d}", "name": rng.choice(names_pool), "x": x, "y": y}
                for i, (x, y) in enumerate(spots)]
    m = {"grid": ["".join(r) for r in grid], "entrance": [0, H - 1], "checkout": [W - 1, H - 1],
         "products": products}
    order = [p["id"] + ":" + p["name"] for p in rng.sample(products, 25)]
    return m, order


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("map", nargs="?")
    ap.add_argument("order", nargs="?")
    ap.add_argument("--speedup", type=float, default=0.0,
                    help="simulated seconds per real second (0 = as fast as possible)")
    ap.add_argument("--target", type=float, default=30.0, help="required time saving in percent")
    ap.add_argument("--make-sample", metavar="PREFIX", help="write a demo map and order, then exit")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args(argv)

    if args.make_sample:
        m, order = make_sample(args.seed)
        with open(args.make_sample + "-map.json", "w") as f:
            json.dump(m, f, indent=1)
        with open(args.make_sample + "-order.json", "w") as f:
            json.dump(order, f, indent=1)
        print(f"wrote {args.make_sample}-map.json and {args.make_sample}-order.json")
        return 0
    if not (args.map and args.order):
        ap.error("MAP and ORDER are required")

    grid, entrance, checkout, products = load_map(args.map)
    ids = load_order(args.order, products)
    n = len(ids)
    stops = [entrance] + [(products[i]["x"], products[i]["y"]) for i in ids] + [checkout]
    names = ["ENTRANCE"] + [products[i]["name"] for i in ids] + ["CHECKOUT"]
    D, P = distances(grid, stops)

    routes = {
        "list-order": list(range(n + 2)),
        "optimized": two_opt(nearest_neighbour(D, n), D),
    }
    results = {}
    for label, route in routes.items():
        paths = [P[a][b] for a, b in zip(route, route[1:])]
        print(f"--- {label} route: {' -> '.join(names[i] for i in route)}")
        results[label] = play(label, route, paths, names, n, args.speedup)

    base, opt = results["list-order"], results["optimized"]
    saving_t = 100.0 * (1 - opt.t / base.t)
    saving_d = 100.0 * (1 - opt.dist_m / base.dist_m)
    print()
    print(f"{'KPI':<22}{'list-order':>14}{'optimized':>14}{'saving':>10}")
    print(f"{'time-to-prepare (s)':<22}{base.t:>14.1f}{opt.t:>14.1f}{saving_t:>9.1f}%")
    print(f"{'distance-covered (m)':<22}{base.dist_m:>14.1f}{opt.dist_m:>14.1f}{saving_d:>9.1f}%")
    ok = saving_t > args.target
    print(f"target: time saving > {args.target:.0f}%  ->  {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
