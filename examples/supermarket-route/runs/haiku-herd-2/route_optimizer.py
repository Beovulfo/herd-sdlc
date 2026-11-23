"""Route optimizer for a supermarket basket picker.

Map (JSON): "layout" is a list of rows, '#' for a wall or shelf and '.' for floor.
"start" is the [x, y] counter where the basket is ready. "products" lists each
product with "id", "short" name and the shelf cell "x", "y". A product cell is
blocked; it is picked from its first open neighbour, checked in the order
left, right, up, down.

Request (text): one "id:short name" per line.
One grid cell is one metre. Time = walking time + a fixed time per pick.

Usage:
  python3 route_optimizer.py MAP.json LIST.txt [--delay SECONDS]
  python3 route_optimizer.py --benchmark
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
from typing import Iterator

WALK_M_PER_S = 1.0  # ponytail: fixed walking speed, calibrate on a real store
PICK_S = 5.0  # ponytail: fixed time per pick, calibrate on a real store
NEIGHBOURS = ((-1, 0), (1, 0), (0, -1), (0, 1))


class RouteError(ValueError):
    """The map or the request cannot be planned."""


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    x: int
    y: int


@dataclass
class Store:
    width: int
    height: int
    open: bytearray  # 1 = walkable; flat index y * width + x
    start: int
    products: dict[str, Product]

    def index(self, x: int, y: int) -> int:
        return y * self.width + x

    def bfs(self, src: int, targets: list[int] | None = None) -> tuple[list[int], list[int]]:
        """Walk length in cells from src to each cell, and the parent of each cell.

        With targets, stops once every target is reached. Without, searches the whole reachable area.
        """
        w, h, op = self.width, self.height, self.open
        dist = [-1] * (w * h)
        parent = [-1] * (w * h)
        dist[src] = 0
        remaining = None if targets is None else set(targets) - {src}
        queue = deque([src])
        while queue and (remaining is None or remaining):
            c = queue.popleft()
            x = c % w
            for nb, ok in ((c - 1, x > 0), (c + 1, x < w - 1), (c - w, c >= w), (c + w, c < w * (h - 1))):
                if ok and op[nb] and dist[nb] < 0:
                    dist[nb] = dist[c] + 1
                    parent[nb] = c
                    if remaining is not None:
                        remaining.discard(nb)
                    queue.append(nb)
        return dist, parent


@dataclass(frozen=True)
class Step:
    kind: str  # "move" or "pick"
    cell: int
    item: str | None = None


@dataclass
class Plan:
    order: list[str]
    steps: list[Step]
    distance_m: int
    time_s: float


def load_store(data: dict) -> Store:
    try:
        rows = data["layout"]
        if not isinstance(rows, list) or not rows:
            raise RouteError("layout must be a non-empty list of rows")
        width = len(rows[0])
        if any(len(r) != width for r in rows):
            raise RouteError("all layout rows must have the same length")
        if any(ch not in "#." for r in rows for ch in r):
            raise RouteError("layout cells must be '#' (blocked) or '.' (floor)")
        height = len(rows)
        op = bytearray(1 if ch == "." else 0 for r in rows for ch in r)
        products: dict[str, Product] = {}
        for p in data.get("products", []):
            pid, x, y = str(p["id"]), int(p["x"]), int(p["y"])
            if pid in products:
                raise RouteError(f"duplicate product id {pid}")
            if not (0 <= x < width and 0 <= y < height):
                raise RouteError(f"product {pid} is outside the map")
            products[pid] = Product(pid, str(p["short"]), x, y)
            op[y * width + x] = 0
        sx, sy = (int(v) for v in data["start"])
        if not (0 <= sx < width and 0 <= sy < height):
            raise RouteError("start is outside the map")
        start = sy * width + sx
        if not op[start]:
            raise RouteError("start must be a floor cell, not a shelf or wall")
    except RouteError:
        raise
    except KeyError as e:
        raise RouteError(f"bad map: missing key {e}") from e
    except (TypeError, ValueError) as e:
        raise RouteError(f"bad map: {e}") from e
    return Store(width, height, op, start, products)


def parse_list(text: str) -> list[tuple[str, str]]:
    items = []
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pid, sep, name = line.partition(":")
        if not sep or not pid.strip() or not name.strip():
            raise RouteError(f"line {n}: expected id:short name, got {line!r}")
        items.append((pid.strip(), name.strip()))
    if not items:
        raise RouteError("the request has no products")
    return items


def _access_cell(store: Store, p: Product) -> int:
    for dx, dy in NEIGHBOURS:
        nx, ny = p.x + dx, p.y + dy
        if 0 <= nx < store.width and 0 <= ny < store.height and store.open[store.index(nx, ny)]:
            return store.index(nx, ny)
    raise RouteError(f"product {p.id} has no open cell next to it")


def _tour_length(tour: list[int], dist: list[list[int]]) -> int:
    seq = [0] + tour + [0]
    return sum(dist[seq[i]][seq[i + 1]] for i in range(len(seq) - 1))


def _nearest_neighbour(dist: list[list[int]]) -> list[int]:
    left = set(range(1, len(dist)))
    cur, tour = 0, []
    while left:
        cur = min(left, key=lambda j: (dist[cur][j], j))
        tour.append(cur)
        left.remove(cur)
    return tour


def _two_opt(tour: list[int], dist: list[list[int]]) -> list[int]:
    seq = [0] + tour
    n = len(seq)
    improved = True
    while improved:
        improved = False
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                a, b = seq[i - 1], seq[i]
                c, d = seq[j], seq[(j + 1) % n]
                if dist[a][c] + dist[b][d] < dist[a][b] + dist[c][d]:
                    seq[i : j + 1] = reversed(seq[i : j + 1])
                    improved = True
    return seq[1:]


def plan_route(store: Store, items: list[tuple[str, str]], optimize: bool = True) -> Plan:
    """Plan the walk from the counter through every item and back.

    optimize=False keeps the request order (the list-order route). With optimize=True,
    the best of the list order and a nearest-neighbour order, each improved by 2-opt.
    """
    stops = []
    for pid, name in items:
        p = store.products.get(pid)
        if p is None:
            raise RouteError(f"unknown product id {pid}")
        if p.name != name:
            raise RouteError(f"product {pid} is '{p.name}' in the map, not '{name}'")
        stops.append(_access_cell(store, p))
    nodes = [store.start] + stops
    searches = [store.bfs(n, nodes) for n in nodes]
    dist = [[searches[a][0][nodes[b]] for b in range(len(nodes))] for a in range(len(nodes))]
    for b, (pid, _) in enumerate(items, 1):
        if dist[0][b] < 0:
            raise RouteError(f"product {pid} cannot be reached from the start")
    tour = list(range(1, len(nodes)))
    if optimize:
        candidates = [_two_opt(tour, dist), _two_opt(_nearest_neighbour(dist), dist)]
        tour = min(candidates, key=lambda t: _tour_length(t, dist))
    steps: list[Step] = []
    prev = 0
    for node in tour + [0]:
        parent = searches[prev][1]
        src, dst = nodes[prev], nodes[node]
        path = []
        cur = dst
        while cur != src:
            path.append(cur)
            cur = parent[cur]
        path.reverse()
        steps.extend(Step("move", c) for c in path)
        if node:
            steps.append(Step("pick", dst, items[node - 1][0]))
        prev = node
    moves = sum(1 for s in steps if s.kind == "move")
    return Plan(
        order=[items[n - 1][0] for n in tour],
        steps=steps,
        distance_m=moves,
        time_s=moves / WALK_M_PER_S + len(items) * PICK_S,
    )


def simulate(store: Store, plan: Plan) -> Iterator[dict]:
    """Yield one event per step with the KPIs reached so far."""
    moves = picks = 0
    for i, step in enumerate(plan.steps, 1):
        if step.kind == "move":
            moves += 1
        else:
            picks += 1
        yield {
            "step": i,
            "action": step.kind,
            "x": step.cell % store.width,
            "y": step.cell // store.width,
            "item": step.item,
            "distance_m": moves,
            "time_s": moves / WALK_M_PER_S + picks * PICK_S,
        }


def _reachable(store: Store, dist: list[int], p: Product) -> bool:
    try:
        return dist[_access_cell(store, p)] >= 0
    except RouteError:
        return False


def _maze(rng: random.Random, width: int, height: int) -> list[list[str]]:
    rows = [["#"] * width for _ in range(height)]
    rows[1][1] = "."
    stack = [(1, 1)]
    while stack:
        x, y = stack[-1]
        nbrs = [
            (x + dx, y + dy)
            for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2))
            if 1 <= x + dx < width - 1 and 1 <= y + dy < height - 1 and rows[y + dy][x + dx] == "#"
        ]
        if not nbrs:
            stack.pop()
            continue
        nx, ny = rng.choice(nbrs)
        rows[(y + ny) // 2][(x + nx) // 2] = "."
        rows[ny][nx] = "."
        stack.append((nx, ny))
    return rows


def generate_map(seed: int, width: int, height: int, kind: str, n_products: int) -> dict:
    """A random store map: 'aisles' (shelf rows), 'hall' (random pillars) or 'maze' (1-wide corridors)."""
    rng = random.Random(seed)
    if kind == "aisles":
        rows = [["#" if x % 3 == 2 and 0 < y < height - 1 else "." for x in range(width)] for y in range(height)]
    elif kind == "hall":
        rows = [["#" if rng.random() < 0.15 else "." for _ in range(width)] for _ in range(height)]
    elif kind == "maze":
        rows = _maze(rng, width, height)
    else:
        raise ValueError(f"unknown layout {kind!r}")
    rows[1][1] = "."  # the counter
    shelves = [
        (x, y)
        for y in range(height)
        for x in range(width)
        if rows[y][x] == "#"
        and any(0 <= x + dx < width and 0 <= y + dy < height and rows[y + dy][x + dx] == "." for dx, dy in NEIGHBOURS)
    ]
    chosen = rng.sample(shelves, min(n_products, len(shelves)))
    data = {
        "layout": ["".join(r) for r in rows],
        "start": [1, 1],
        "products": [{"id": f"P{i:03d}", "short": f"item{i:03d}", "x": x, "y": y} for i, (x, y) in enumerate(chosen)],
    }
    store = load_store(data)
    dist, _ = store.bfs(store.start)
    data["products"] = [p for p in data["products"] if _reachable(store, dist, store.products[p["id"]])]
    return data


def random_items(data: dict, seed: int, n: int) -> list[tuple[str, str]]:
    """n random products in random order: a customer list that ignores the store layout."""
    chosen = random.Random(seed).sample(data["products"], n)
    return [(p["id"], p["short"]) for p in chosen]


def benchmark(seeds=range(20), n_items: int = 20) -> tuple[list[dict], float]:
    """Compare the list-order route with the optimized route on generated stores.

    Returns one row per store and the aggregate saving of basket time, in percent.
    """
    rows = []
    for seed in seeds:
        rng = random.Random(seed * 7919 + 1)
        kind = ("aisles", "hall", "maze")[seed % 3]
        width, height = rng.randrange(40, 121), rng.randrange(40, 121)
        data = generate_map(seed, width, height, kind, n_products=60)
        store = load_store(data)
        items = random_items(data, seed, n_items)
        list_plan = plan_route(store, items, optimize=False)
        best = plan_route(store, items)
        rows.append(
            {
                "seed": seed,
                "layout": kind,
                "size": f"{width}x{height}",
                "list_time_s": list_plan.time_s,
                "optimized_time_s": best.time_s,
                "list_distance_m": list_plan.distance_m,
                "optimized_distance_m": best.distance_m,
                "saving_pct": _saving(list_plan.time_s, best.time_s),
            }
        )
    total_list = sum(r["list_time_s"] for r in rows)
    total_best = sum(r["optimized_time_s"] for r in rows)
    return rows, _saving(total_list, total_best)


def _saving(before: float, after: float) -> float:
    return 100.0 * (before - after) / before if before else 0.0


def _event_line(ev: dict) -> str:
    item = f" {ev['item']}" if ev["item"] else ""
    return (
        f"{ev['step']:>6} {ev['action']:<4} ({ev['x']},{ev['y']}){item}  "
        f"time-to-prepare-basket {ev['time_s']:8.1f} s  distance-covered {ev['distance_m']:5d} m"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan and simulate a supermarket basket route.")
    ap.add_argument("map", nargs="?", type=Path, help="store map JSON")
    ap.add_argument("items", nargs="?", type=Path, help="request text: one id:short name per line")
    ap.add_argument("--delay", type=float, default=0.0, help="seconds to wait before each step")
    ap.add_argument("--benchmark", action="store_true", help="compare both routes on 20 generated stores")
    args = ap.parse_args(argv)
    if args.benchmark:
        rows, saving = benchmark()
        for r in rows:
            print(
                f"seed {r['seed']:>2} {r['layout']:<7} {r['size']:<8} "
                f"list {r['list_time_s']:8.1f} s  optimized {r['optimized_time_s']:8.1f} s  "
                f"saving {r['saving_pct']:5.1f}%"
            )
        print(f"aggregate saving: {saving:.1f}%")
        return 0
    if not args.map or not args.items:
        ap.error("give MAP and ITEMS, or --benchmark")
    try:
        store = load_store(json.loads(args.map.read_text()))
        items = parse_list(args.items.read_text())
        list_plan = plan_route(store, items, optimize=False)
        best = plan_route(store, items)
    except (RouteError, OSError, ValueError) as e:  # OSError: missing file; ValueError: bad JSON
        print(f"error: {e}", file=sys.stderr)
        return 2
    for title, plan in (("list-order route", list_plan), ("optimized route", best)):
        print(f"== {title}")
        for ev in simulate(store, plan):
            print(_event_line(ev))
            if args.delay:
                time.sleep(args.delay)
    print(
        f"time-to-prepare-basket: list-order {list_plan.time_s:.1f} s, optimized {best.time_s:.1f} s, "
        f"saving {_saving(list_plan.time_s, best.time_s):.1f}%"
    )
    print(
        f"distance-covered: list-order {list_plan.distance_m} m, optimized {best.distance_m} m"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
