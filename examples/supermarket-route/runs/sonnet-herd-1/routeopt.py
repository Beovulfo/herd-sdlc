"""Supermarket pick-route optimizer: any grid layout, any size. Standard library only.

Map JSON: {"grid": ["#####", "E...C", ...], "products": [{"id": "P1", "name": "milk", "x": 2, "y": 0}]}
  grid chars: '#' blocked (shelf or wall), '.' floor, 'E' entrance (start, exactly one),
  'C' checkout (end, optional, defaults to entrance). Products may sit on shelf or floor cells;
  the picker stands on a walkable cell (the product cell itself, else a 4-neighbour).
List file: one "id:short name" per line; blank lines and '#' lines are ignored.
"""
import argparse
import json
import random
import sys
import time
from collections import deque


class RouteError(Exception):
    pass


def load_map(path):
    try:
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
    except OSError as e:
        raise RouteError(f"cannot read map {path}: {e.strerror}")
    except (ValueError, UnicodeDecodeError) as e:
        raise RouteError(f"map {path} is not valid JSON: {e}")
    return parse_map(m)


def parse_map(m):
    if not isinstance(m, dict) or not isinstance(m.get("grid"), list) or not m["grid"]:
        raise RouteError('map must be an object with a non-empty "grid" list of strings')
    grid = m["grid"]
    if not all(isinstance(r, str) for r in grid):
        raise RouteError("every grid row must be a string")
    w = len(grid[0])
    if w == 0 or any(len(r) != w for r in grid):
        raise RouteError("grid rows must be non-empty and the same length")
    h = len(grid)
    start = end = None
    for y, row in enumerate(grid):
        for x, c in enumerate(row):
            if c not in "#.EC":
                raise RouteError(f"unknown grid character {c!r} at x={x} y={y}")
            if c == "E":
                if start:
                    raise RouteError("grid has more than one entrance 'E'")
                start = (x, y)
            if c == "C":
                if end:
                    raise RouteError("grid has more than one checkout 'C'")
                end = (x, y)
    if start is None:
        raise RouteError("grid has no entrance 'E'")
    prods = {}
    plist = m.get("products", [])
    if not isinstance(plist, list):
        raise RouteError('"products" must be a list')
    for i, p in enumerate(plist):
        if (not isinstance(p, dict) or not isinstance(p.get("id"), str) or not p["id"].strip()
                or not isinstance(p.get("name", ""), str)
                or not all(type(p.get(k)) is int for k in ("x", "y"))):
            raise RouteError(f"products[{i}] needs a string id and integer x, y")
        if not (0 <= p["x"] < w and 0 <= p["y"] < h):
            raise RouteError(f"product {p['id']} is outside the grid")
        if p["id"] in prods:
            raise RouteError(f"duplicate product id {p['id']} in map")
        prods[p["id"]] = (p.get("name", ""), p["x"], p["y"])
    return {"grid": grid, "w": w, "h": h, "start": start, "end": end or start, "products": prods}


def load_list(path):
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as e:
        raise RouteError(f"cannot read list {path}: {e.strerror}")
    except UnicodeDecodeError:
        raise RouteError(f"list {path} is not valid UTF-8 text")
    return parse_list(lines)


def parse_list(lines):
    items = []
    for n, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pid, sep, name = line.partition(":")
        if not sep or not pid.strip():
            raise RouteError(f'list line {n}: expected "id:short name", got {line!r}')
        items.append((pid.strip(), name.strip()))
    if not items:
        raise RouteError("shopping list is empty")
    return items


def bfs(m, src):
    """Flat list of walking distances (in cells) from src; -1 when unreachable."""
    w, h, g = m["w"], m["h"], m["grid"]
    dist = [-1] * (w * h)
    dist[src[1] * w + src[0]] = 0
    q = deque([src])
    while q:
        x, y = q.popleft()
        d = dist[y * w + x] + 1
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and g[ny][nx] != "#" and dist[ny * w + nx] < 0:
                dist[ny * w + nx] = d
                q.append((nx, ny))
    return dist


