#!/usr/bin/env python3
"""Picking route optimizer for a supermarket, with a step-by-step simulator.

Map file (JSON):
  {"grid": ["#####", "#...#", ...],          "#" = blocked (wall, shelf), anything else walkable
   "entrance": [x, y], "checkout": [x, y],   x = column, y = row
   "products": [{"id": "P1", "name": "Milk", "x": 3, "y": 1}]}
A product on a blocked cell is picked from its first walkable neighbour.

Basket file (text): one "id:short name" per line. Blank lines and "#" comments are skipped.

Usage:
  route_optimizer.py generate --rows 200 --cols 300 --products 3000 --basket 25 \
                              --map store.json --list basket.txt
  route_optimizer.py run store.json basket.txt [--delay 0.01]
"""

import argparse
import json
import random
import time
from array import array
from collections import deque

CELL_M = 1.0     # metres per grid cell
WALK_MPS = 1.2   # walking speed, metres per second
PICK_S = 8.0     # seconds to pick one item


class Store:
    def __init__(self, data):
        self.grid = data["grid"]
        self.h = len(self.grid)
        self.w = len(self.grid[0])
        self.open = bytearray(self.w * self.h)  # 1 = walkable, indexed y * w + x
        for y, row in enumerate(self.grid):
            for x, ch in enumerate(row):
                self.open[y * self.w + x] = ch != "#"
        self.entrance = self.access(*data["entrance"])
        self.checkout = self.access(*data["checkout"])
        self.products = {p["id"]: (p["name"], self.access(p["x"], p["y"])) for p in data["products"]}

    def access(self, x, y):
        """Flat index of the walkable cell used to reach (x, y)."""
        for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < self.w and 0 <= ny < self.h and self.open[ny * self.w + nx]:
                return ny * self.w + nx
        raise ValueError(f"no walkable cell at or next to ({x}, {y})")


def bfs(store, src):
    """Walk distance in cells and parent cell from src to every cell (-1 = unreachable)."""
    w, n = store.w, store.w * store.h
    dist = array("i", [-1]) * n
    parent = array("i", [-1]) * n
    dist[src] = 0
    queue = deque([src])
    while queue:
        c = queue.popleft()
        x = c % w
        nbrs = []
        if x > 0:
            nbrs.append(c - 1)
        if x < w - 1:
            nbrs.append(c + 1)
        if c >= w:
            nbrs.append(c - w)
        if c + w < n:
            nbrs.append(c + w)
        for nb in nbrs:
            if store.open[nb] and dist[nb] < 0:
                dist[nb] = dist[c] + 1
                parent[nb] = c
                queue.append(nb)
    return dist, parent


def order_stops(cells, trees):
    """Visit order over cells (index 0 = entrance, last = checkout), as indices into cells.

    Nearest neighbour from the entrance, then 2-opt until no swap shortens the walk.
    ponytail: heuristic, not optimal; add Or-opt or an exact solver if baskets get big.
    """
    def d(i, j):
        return trees[cells[i]][0][cells[j]]

    rest = list(range(1, len(cells) - 1))
    tour = [0]
    while rest:
        nxt = min(rest, key=lambda j: d(tour[-1], j))
        rest.remove(nxt)
        tour.append(nxt)
    tour.append(len(cells) - 1)

    improved = True
    while improved:
        improved = False
        for i in range(1, len(tour) - 2):
            for j in range(i + 1, len(tour) - 1):
                a, b, c, e = tour[i - 1], tour[i], tour[j], tour[j + 1]
                if d(a, c) + d(b, e) < d(a, b) + d(c, e):
                    tour[i:j + 1] = tour[i:j + 1][::-1]
                    improved = True
    return tour


def route_cells(parent, src, dst):
    """Cells walked from src to dst, excluding src and including dst."""
    out = []
    c = dst
    while c != src:
        out.append(c)
        c = parent[c]
    return out[::-1]


def simulate(store, trees, cells, labels, tour):
    """Yield a KPI snapshot after every step, every pick and at the end."""
    steps = picks = 0
    dist_m = elapsed = 0.0

    def snap(cell, event):
        return {"step": steps, "x": cell % store.w, "y": cell // store.w,
                "elapsed_s": elapsed, "distance_m": dist_m, "picked": picks, "event": event}

    yield snap(cells[tour[0]], "start")
    for a, b in zip(tour, tour[1:]):
        for c in route_cells(trees[cells[a]][1], cells[a], cells[b]):
            steps += 1
            dist_m += CELL_M
            elapsed += CELL_M / WALK_MPS
            yield snap(c, None)
        if labels[b] is not None:
            picks += 1
            elapsed += PICK_S
            yield snap(cells[b], f"picked {labels[b]}")
    yield snap(cells[tour[-1]], "basket ready")


