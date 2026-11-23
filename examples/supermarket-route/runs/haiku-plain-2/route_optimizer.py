#!/usr/bin/env python3
"""Supermarket route optimizer for a basket-picking delivery guy.

Map (JSON):
  {"layout": [...], "start": [x, y], "checkout": [x, y],
   "products": {"P001": {"name": "milk", "at": [x, y]}}}
  - layout: one string per row. "." is walkable, any other character is blocked
    (shelf, wall, counter).
  - products: "at" is the product's cell. If that cell is blocked, the picker
    stands on its first free neighbour (up, down, left, right).
  - checkout defaults to start: the basket is ready when the guy is back there.
Order (text): one "id:short name" per line, as the customer wrote the list.

  python3 route_optimizer.py run MAP.json ORDER.txt [--trace] [--realtime 10]
  python3 route_optimizer.py demo [--width 120 --height 80 --products 400
                                   --items 30 --trials 5 --seed 1 --save-dir DIR]

--realtime F plays the walk at F times real speed (0 = as fast as possible).
"""
import argparse
import heapq
import json
import os
import random
import statistics
import sys
import time

CELL_M = 1.0      # metres per grid cell
WALK_MPS = 1.2    # walking speed of the delivery guy
PICK_S = 4.0      # seconds to pick one item off a shelf
TARGET_SAVING = 0.30
NEIGH = ((0, -1), (0, 1), (-1, 0), (1, 0))
WORDS = ["milk", "bread", "eggs", "rice", "pasta", "tomato", "apple", "banana",
         "cheese", "yogurt", "butter", "coffee", "tea", "sugar", "flour", "oats",
         "honey", "jam", "water", "juice", "wine", "soap", "shampoo", "salt"]


class Store:
    def __init__(self, data):
        self.rows = data["layout"]
        self.h, self.w = len(self.rows), len(self.rows[0])
        self.start = tuple(data["start"])
        self.checkout = tuple(data.get("checkout", data["start"]))
        for c in (self.start, self.checkout):
            if not self.free(c):
                raise ValueError(f"start/checkout {c} is blocked or outside the map")
        self.products = {}  # id -> (short name, access cell)
        for pid, p in data["products"].items():
            at = tuple(p["at"])
            if not self.inside(at):
                raise ValueError(f"product {pid} is outside the map")
            self.products[pid] = (p["name"], self.access(pid, at))

    def inside(self, c):
        return 0 <= c[0] < self.w and 0 <= c[1] < self.h

    def free(self, c):
        return self.inside(c) and self.rows[c[1]][c[0]] == "."

    def access(self, pid, at):
        for c in [at] + [(at[0] + dx, at[1] + dy) for dx, dy in NEIGH]:
            if self.free(c):
                return c
        raise ValueError(f"product {pid} has no free cell next to it")


def shortest_path(store, a, b):
    """A* on the 4-connected grid (Manhattan heuristic). Cells from a to b, or None."""
    if a == b:
        return [a]
    heap = [(abs(a[0] - b[0]) + abs(a[1] - b[1]), 0, a)]
    came = {a: None}
    g = {a: 0}
    while heap:
        _, cost, cur = heapq.heappop(heap)
        if cur == b:
            break
        if cost > g[cur]:
            continue  # stale heap entry
        for dx, dy in NEIGH:
            n = (cur[0] + dx, cur[1] + dy)
            if not store.free(n):
                continue
            ng = cost + 1
            if ng < g.get(n, ng + 1):
                g[n] = ng
                came[n] = cur
                heapq.heappush(heap, (ng + abs(n[0] - b[0]) + abs(n[1] - b[1]), ng, n))
    if b not in came:
        return None
    path = [b]
    while came[path[-1]] is not None:
        path.append(came[path[-1]])
    return path[::-1]


