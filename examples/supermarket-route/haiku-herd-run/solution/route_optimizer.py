"""Supermarket route optimizer for a delivery guy who picks a basket.

Map (JSON): {"grid": ["..#..", ...], "start": [x, y], "end": [x, y],
             "products": [{"id": "P01", "short": "milk", "x": 3, "y": 1}]}
'#' is a shelf or wall; every other cell is walkable. Products sit on walkable cells.
Basket (text): one `id:short name` per line, in the order the customer listed them.

Time model (identical for both strategies, so the comparison is fair):
  time to prepare = walked cells / WALK_SPEED + PICK_S per item (basket ready at checkout).
  One grid cell is one metre.

Usage:
  python3 route_optimizer.py simulate MAP BASKET [--strategy optimized|list-order] [--delay S]
  python3 route_optimizer.py compare MAP BASKET
Sample map: python3 -c "import json, route_optimizer as r; print(json.dumps(r.demo_store()))"
"""
import argparse
import json
import random
import sys
import time
from collections import deque

WALK_SPEED = 1.0  # cells per second
PICK_S = 4.0  # seconds per picked item
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


class Store:
    def __init__(self, data):
        self.grid = data["grid"]
        self.h = len(self.grid)
        self.w = len(self.grid[0])
        self.start = tuple(data["start"])
        self.end = tuple(data["end"])
        self.products = {p["id"]: (p["short"], (p["x"], p["y"])) for p in data["products"]}


def bfs(store, src):
    dist = {src: 0}
    q = deque([src])
    while q:
        x, y = q.popleft()
        for dx, dy in DIRS:
            nxt = (x + dx, y + dy)
            if 0 <= nxt[0] < store.w and 0 <= nxt[1] < store.h and store.grid[nxt[1]][nxt[0]] != "#" and nxt not in dist:
                dist[nxt] = dist[(x, y)] + 1
                q.append(nxt)
    return dist


def parse_basket(text):
    """Product ids in list order. The short name after the colon is informational."""
    return [line.partition(":")[0].strip() for line in text.splitlines() if line.strip()]


def stops(store, ids):
    """Index 0 is the entrance, 1..n the products in list order, n+1 the checkout."""
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate product id in basket")
    cells = [store.start]
    for pid in ids:
        if pid not in store.products:
            raise ValueError(f"unknown product id: {pid}")
        x, y = store.products[pid][1]
        if store.grid[y][x] == "#":
            raise ValueError(f"product {pid} is on a shelf cell, not walkable")
        cells.append((x, y))
    cells.append(store.end)
    return cells


def distances(store, cells):
    out = []
    for a in cells:
        reach = bfs(store, a)
        if any(b not in reach for b in cells):
            raise ValueError(f"a stop is unreachable from {a}")
        out.append([reach[b] for b in cells])
    return out


def path_len(order, d):
    return sum(d[a][b] for a, b in zip(order, order[1:]))


def optimize(d, n):
    """Nearest neighbour from the entrance, then 2-opt on the open path.
    ponytail: heuristic, not optimal; full 2-opt passes are O(n^3), fine for baskets up to ~50 items."""
    left, order = set(range(1, n + 1)), [0]
    while left:
        nxt = min(left, key=lambda j: (d[order[-1]][j], j))
        order.append(nxt)
        left.remove(nxt)
    order.append(n + 1)
    improved = True
    while improved:
        improved = False
        for i in range(1, n):
            for j in range(i + 1, n + 1):
                cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                if path_len(cand, d) < path_len(order, d):
                    order, improved = cand, True
    return order


def plan_route(store, ids, strategy):
    if strategy not in ("optimized", "list-order"):
        raise ValueError(f"unknown strategy: {strategy}")
    cells = stops(store, ids)
    d = distances(store, cells)
    order = optimize(d, len(ids)) if strategy == "optimized" else list(range(len(ids) + 2))
    return order, cells, d


def simulate(store, ids, strategy):
    """Yield one event per stop, with KPIs so far. The last event is the checkout."""
    order, cells, d = plan_route(store, ids, strategy)
    n = len(ids)
    walked = picked = 0
    for step, (a, b) in enumerate(zip(order, order[1:]), start=1):
        walked += d[a][b]
        if 1 <= b <= n:
            picked += 1
        yield {
            "step": step,
            "stop": store.products[ids[b - 1]][0] if b <= n else "checkout",
            "cell": cells[b],
            "distance_covered": walked,
            "time_to_prepare_s": round(walked / WALK_SPEED + PICK_S * picked, 1),
        }


def final_kpis(store, ids, strategy):
    order, _, d = plan_route(store, ids, strategy)
    last = list(simulate(store, ids, strategy))[-1]
    return {
        "order": [ids[i - 1] for i in order[1:-1]],
        "distance_covered": last["distance_covered"],
        "time_to_prepare_s": last["time_to_prepare_s"],
    }


def compare(store, ids):
    base = final_kpis(store, ids, "list-order")
    opt = final_kpis(store, ids, "optimized")
    saving = 1 - opt["time_to_prepare_s"] / base["time_to_prepare_s"] if base["time_to_prepare_s"] else 0.0
    return {"list-order": base, "optimized": opt, "saving": saving}


def demo_store():
    """41 x 21 store: six shelf rows with aisles between them, 54 products on the aisle below each shelf."""
    w, h = 41, 21
    grid = [["."] * w for _ in range(h)]
    products = []
    shelf_rows = range(2, h - 2, 3)
    for y in shelf_rows:
        for x in range(2, w - 2):
            grid[y][x] = "#"
    for y in shelf_rows:
        for x in range(3, w - 3, 4):
            k = len(products) + 1
            products.append({"id": f"P{k:02d}", "short": f"item-{k:02d}", "x": x, "y": y + 1})
    return {"grid": ["".join(r) for r in grid], "start": [0, 0], "end": [w - 1, h - 1], "products": products}


def demo_basket(seed, size=12):
    """Random customer list (in the order the customer wrote it) from the demo store."""
    ids = [p["id"] for p in demo_store()["products"]]
    return random.Random(seed).sample(ids, size)


def main(argv=None):
    p = argparse.ArgumentParser(description="Supermarket route optimizer")
    sub = p.add_subparsers(dest="cmd", required=True)
    sim = sub.add_parser("simulate")
    sim.add_argument("map")
    sim.add_argument("basket")
    sim.add_argument("--strategy", choices=["optimized", "list-order"], default="optimized")
    sim.add_argument("--delay", type=float, default=0.0, help="seconds to wait between steps")
    cmp_ = sub.add_parser("compare")
    cmp_.add_argument("map")
    cmp_.add_argument("basket")
    args = p.parse_args(argv)
    try:
        with open(args.map) as f:
            store = Store(json.load(f))
        with open(args.basket) as f:
            ids = parse_basket(f.read())
        if args.cmd == "simulate":
            for ev in simulate(store, ids, args.strategy):
                print(f"step {ev['step']:>2}  {ev['stop']:<10}  distance {ev['distance_covered']:>4} cells  "
                      f"time {ev['time_to_prepare_s']:>7.1f} s", flush=True)
                time.sleep(args.delay)
        else:
            res = compare(store, ids)
            for name in ("list-order", "optimized"):
                k = res[name]
                print(f"{name:<11} distance {k['distance_covered']:>4} cells  "
                      f"time-to-prepare-basket {k['time_to_prepare_s']:>7.1f} s")
            print(f"saving {res['saving']:.1%} of time-to-prepare-basket")
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