def read_basket(path, store):
    items = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            pid, _, name = line.partition(":")
            pid = pid.strip()
            if pid not in store.products:
                raise SystemExit(f"unknown product id in basket: {pid}")
            pname, cell = store.products[pid]
            items.append((pid, name.strip() or pname, cell))
    return items


def hms(seconds):
    s = int(round(seconds))
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}"


def cmd_run(args):
    with open(args.map) as f:
        store = Store(json.load(f))
    basket = read_basket(args.basket, store)
    cells = [store.entrance] + [cell for _, _, cell in basket] + [store.checkout]
    labels = [None] + [f"{pid} {name}" for pid, name, _ in basket] + [None]
    trees = {c: bfs(store, c) for c in set(cells)}
    if any(trees[store.entrance][0][c] < 0 for c in cells):
        raise SystemExit("some basket products cannot be reached from the entrance")

    results = {}
    routes = (("list-order", list(range(len(cells)))), ("optimized", order_stops(cells, trees)))
    for name, tour in routes:
        print(f"== {name} route ({len(basket)} items) ==")
        last = None
        for snap in simulate(store, trees, cells, labels, tour):
            last = snap
            if snap["event"]:
                print(f"  step {snap['step']:>7}  at ({snap['x']},{snap['y']})  "
                      f"t={hms(snap['elapsed_s'])}  dist={snap['distance_m']:9.1f} m  "
                      f"{snap['event']}")
            if args.delay:
                time.sleep(args.delay)
        results[name] = last

    base, opt = results["list-order"], results["optimized"]

    def saved(a, b):
        return 100.0 * (a - b) / a if a else 0.0

    print("== comparison ==")
    print(f"{'route':<12}{'time-to-prepare':>18}{'distance':>16}{'steps':>10}")
    for name, r in results.items():
        print(f"{name:<12}{hms(r['elapsed_s']):>18}{r['distance_m']:>13.1f} m{r['step']:>10}")
    print(f"time saved: {saved(base['elapsed_s'], opt['elapsed_s']):.1f}%   "
          f"distance saved: {saved(base['distance_m'], opt['distance_m']):.1f}%")


WORDS = ["Milk", "Bread", "Eggs", "Rice", "Pasta", "Tomato", "Apple", "Cheese", "Yogurt",
         "Juice", "Water", "Coffee", "Tea", "Butter", "Honey", "Salt"]


def cmd_generate(args):
    rng = random.Random(args.seed)
    rows, cols = args.rows, args.cols
    if rows < 5 or cols < 6:
        raise SystemExit("store must be at least 5 rows by 6 columns")
    grid = [["#"] * cols for _ in range(rows)]
    for y in range(1, rows - 1):
        for x in range(1, cols - 1):
            grid[y][x] = "."
    shelves = []
    for y in range(2, rows - 2, 3):  # shelf rows, open at both ends
        for x in range(2, cols - 2):
            grid[y][x] = "#"
            shelves.append((x, y))

    picks = rng.sample(shelves, min(args.products, len(shelves)))
    products = [{"id": f"P{i:05d}", "name": f"{WORDS[i % len(WORDS)]} {i}", "x": x, "y": y}
                for i, (x, y) in enumerate(picks)]
    store = {"grid": ["".join(r) for r in grid], "entrance": [1, rows - 2],
             "checkout": [cols - 2, rows - 2], "products": products}
    with open(args.map, "w") as f:
        json.dump(store, f)

    basket = rng.sample(products, min(args.basket, len(products)))
    with open(args.list, "w") as f:
        f.writelines(f"{p['id']}:{p['name']}\n" for p in basket)
    print(f"wrote {args.map} ({rows}x{cols}, {len(products)} products) and {args.list} ({len(basket)} items)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="write a sample store map and a random basket")
    g.add_argument("--rows", type=int, default=200)
    g.add_argument("--cols", type=int, default=300)
    g.add_argument("--products", type=int, default=3000)
    g.add_argument("--basket", type=int, default=25)
    g.add_argument("--seed", type=int, default=1)
    g.add_argument("--map", default="store.json")
    g.add_argument("--list", default="basket.txt")

    r = sub.add_parser("run", help="simulate list-order vs optimized route")
    r.add_argument("map")
    r.add_argument("basket")
    r.add_argument("--delay", type=float, default=0.0, help="real-time pause per step, seconds")

    args = parser.parse_args()
    {"generate": cmd_generate, "run": cmd_run}[args.cmd](args)


if __name__ == "__main__":
    main()