def distance_matrix(store, cells, labels):
    # ponytail: one A* per pair, O(n^2) searches. Ceiling: a few hundred stops.
    n = len(cells)
    d = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            path = shortest_path(store, cells[i], cells[j])
            if path is None:
                raise ValueError(f"{labels[j]} cannot be reached from {labels[i]}")
            d[i][j] = d[j][i] = len(path) - 1
    return d


def nearest_neighbour(d, n):
    left = set(range(1, n + 1))
    seq, cur = [0], 0
    while left:
        cur = min(left, key=lambda k: (d[cur][k], k))
        left.remove(cur)
        seq.append(cur)
    return seq + [n + 1]


def two_opt(seq, d):
    """Local search: reverse segments while that shortens the open path.
    seq[0] (start) and seq[-1] (checkout) stay fixed."""
    improved = True
    while improved:
        improved = False
        for i in range(1, len(seq) - 2):
            for j in range(i + 1, len(seq) - 1):
                a, b, c, e = seq[i - 1], seq[i], seq[j], seq[j + 1]
                if d[a][c] + d[b][e] < d[a][b] + d[c][e]:
                    seq[i:j + 1] = seq[i:j + 1][::-1]
                    improved = True
    return seq


def parse_order(text, store):
    pids = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pid = line.split(":", 1)[0].strip()
        if pid not in store.products:
            raise ValueError(f"unknown product id {pid!r}")
        pids.append(pid)
    if len(set(pids)) != len(pids):
        raise ValueError("duplicate product id in order")
    return pids


def plan(store, pids):
    """Return (list-order sequence, optimized sequence). Node 0 is the start,
    nodes 1..n are the products in order, node n+1 is the checkout."""
    cells = [store.start] + [store.products[p][1] for p in pids] + [store.checkout]
    labels = ["start"] + pids + ["checkout"]
    d = distance_matrix(store, cells, labels)
    n = len(pids)
    return list(range(n + 2)), two_opt(nearest_neighbour(d, n), d)


def run(store, pids, seq, on_event=None, realtime=0.0):
    """Walk the route cell by cell, clock and odometer ticking. Returns the KPIs.
    on_event(kind, kpis, where) is called for every move ("move", cell) and pick ("pick", id)."""
    nodes = [store.start] + [store.products[p][1] for p in pids] + [store.checkout]
    state = {"time_s": 0.0, "distance_m": 0.0, "steps": 0, "picks": 0}

    def tick(kind, dt, where):
        state["time_s"] += dt
        if kind == "move":
            state["steps"] += 1
            state["distance_m"] += CELL_M
        else:
            state["picks"] += 1
        if realtime:
            time.sleep(dt / realtime)
        if on_event:
            on_event(kind, dict(state), where)

    for i in range(len(seq) - 1):
        path = shortest_path(store, nodes[seq[i]], nodes[seq[i + 1]])
        for cell in path[1:]:
            tick("move", CELL_M / WALK_MPS, cell)
        if i + 1 < len(seq) - 1:
            tick("pick", PICK_S, pids[seq[i + 1] - 1])
    return dict(state)


def compare(store, pids, on_event=None, realtime=0.0):
    listed, optimized = plan(store, pids)
    results = {}
    for name, seq in (("list-order", listed), ("optimized", optimized)):
        cb = (lambda kind, kpi, where, name=name: on_event(name, kind, kpi, where)) if on_event else None
        results[name] = run(store, pids, seq, cb, realtime)
    base = results["list-order"]["time_s"]
    saving = 1 - results["optimized"]["time_s"] / base if base else 0.0
    return results, saving


