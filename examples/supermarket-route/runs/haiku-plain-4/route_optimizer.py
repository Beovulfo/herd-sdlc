#!/usr/bin/env python3
"""Picking-route optimizer for a supermarket, with a step-by-step KPI simulation.

Map (JSON):
  grid        rectangle of strings; '#' is blocked (shelf, wall), anything else is walkable
  cell_size_m metres per grid cell (default 1.0)
  entrance    [row, col] where the delivery guy starts
  checkout    [row, col] where the basket is delivered
  products    [{"id": "P00001", "name": "item-0001", "cell": [row, col]}, ...]
              cell = walkable aisle cell in front of the product's shelf

Order (text): one "ID:short name" per line, or comma separated. Bare IDs also work.

KPIs: time-to-prepare (walking + picking, seconds) and distance covered (metres).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

Cell = tuple[int, int]
MOVES = ((1, 0), (-1, 0), (0, 1), (0, -1))


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    cell: Cell


@dataclass(frozen=True)
class Store:
    grid: tuple[str, ...]
    cell_size_m: float
    entrance: Cell
    checkout: Cell
    products: dict[str, Product]

    def walkable(self, cell: Cell) -> bool:
        r, c = cell
        return 0 <= r < len(self.grid) and 0 <= c < len(self.grid[0]) and self.grid[r][c] != "#"


def load_store(path: str | Path) -> Store:
    data = json.loads(Path(path).read_text())
    grid = tuple(data["grid"])
    if not grid or any(len(row) != len(grid[0]) for row in grid):
        raise ValueError("grid must be a non-empty rectangle")
    products: dict[str, Product] = {}
    for p in data["products"]:
        if p["id"] in products:
            raise ValueError(f"duplicate product id {p['id']}")
        products[p["id"]] = Product(p["id"], p["name"], tuple(p["cell"]))
    store = Store(grid, float(data.get("cell_size_m", 1.0)), tuple(data["entrance"]),
                  tuple(data["checkout"]), products)
    checks = [("entrance", store.entrance), ("checkout", store.checkout)]
    checks += [(p.id, p.cell) for p in products.values()]
    for label, cell in checks:
        if not store.walkable(cell):
            raise ValueError(f"{label} at {cell} is not a walkable cell")
    return store


def parse_order(text: str, store: Store) -> list[str]:
    ids: list[str] = []
    for token in text.replace("\n", ",").split(","):
        if not token.strip():
            continue
        pid = token.split(":", 1)[0].strip()
        if pid not in store.products:
            raise ValueError(f"unknown product id {pid!r}")
        if pid in ids:
            raise ValueError(f"duplicate product id {pid!r} in order")
        ids.append(pid)
    if not ids:
        raise ValueError("empty order")
    return ids


def bfs(store: Store, source: Cell, targets) -> tuple[dict[Cell, int], dict[Cell, Cell | None]]:
    """Shortest step counts and parents from source. Stops once all targets are reached."""
    dist: dict[Cell, int] = {source: 0}
    parent: dict[Cell, Cell | None] = {source: None}
    remaining = set(targets) - {source}
    queue = deque([source])
    while queue and remaining:
        cur = queue.popleft()
        for dr, dc in MOVES:
            nxt = (cur[0] + dr, cur[1] + dc)
            if nxt in dist or not store.walkable(nxt):
                continue
            dist[nxt] = dist[cur] + 1
            parent[nxt] = cur
            remaining.discard(nxt)
            queue.append(nxt)
    if remaining:
        raise ValueError(f"unreachable from {source}: {sorted(remaining)}")
    return dist, parent


def distance_matrix(store: Store, cells: list[Cell]) -> list[list[int]]:
    n = len(cells)
    d = [[0] * n for _ in range(n)]
    for i in range(n):
        dist, _ = bfs(store, cells[i], cells[i + 1:])
        for j in range(i + 1, n):
            d[i][j] = d[j][i] = dist[cells[j]]  # the grid is undirected, so the matrix is symmetric
    return d


def nearest_neighbour(d: list[list[int]], start: int, end: int, nodes: list[int]) -> list[int]:
    seq = [start]
    left = set(nodes)
    while left:
        nxt = min(left, key=lambda j: (d[seq[-1]][j], j))
        seq.append(nxt)
        left.remove(nxt)
    return seq + [end]


def two_opt(d: list[list[int]], seq: list[int]) -> list[int]:
    # ponytail: 2-opt local search, not exact. Add Or-opt or Held-Karp if the gap to optimal matters.
    improved = True
    while improved:
        improved = False
        for i in range(1, len(seq) - 2):
            for j in range(i + 1, len(seq) - 1):
                a, b, c, e = seq[i - 1], seq[i], seq[j], seq[j + 1]
                if d[a][c] + d[b][e] < d[a][b] + d[c][e]:
                    seq[i:j + 1] = reversed(seq[i:j + 1])
                    improved = True
    return seq


def optimized_order(store: Store, ids: list[str]) -> list[str]:
    cells = [store.entrance] + [store.products[p].cell for p in ids] + [store.checkout]
    d = distance_matrix(store, cells)
    end = len(ids) + 1
    seq = nearest_neighbour(d, 0, end, list(range(1, end)))
    seq = two_opt(d, seq)
    return [ids[i - 1] for i in seq[1:-1]]


@dataclass(frozen=True)
class Event:
    kind: str  # "start", "walk", "pick" or "done"
    cell: Cell
    item: str | None
    distance_m: float
    elapsed_s: float
    picked: int


def simulate(store: Store, order: list[str], walk_speed_mps: float = 1.2,
             pick_seconds: float = 5.0, delay: float = 0.0) -> Iterator[Event]:
    """Walk the basket route cell by cell, yielding an event per step and per pick.

    delay: real seconds to sleep per walked cell, for a real-time view (0 = as fast as possible).
    """
    step_m = store.cell_size_m
    step_s = step_m / walk_speed_mps
    stops = [store.entrance] + [store.products[p].cell for p in order] + [store.checkout]
    items = [None] + order + [None]
    distance_m = elapsed_s = 0.0
    picked = 0
    yield Event("start", store.entrance, None, 0.0, 0.0, 0)
    for leg, (src, dst) in enumerate(zip(stops, stops[1:])):
        _, parent = bfs(store, src, [dst])
        path: list[Cell] = []
        cur: Cell | None = dst
        while cur is not None:
            path.append(cur)
            cur = parent[cur]
        path.reverse()
        for cell in path[1:]:
            distance_m += step_m
            elapsed_s += step_s
            if delay:
                time.sleep(delay)
            yield Event("walk", cell, None, distance_m, elapsed_s, picked)
        if items[leg + 1] is not None:
            elapsed_s += pick_seconds
            picked += 1
            yield Event("pick", dst, items[leg + 1], distance_m, elapsed_s, picked)
    yield Event("done", store.checkout, None, distance_m, elapsed_s, picked)


@dataclass(frozen=True)
class Result:
    order: list[str]
    time_s: float
    distance_m: float


def run(store: Store, order: list[str], walk: float, pick: float, delay: float = 0.0,
        on_event: Callable[[Event], None] | None = None) -> Result:
    last = None
    for ev in simulate(store, order, walk, pick, delay):
        if on_event:
            on_event(ev)
        last = ev
    return Result(order, last.elapsed_s, last.distance_m)


def compare(store: Store, ids: list[str], walk: float, pick: float, delay: float = 0.0,
            on_event: Callable[[str, Event], None] | None = None) -> tuple[Result, Result]:
    base_cb = (lambda ev: on_event("list-order", ev)) if on_event else None
    opt_cb = (lambda ev: on_event("optimized", ev)) if on_event else None
    base = run(store, ids, walk, pick, delay, base_cb)
    opt = run(store, optimized_order(store, ids), walk, pick, delay, opt_cb)
    return base, opt


def saving_pct(base: Result, opt: Result) -> float:
    return 100.0 * (base.time_s - opt.time_s) / base.time_s if base.time_s else 0.0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--store", required=True, help="store map JSON")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--order", help="customer list file (ID:short name per line)")
    src.add_argument("--random-orders", type=int, metavar="N",
                     help="benchmark N random baskets instead of one order")
    ap.add_argument("--basket-size", type=int, default=12, help="items per random basket")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--walk-speed", type=float, default=1.2, help="metres per second")
    ap.add_argument("--pick-seconds", type=float, default=5.0, help="seconds per item picked")
    ap.add_argument("--delay", type=float, default=0.0,
                    help="real seconds per walked cell (e.g. 0.05 to watch the walk live)")
    args = ap.parse_args(argv)

    store = load_store(args.store)
    if args.order:
        ids = parse_order(Path(args.order).read_text(), store)
        names = {p.id: p.name for p in store.products.values()}
        counter = {"list-order": 0, "optimized": 0}

        def show(label: str, ev: Event) -> None:
            if ev.kind == "pick":
                counter[label] += 1
                print(f"[{label:>10}] pick {counter[label]:>2}/{len(ids)} {ev.item} "
                      f"{names[ev.item]:<14} time-to-prepare {ev.elapsed_s:8.1f} s  "
                      f"distance {ev.distance_m:8.1f} m")
            elif ev.kind == "done":
                print(f"[{label:>10}] delivered at checkout  time-to-prepare {ev.elapsed_s:8.1f} s  "
                      f"distance {ev.distance_m:8.1f} m")

        base, opt = compare(store, ids, args.walk_speed, args.pick_seconds, args.delay, show)
        print()
        print(f"{'KPI':<18}{'list-order':>14}{'optimized':>14}{'saving':>10}")
        print(f"{'time-to-prepare':<18}{base.time_s:>13.1f}s{opt.time_s:>13.1f}s"
              f"{saving_pct(base, opt):>9.1f}%")
        print(f"{'distance covered':<18}{base.distance_m:>12.1f}m{opt.distance_m:>12.1f}m"
              f"{100 * (base.distance_m - opt.distance_m) / base.distance_m:>9.1f}%")
        print("optimized pick order: " + " -> ".join(f"{p}:{names[p]}" for p in opt.order))
        return 0

    rng = random.Random(args.seed)
    all_ids = sorted(store.products)
    savings = []
    for k in range(1, args.random_orders + 1):
        ids = rng.sample(all_ids, args.basket_size)
        base, opt = compare(store, ids, args.walk_speed, args.pick_seconds)
        savings.append(saving_pct(base, opt))
        print(f"basket {k:>3}: list-order {base.time_s:8.1f} s  optimized {opt.time_s:8.1f} s  "
              f"saving {savings[-1]:5.1f}%")
    print(f"\n{len(savings)} baskets of {args.basket_size} items: mean saving {sum(savings) / len(savings):.1f}%, "
          f"min {min(savings):.1f}%, max {max(savings):.1f}%, "
          f"{sum(s > 30 for s in savings)}/{len(savings)} above 30%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