def pick_cells(m, items):
    """Map each requested id to the walkable cell where the picker stands. Fails on unknown/unreachable."""
    from_start = bfs(m, m["start"])
    w, g = m["w"], m["grid"]
    cells = {}
    for pid, _ in items:
        if pid in cells:
            continue
        if pid not in m["products"]:
            raise RouteError(f"product {pid} is not in the map")
        _, x, y = m["products"][pid]
        cand = [(x, y)] if g[y][x] != "#" else [
            (nx, ny) for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
            if 0 <= nx < m["w"] and 0 <= ny < m["h"] and g[ny][nx] != "#"]
        cand = [c for c in cand if from_start[c[1] * w + c[0]] >= 0]
        if not cand:
            raise RouteError(f"product {pid} cannot be reached from the entrance")
        cells[pid] = min(cand, key=lambda c: from_start[c[1] * w + c[0]])
    if from_start[m["end"][1] * w + m["end"][0]] < 0:
        raise RouteError("checkout cannot be reached from the entrance")
    return cells


def _cost(path, D):
    return sum(D[a][b] for a, b in zip(path, path[1:]))


def optimize(D, n):
    """Order nodes 1..n (0 = start, n+1 = end) minimising walking distance: nearest neighbour, then 2-opt + relocate."""
    path, left = [0], set(range(1, n + 1))
    while left:
        nxt = min(left, key=lambda j: D[path[-1]][j])
        path.append(nxt)
        left.discard(nxt)
    path.append(n + 1)
    improved = True
    while improved:
        improved = False
        for i in range(1, n):  # 2-opt: reverse path[i..j]
            for j in range(i + 1, n + 1):
                a, b, c, d = path[i - 1], path[i], path[j], path[j + 1]
                if D[a][c] + D[b][d] < D[a][b] + D[c][d]:
                    path[i:j + 1] = reversed(path[i:j + 1])
                    improved = True
        for i in range(1, n + 1):  # relocate one node
            node = path[i]
            rest = path[:i] + path[i + 1:]
            base = _cost(path, D)
            for k in range(1, len(rest)):
                cand = rest[:k] + [node] + rest[k:]
                if _cost(cand, D) < base:
                    path, improved = cand, True
                    break
    return path[1:-1]


def plan(m, items):
    """Return (list_order_cells, optimized_cells): ordered pick stops as lists of (cell, [item,...])."""
    cells = pick_cells(m, items)
    uniq = sorted(set(cells.values()))
    nodes = [m["start"]] + uniq + [m["end"]]
    w = m["w"]
    D = []
    for a in nodes:
        dist = bfs(m, a)
        D.append([dist[b[1] * w + b[0]] for b in nodes])
    if any(v < 0 for row in D for v in row):
        raise RouteError("a requested product or the checkout is not connected to the rest of the store")
    order = optimize(D, len(uniq))
    by_cell = {}
    for it in items:
        by_cell.setdefault(cells[it[0]], []).append(it)
    naive = [(cells[it[0]], [it]) for it in items]
    best = [(uniq[i - 1], by_cell[uniq[i - 1]]) for i in order]
    return naive, best


def simulate(m, stops, speed=1.2, cell_m=1.0, pick_s=8.0):
    """Yield one event per step: a move of one cell, or a pick. KPIs are cumulative at that moment."""
    w = m["w"]
    pos, cells, t, picked = m["start"], 0, 0.0, 0
    yield {"event": "start", "pos": pos, "cells": 0, "distance_m": 0.0, "time_s": 0.0, "picked": 0}
    targets = [(c, its) for c, its in stops] + [(m["end"], [])]
    for cell, its in targets:
        if cell != pos:
            dist = bfs(m, pos)
            path, cur = [], cell
            while cur != pos:
                path.append(cur)
                x, y = cur
                cur = next(nb for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
                           if 0 <= nb[0] < w and 0 <= nb[1] < m["h"] and dist[nb[1] * w + nb[0]] == dist[y * w + x] - 1)
            for step in reversed(path):
                pos, cells = step, cells + 1
                t += cell_m / speed
                yield {"event": "move", "pos": pos, "cells": cells, "distance_m": cells * cell_m,
                       "time_s": t, "picked": picked}
        for pid, name in its:
            t += pick_s
            picked += 1
            yield {"event": f"pick {pid} {name}".strip(), "pos": pos, "cells": cells,
                   "distance_m": cells * cell_m, "time_s": t, "picked": picked}
    yield {"event": "done", "pos": pos, "cells": cells, "distance_m": cells * cell_m, "time_s": t, "picked": picked}


