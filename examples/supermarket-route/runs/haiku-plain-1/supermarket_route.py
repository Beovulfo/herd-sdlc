#!/usr/bin/env python3
"""Supermarket route optimizer and step-by-step picking simulator.

Map (JSON): {"grid": ["#####", "#E..#", ...], "products": [{"id", "name", "x", "y"}]}
  '#' is a wall, every other character is walkable, 'E' is the entrance/checkout.
  x is the column and y the row of the cell the product is picked from.
Shopping list (text): one "ID:short name" per line. Blank lines and '#' comments are skipped.

Run: python3 supermarket_route.py --map examples/sample_map.json --list examples/sample_list.txt
"""
import argparse
import json
import sys
import time
from collections import deque

WALK_SPEED_M_S = 1.2  # average walking speed
PICK_SECONDS = 5.0  # time to find and pick one item
CELL_M = 1.0  # size of one grid cell in metres
TARGET_SAVING_PCT = 30.0
ENTRANCE = 0  # index of the entrance in the stop list
MOVES = ((1, 0), (-1, 0), (0, 1), (0, -1))


def load_map(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    grid = data["grid"]
    width = len(grid[0])
    if any(len(row) != width for row in grid):
        raise ValueError("all grid rows must have the same length")
    entrances = [(x, y) for y, row in enumerate(grid) for x, c in enumerate(row) if c == "E"]
    if len(entrances) != 1:
        raise ValueError("the map needs exactly one 'E' entrance cell")
    products = {}
    for p in data["products"]:
        cell = (p["x"], p["y"])
        if not _walkable(grid, cell) or cell == entrances[0]:
            raise ValueError(f"product {p['id']} is not on a walkable cell")
        if p["id"] in products:
            raise ValueError(f"duplicate product id {p['id']}")
        products[p["id"]] = (p["name"], cell)
    return grid, entrances[0], products


def load_list(path, products):
    picks = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            pid = line.split(":", 1)[0].strip()
            if pid not in products:
                raise ValueError(f"product {pid!r} is not on the map")
            if pid in picks:
                raise ValueError(f"product {pid!r} is listed twice")
            picks.append(pid)
    if not picks:
        raise ValueError("the shopping list is empty")
    return picks


def _walkable(grid, cell):
    x, y = cell
    return 0 <= y < len(grid) and 0 <= x < len(grid[0]) and grid[y][x] != "#"


def _bfs(grid, src, targets=frozenset()):
    """Breadth-first search from src; stops once every target is reached."""
    dist = {src: 0}
    parent = {src: None}
    pending = set(targets) - {src}
    queue = deque([src])
    while queue and pending:
        x, y = queue.popleft()
        for dx, dy in MOVES:
            nxt = (x + dx, y + dy)
            if nxt not in dist and _walkable(grid, nxt):
                dist[nxt] = dist[(x, y)] + 1
                parent[nxt] = (x, y)
                pending.discard(nxt)
                queue.append(nxt)
    return dist, parent


def _path(parent, end):
    path = []
    cell = end
    while cell is not None:
        path.append(cell)
        cell = parent[cell]
    return path[::-1]


def distance_matrix(grid, stops, labels):
    """Walking distance in cells between every pair of stops (grid is undirected, so symmetric)."""
    n = len(stops)
    d = [[0] * n for _ in range(n)]
    for i in range(n):
        dist, _ = _bfs(grid, stops[i], set(stops[i + 1:]))
        for j in range(i + 1, n):
            if stops[j] not in dist:
                raise ValueError(f"{labels[j]} cannot be reached from {labels[i]}")
            d[i][j] = d[j][i] = dist[stops[j]]
    return d


def cycle_cost(cycle, d):
    return sum(d[cycle[i]][cycle[(i + 1) % len(cycle)]] for i in range(len(cycle)))


def plan(d):
    """Nearest neighbour from the entrance, then 2-opt until no swap shortens the loop."""
    n = len(d)
    tour = [ENTRANCE]
    left = set(range(1, n))
    while left:
        cur = tour[-1]
        nxt = min(left, key=lambda j: (d[cur][j], j))
        tour.append(nxt)
        left.remove(nxt)
    # ponytail: O(n^3) 2-opt is fine for shopping lists; Or-opt or a real TSP solver if lists reach hundreds
    improved = True
    while improved:
        improved = False
        for i in range(1, n - 1):
            for k in range(i + 1, n):
                a, b = tour[i - 1], tour[i]
                c, e = tour[k], tour[(k + 1) % n]
                if d[a][c] + d[b][e] < d[a][b] + d[c][e] - 1e-9:
                    tour[i:k + 1] = reversed(tour[i:k + 1])
                    improved = True
    return tour


def simulate(grid, stops, labels, cycle, speed, pick_s, emit=None, delay=0.0, trace=False):
    """Walk the loop cell by cell, updating the KPIs each step. The loop returns to the entrance."""
    time_s = dist_m = 0.0
    picked = 0
    total = len(cycle) - 1
    for i, a in enumerate(cycle):
        b = cycle[(i + 1) % len(cycle)]
        _, parent = _bfs(grid, stops[a], {stops[b]})
        for cell in _path(parent, stops[b])[1:]:
            dist_m += CELL_M
            time_s += CELL_M / speed
            if trace and emit:
                emit(f"[{time_s:7.1f} s] {dist_m:7.1f} m  step to {cell}")
            if delay:
                time.sleep(delay)
        if b != ENTRANCE:
            picked += 1
            time_s += pick_s
            if emit:
                emit(f"[{time_s:7.1f} s] {dist_m:7.1f} m  picked {labels[b]} ({picked}/{total})")
    return {"time_s": time_s, "distance_m": dist_m, "picked": picked}


def saving_pct(before, after):
    return 100.0 * (before - after) / before if before else 0.0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", required=True, help="supermarket map JSON")
    ap.add_argument("--list", required=True, dest="listfile", help="shopping list, ID:short name per line")
    ap.add_argument("--speed", type=float, default=WALK_SPEED_M_S, help="walking speed in m/s")
    ap.add_argument("--pick-seconds", type=float, default=PICK_SECONDS, help="seconds per picked item")
    ap.add_argument("--delay", type=float, default=0.0, help="real seconds to sleep per walked cell")
    ap.add_argument("--trace", action="store_true", help="print every walked cell, not just picks")
    args = ap.parse_args(argv)
    try:
        grid, entrance, products = load_map(args.map)
        picks = load_list(args.listfile, products)
        stops = [entrance] + [products[pid][1] for pid in picks]
        labels = ["ENTRANCE"] + [f"{pid} {products[pid][0]}" for pid in picks]
        d = distance_matrix(grid, stops, labels)
    except (ValueError, KeyError, OSError) as e:
        sys.exit(f"error: {e}")

    routes = {
        "list order": list(range(len(stops))),
        "optimized": plan(d),
    }
    results = {}
    for title, cycle in routes.items():
        print(f"== {title} route ==", flush=True)
        results[title] = simulate(grid, stops, labels, cycle, args.speed, args.pick_seconds,
                                  emit=lambda msg: print(msg, flush=True),
                                  delay=args.delay, trace=args.trace)

    base, opt = results["list order"], results["optimized"]
    time_pct = saving_pct(base["time_s"], opt["time_s"])
    dist_pct = saving_pct(base["distance_m"], opt["distance_m"])
    print()
    print(f"{'route':<12}{'time-to-prepare':>18}{'distance':>14}{'picks':>8}")
    for title in routes:
        r = results[title]
        print(f"{title:<12}{r['time_s']:>15.1f} s{r['distance_m']:>11.1f} m{r['picked']:>8}")
    print(f"time saved: {time_pct:.1f}%   distance saved: {dist_pct:.1f}%")
    print(f"target (>= {TARGET_SAVING_PCT:.0f}% time saved): {'met' if time_pct >= TARGET_SAVING_PCT else 'not met'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
