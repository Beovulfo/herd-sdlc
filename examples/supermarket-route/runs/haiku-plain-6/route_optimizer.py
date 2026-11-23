#!/usr/bin/env python3
"""Supermarket route optimizer with a live step-by-step simulator (stdlib only).

Store map (JSON):
  {
    "cell_size_m": 1.0,                      # metres per grid cell (optional)
    "layout": ["##########", "#...#....#"],  # '#' = blocked, any other char = walkable
    "entrance": [x, y],                      # where the delivery guy starts
    "checkout": [x, y],                      # where the basket is delivered (default: entrance)
    "products": [{"id": "P0001", "name": "milk", "x": 2, "y": 1}]
  }
A product may sit on a blocked cell (a shelf); it is picked from an adjacent walkable cell.

Order file: tokens "id:name" or "id" separated by commas or whitespace.

Usage:
  python3 route_optimizer.py gen   --width 120 --height 80 --products 400 --seed 1 > store.json
  python3 route_optimizer.py run   store.json order.txt [--trace] [--sleep 0.02]
  python3 route_optimizer.py bench store.json --orders 200 --items 25 --seed 1

KPIs: time-to-prepare-basket (s, includes the walk to checkout) and distance-covered (m).
Times use WALK_SPEED_MPS and PICK_TIME_S below.
"""

import argparse
import collections
import json
import random
import re
import statistics
import sys
import time

WALK_SPEED_MPS = 1.2
PICK_TIME_S = 5.0
NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1))
HELD_KARP_MAX_ITEMS = 10  # exact DP up to this many items, NN + 2-opt above it