def final(events):
    last = None
    for last in events:
        pass
    return last


def compare(m, items, **kw):
    naive, best = plan(m, items)
    a, b = final(simulate(m, naive, **kw)), final(simulate(m, best, **kw))
    return {"naive": a, "optimized": b,
            "time_saved_pct": 100 * (a["time_s"] - b["time_s"]) / a["time_s"] if a["time_s"] else 0.0,
            "distance_saved_pct": 100 * (a["distance_m"] - b["distance_m"]) / a["distance_m"] if a["distance_m"] else 0.0}


def generate(w, h, n_products, seed=0, layout="aisles"):
    """Synthetic store for tests and benchmarks. layouts: aisles (parallel shelves), rooms (random blocks), open."""
    rnd = random.Random(seed)
    g = [["." for _ in range(w)] for _ in range(h)]
    if layout == "aisles":
        for x in range(2, w - 2, 3):
            for y in range(2, h - 2):
                g[y][x] = "#"
    elif layout == "rooms":
        for _ in range(w * h // 12):
            g[rnd.randrange(1, h - 1)][rnd.randrange(1, w - 1)] = "#"
    g[0][0] = "E"
    g[h - 1][w - 1] = "C"
    shelves = [(x, y) for y in range(h) for x in range(w) if g[y][x] == "#"] or \
              [(x, y) for y in range(h) for x in range(w) if g[y][x] == "."]
    spots = rnd.sample(shelves, min(n_products, len(shelves)))
    prods = [{"id": f"P{i}", "name": f"item{i}", "x": x, "y": y} for i, (x, y) in enumerate(spots)]
    return {"grid": ["".join(r) for r in g], "products": prods}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Supermarket pick-route optimizer")
    ap.add_argument("map")
    ap.add_argument("list")
    ap.add_argument("--simulate", action="store_true", help="print every step with live KPIs")
    ap.add_argument("--delay", type=float, default=0.0, help="seconds to sleep between steps")
    ap.add_argument("--speed", type=float, default=1.2, help="walking speed, m/s")
    ap.add_argument("--cell-m", type=float, default=1.0, help="metres per grid cell")
    ap.add_argument("--pick-s", type=float, default=8.0, help="seconds to pick one item")
    a = ap.parse_args(argv)
    try:
        if a.speed <= 0 or a.cell_m <= 0 or a.pick_s < 0:
            raise RouteError("speed and cell-m must be > 0, pick-s >= 0")
        m, items = load_map(a.map), load_list(a.list)
        naive, best = plan(m, items)
        kw = dict(speed=a.speed, cell_m=a.cell_m, pick_s=a.pick_s)
        res = {}
        for label, stops in (("list-order", naive), ("optimized", best)):
            for ev in simulate(m, stops, **kw):
                if a.simulate:
                    print(f"[{label}] {ev['event']:<28} at {ev['pos']} distance={ev['distance_m']:.1f}m "
                          f"time={ev['time_s']:.1f}s picked={ev['picked']}")
                    if a.delay:
                        time.sleep(a.delay)
            res[label] = ev
        for label, ev in res.items():
            print(f"{label:<10} time-to-prepare-basket={ev['time_s']:.1f}s distance-covered={ev['distance_m']:.1f}m")
        n, o = res["list-order"], res["optimized"]
        print(f"time saved: {100 * (n['time_s'] - o['time_s']) / n['time_s']:.1f}%  "
              f"distance saved: {100 * (n['distance_m'] - o['distance_m']) / n['distance_m']:.1f}%"
              if n["time_s"] and n["distance_m"] else "time saved: 0.0%")
    except RouteError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