def compare_and_print(store, pids, trace=False, realtime=0.0):
    def show(route, kind, kpi, where):
        if kind == "pick":
            print(f"[{route:<10}] t={kpi['time_s']:8.1f} s  dist={kpi['distance_m']:8.1f} m"
                  f"  picked {where} ({store.products[where][0]})")
        elif trace:
            print(f"[{route:<10}] step {where}  t={kpi['time_s']:8.1f} s  dist={kpi['distance_m']:8.1f} m")

    results, saving = compare(store, pids, show, realtime)
    print(f"\n{'route':<12}{'time to basket ready':>24}{'distance covered':>20}{'picks':>8}")
    for name, k in results.items():
        print(f"{name:<12}{k['time_s']:>21.1f} s{k['distance_m']:>17.1f} m{k['picks']:>8}")
    verdict = "met" if saving > TARGET_SAVING else "NOT met"
    print(f"time saved by optimized route: {saving:.1%} (target > {TARGET_SAVING:.0%}: {verdict})")
    return saving


def demo_map(width, height, n_products, rng):
    """Synthetic store: boundary walls, shelf stripes every 4 columns, cross aisles."""
    cross_rows = {1, height // 3, 2 * height // 3, height - 2}
    layout = []
    for y in range(height):
        row = []
        for x in range(width):
            if x in (0, width - 1) or y in (0, height - 1):
                row.append("#")
            elif y in cross_rows or x % 4 != 2:
                row.append(".")
            else:
                row.append("=")
        layout.append("".join(row))
    shelves = [(x, y) for y, row in enumerate(layout) for x, ch in enumerate(row) if ch == "="]
    if n_products > len(shelves):
        raise ValueError(f"store has only {len(shelves)} shelf cells")
    products = {}
    for i, (x, y) in enumerate(rng.sample(shelves, n_products)):
        products[f"P{i:04d}"] = {"name": f"{WORDS[i % len(WORDS)]}-{i}", "at": [x, y]}
    return {"layout": layout, "start": [1, height - 2], "products": products}


def demo(args):
    data = demo_map(args.width, args.height, args.products, random.Random(args.seed))
    store = Store(data)
    ids = sorted(data["products"])
    print(f"demo store {args.width}x{args.height} cells, {args.products} products, "
          f"{args.items} items per order")
    savings = []
    for trial in range(args.trials):
        pids = random.Random(args.seed * 1000 + trial).sample(ids, args.items)
        if trial == 0:
            print("\n-- trial 1, step by step --")
            savings.append(compare_and_print(store, pids, args.trace, args.realtime))
            if args.save_dir:
                os.makedirs(args.save_dir, exist_ok=True)
                with open(os.path.join(args.save_dir, "map.json"), "w") as f:
                    json.dump(data, f)
                with open(os.path.join(args.save_dir, "order.txt"), "w") as f:
                    f.write("\n".join(f"{p}:{store.products[p][0]}" for p in pids) + "\n")
        else:
            savings.append(compare(store, pids)[1])
    print("\ntime saved per trial: " + ", ".join(f"{s:.1%}" for s in savings))
    print(f"min {min(savings):.1%}  median {statistics.median(savings):.1%}  "
          f"max {max(savings):.1%}  target met in {sum(s > TARGET_SAVING for s in savings)}"
          f"/{len(savings)} trials")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="route one order on a map file")
    r.add_argument("map")
    r.add_argument("order")
    r.add_argument("--trace", action="store_true", help="print every step")
    r.add_argument("--realtime", type=float, default=0.0)
    d = sub.add_parser("demo", help="synthetic store, random orders")
    d.add_argument("--width", type=int, default=120)
    d.add_argument("--height", type=int, default=80)
    d.add_argument("--products", type=int, default=400)
    d.add_argument("--items", type=int, default=30)
    d.add_argument("--trials", type=int, default=5)
    d.add_argument("--seed", type=int, default=1)
    d.add_argument("--trace", action="store_true")
    d.add_argument("--realtime", type=float, default=0.0)
    d.add_argument("--save-dir", help="write map.json and order.txt of trial 1 here")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "run":
            with open(args.map) as f:
                store = Store(json.load(f))
            with open(args.order) as f:
                pids = parse_order(f.read(), store)
            compare_and_print(store, pids, args.trace, args.realtime)
        else:
            demo(args)
    except (ValueError, KeyError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