class Store:
    def __init__(self, data):
        self.layout = data["layout"]
        self.h = len(self.layout)
        self.w = len(self.layout[0])
        self.cell_m = float(data.get("cell_size_m", 1.0))
        self.entrance = tuple(data["entrance"])
        self.checkout = tuple(data.get("checkout", data["entrance"]))
        self.products = {p["id"]: p for p in data["products"]}
        self.by_name = {p["name"]: p["id"] for p in data["products"]}
        for cell in (self.entrance, self.checkout):
            if not self.walkable(*cell):
                raise ValueError(f"entrance/checkout {cell} is blocked")

    def walkable(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h and self.layout[y][x] != "#"

    def neighbours(self, x, y):
        for dx, dy in NEIGHBOURS:
            if self.walkable(x + dx, y + dy):
                yield (x + dx, y + dy)

    def access(self, pid):
        p = self.products[pid]
        cell = (p["x"], p["y"])
        if self.walkable(*cell):
            return cell
        for c in self.neighbours(*cell):
            return c
        raise ValueError(f"product {pid} has no walkable access cell")

    def resolve(self, token):
        """Accept 'id:name', 'id' or 'name'; return the product id."""
        key = token.split(":", 1)[0].strip()
        if key in self.products:
            return key
        if token.strip() in self.by_name:
            return self.by_name[token.strip()]
        if key in self.by_name:
            return self.by_name[key]
        raise ValueError(f"unknown product in order: {token!r}")


def bfs(store, src, dst=None):
    """Breadth-first search from src. Stops early once dst is found. Returns (dist, parent)."""
    dist = {src: 0}
    parent = {src: None}
    queue = collections.deque([src])
    while queue:
        cur = queue.popleft()
        if cur == dst:
            break
        for nxt in store.neighbours(*cur):
            if nxt not in dist:
                dist[nxt] = dist[cur] + 1
                parent[nxt] = cur
                queue.append(nxt)
    return dist, parent


def distance_matrix(store, cells):
    """Shortest walking distance (in cells) between every pair of cells."""
    matrix = []
    for src in cells:
        dist, _ = bfs(store, src)
        row = []
        for dst in cells:
            if dst not in dist:
                raise ValueError(f"cell {dst} is unreachable from {src}")
            row.append(dist[dst])
        matrix.append(row)
    return matrix


def held_karp(D):
    """Exact shortest open path 0 -> ... -> n-1 visiting all other nodes."""
    n = len(D)
    mids = list(range(1, n - 1))
    m = len(mids)
    if m == 0:
        return [0, n - 1]
    inf = float("inf")
    dp = [[inf] * m for _ in range(1 << m)]
    par = [[-1] * m for _ in range(1 << m)]
    for j, v in enumerate(mids):
        dp[1 << j][j] = D[0][v]
    for mask in range(1, 1 << m):
        for j in range(m):
            cur = dp[mask][j]
            if cur == inf or not mask >> j & 1:
                continue
            for k in range(m):
                if mask >> k & 1:
                    continue
                nmask = mask | 1 << k
                cand = cur + D[mids[j]][mids[k]]
                if cand < dp[nmask][k]:
                    dp[nmask][k] = cand
                    par[nmask][k] = j
    full = (1 << m) - 1
    last = min(range(m), key=lambda j: dp[full][j] + D[mids[j]][n - 1])
    order, mask, j = [], full, last
    while j != -1:
        order.append(mids[j])
        prev = par[mask][j]
        mask ^= 1 << j
        j = prev
    return [0] + order[::-1] + [n - 1]


def nearest_neighbour_2opt(D):
    """Greedy nearest neighbour, then 2-opt until no reversal shortens the path."""
    n = len(D)
    left = set(range(1, n - 1))
    path = [0]
    while left:
        nxt = min(left, key=lambda v: D[path[-1]][v])
        left.remove(nxt)
        path.append(nxt)
    path.append(n - 1)
    improved = True
    while improved:
        improved = False
        for i in range(1, n - 2):
            for j in range(i + 1, n - 1):
                a, b, c, d = path[i - 1], path[i], path[j], path[j + 1]
                if D[a][c] + D[b][d] < D[a][b] + D[c][d] - 1e-9:
                    path[i:j + 1] = path[i:j + 1][::-1]
                    improved = True
    return path


def optimize_order(D):
    """Visiting order (indexes into D; 0 = entrance, n-1 = checkout)."""
    if len(D) - 2 <= HELD_KARP_MAX_ITEMS:
        return held_karp(D)
    # ponytail: NN + 2-opt is a local optimum; add Or-opt if savings matter at 30+ items
    return nearest_neighbour_2opt(D)


def plan(store, product_ids):
    """Return (list-order route, optimized route). A route is [(cell, product_id or None)]."""
    cells = [store.entrance] + [store.access(p) for p in product_ids] + [store.checkout]
    labels = [None] + list(product_ids) + [None]
    D = distance_matrix(store, cells)
    baseline = list(range(len(cells)))
    optimized = optimize_order(D)
    return ([(cells[i], labels[i]) for i in baseline],
            [(cells[i], labels[i]) for i in optimized])


def walk(store, route):
    """Simulate the walk cell by cell. Yields one KPI snapshot per step, pick and arrival."""
    step_s = store.cell_m / WALK_SPEED_MPS
    total_picks = sum(1 for _, pid in route if pid is not None)
    t, dist_m, picked, steps = 0.0, 0.0, 0, 0
    pos = route[0][0]

    def snap(event):
        return {"t_s": round(t, 2), "distance_m": round(dist_m, 2), "steps": steps,
                "picked": picked, "remaining": total_picks - picked,
                "cell": pos, "event": event}

    yield snap("start")
    for (src, _), (dst, pid) in zip(route, route[1:]):
        _, parent = bfs(store, src, dst)
        if dst not in parent:
            raise ValueError(f"no path from {src} to {dst}")
        leg = []
        cur = dst
        while cur != src:
            leg.append(cur)
            cur = parent[cur]
        for cell in reversed(leg):
            t += step_s
            dist_m += store.cell_m
            steps += 1
            pos = cell
            yield snap("step")
        if pid is not None:
            t += PICK_TIME_S
            picked += 1
            yield snap(f"picked {pid}")
    yield snap("basket ready at checkout")


def run_route(store, route, on_snap=None):
    final = None
    for final in walk(store, route):
        if on_snap:
            on_snap(final)
    return final


def parse_order(store, text):
    tokens = [t for t in re.split(r"[,\s]+", text.strip()) if t]
    seen = []
    for tok in tokens:
        pid = store.resolve(tok)
        if pid not in seen:
            seen.append(pid)
    return seen


def load_store(path):
    with open(path, encoding="utf-8") as fh:
        return Store(json.load(fh))


def fmt_snap(s):
    return (f"t={s['t_s']:8.1f}s  dist={s['distance_m']:8.1f}m  "
            f"picked={s['picked']:3d}  left={s['remaining']:3d}  {s['event']}")


def cmd_run(args):
    store = load_store(args.map)
    with open(args.order, encoding="utf-8") as fh:
        pids = parse_order(store, fh.read())
    base, opt = plan(store, pids)
    results = {}
    for name, route in (("list-order", base), ("optimized", opt)):
        print(f"== {name} route ({len(pids)} items) ==")

        def show(s):
            if args.trace or s["event"] != "step":
                print(fmt_snap(s), flush=True)
            if args.sleep and s["event"] == "step":
                time.sleep(args.sleep)

        results[name] = run_route(store, route, show)
    b, o = results["list-order"], results["optimized"]
    time_saving = 100.0 * (b["t_s"] - o["t_s"]) / b["t_s"]
    dist_saving = 100.0 * (b["distance_m"] - o["distance_m"]) / b["distance_m"]
    print("== comparison ==")
    print(f"time-to-prepare-basket  list-order {b['t_s']:.1f}s  optimized {o['t_s']:.1f}s  "
          f"saving {time_saving:.1f}%")
    print(f"distance-covered        list-order {b['distance_m']:.1f}m  optimized {o['distance_m']:.1f}m  "
          f"saving {dist_saving:.1f}%")
    return 0


def cmd_bench(args):
    store = load_store(args.map)
    rng = random.Random(args.seed)
    ids = list(store.products)
    savings = []
    for _ in range(args.orders):
        pids = rng.sample(ids, min(args.items, len(ids)))
        base, opt = plan(store, pids)
        b = run_route(store, base)
        o = run_route(store, opt)
        savings.append(100.0 * (b["t_s"] - o["t_s"]) / b["t_s"])
    hit = sum(1 for s in savings if s >= 30.0)
    print(f"orders={len(savings)} items={args.items}")
    print(f"time saving: mean {statistics.mean(savings):.1f}%  median {statistics.median(savings):.1f}%  "
          f"min {min(savings):.1f}%  max {max(savings):.1f}%")
    print(f"orders with >=30% saving: {hit}/{len(savings)}")
    return 0


WORDS = ["milk", "bread", "eggs", "rice", "pasta", "tomato", "onion", "apple", "banana",
         "cheese", "yogurt", "butter", "coffee", "tea", "sugar", "flour", "salt", "oil",
         "water", "juice", "wine", "soap", "shampoo", "cereal", "honey", "jam", "ham",
         "chicken", "fish", "carrot", "lettuce", "potato", "lemon", "beans", "soup", "nuts"]


def gen_store(width, height, n_products, seed):
    """Synthetic store: outer walls, shelving columns every 4 cells, open cross aisles."""
    rng = random.Random(seed)
    grid = [["." for _ in range(width)] for _ in range(height)]
    for x in range(width):
        grid[0][x] = grid[height - 1][x] = "#"
    for y in range(height):
        grid[y][0] = grid[y][width - 1] = "#"
    shelf_cells = []
    for x in range(3, width - 3, 4):
        for y in range(2, height - 4):
            grid[y][x] = "#"
            shelf_cells.append((x, y))
    if n_products > len(shelf_cells):
        raise ValueError(f"store has room for {len(shelf_cells)} products at most")
    spots = rng.sample(shelf_cells, n_products)
    products = []
    for i, (x, y) in enumerate(spots):
        name = f"{WORDS[i % len(WORDS)]}-{i}"
        products.append({"id": f"P{i + 1:04d}", "name": name, "x": x, "y": y})
    return {"cell_size_m": 1.0,
            "layout": ["".join(row) for row in grid],
            "entrance": [width // 2, height - 3],
            "checkout": [width - 2, height - 3],
            "products": products}


def cmd_gen(args):
    data = gen_store(args.width, args.height, args.products, args.seed)
    print(json.dumps(data, indent=1))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("gen", help="generate a synthetic store map (JSON on stdout)")
    p.add_argument("--width", type=int, default=60)
    p.add_argument("--height", type=int, default=40)
    p.add_argument("--products", type=int, default=200)
    p.add_argument("--seed", type=int, default=1)
    p.set_defaults(func=cmd_gen)

    p = sub.add_parser("run", help="simulate one order: list-order vs optimized")
    p.add_argument("map")
    p.add_argument("order")
    p.add_argument("--trace", action="store_true", help="print every step, not only picks")
    p.add_argument("--sleep", type=float, default=0.0, help="real-time pause per step (s)")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("bench", help="random orders: distribution of time savings")
    p.add_argument("map")
    p.add_argument("--orders", type=int, default=100)
    p.add_argument("--items", type=int, default=20)
    p.add_argument("--seed", type=int, default=1)
    p.set_defaults(func=cmd_bench)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
