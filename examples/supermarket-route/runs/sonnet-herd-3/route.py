"""Supermarket pick-route optimizer, step-by-step simulator and KPI comparison.

Map JSON: {"grid": ["#####", "#S..#", ...], "products": [{"id": "p1", "name": "milk", "row": 0, "col": 2}]}
  '#' blocked (walls, shelves), '.' floor, 'S' start/packing point (exactly one).
  A product sits on any cell; the picker takes it from that cell if it is floor,
  or from any floor cell next to it (shelf).
List file: one "id:short name" per line.
"""
import argparse
import json
import random
import sys
from collections import deque

MOVES = ((1, 0), (-1, 0), (0, 1), (0, -1))


class RouteError(Exception):
    pass


def load_store(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise RouteError(f"cannot read map {path}: {e.strerror}")
    except ValueError as e:
        raise RouteError(f"map {path} is not valid JSON: {e}")
    return parse_store(data)


def parse_store(data):
    if not isinstance(data, dict) or not isinstance(data.get("grid"), list) or not data["grid"]:
        raise RouteError("map needs a non-empty 'grid' list of strings")
    grid = data["grid"]
    if not all(isinstance(r, str) for r in grid) or len({len(r) for r in grid}) != 1 or not grid[0]:
        raise RouteError("map 'grid' rows must be non-empty strings of equal length")
    starts = []
    for r, row in enumerate(grid):
        for c, ch in enumerate(row):
            if ch not in "#.S":
                raise RouteError(f"map grid has unknown character {ch!r} at row {r}, col {c}")
            if ch == "S":
                starts.append((r, c))
    if len(starts) != 1:
        raise RouteError(f"map grid needs exactly one 'S' start cell, found {len(starts)}")
    prods = {}
    plist = data.get("products")
    if not isinstance(plist, list):
        raise RouteError("map needs a 'products' list")
    for p in plist:
        if not isinstance(p, dict) or not isinstance(p.get("id"), str) or not p["id"]:
            raise RouteError(f"product needs a string 'id': {p!r}")
        r, c = p.get("row"), p.get("col")
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (r, c)):
            raise RouteError(f"product {p['id']} needs integer 'row' and 'col'")
        if not (0 <= r < len(grid) and 0 <= c < len(grid[0])):
            raise RouteError(f"product {p['id']} is outside the grid at ({r}, {c})")
        if p["id"] in prods:
            raise RouteError(f"duplicate product id in map: {p['id']}")
        prods[p["id"]] = {"name": str(p.get("name", "")), "pos": (r, c)}
    return {"grid": grid, "start": starts[0], "products": prods}


def load_list(path):
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as e:
        raise RouteError(f"cannot read list {path}: {e.strerror}")
    except UnicodeDecodeError:
        raise RouteError(f"list {path} is not UTF-8 text")
    items = []
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        pid, sep, name = line.partition(":")
        if not sep or not pid.strip():
            raise RouteError(f"list line {n} is not 'id:short name': {line!r}")
        items.append((pid.strip(), name.strip()))
    if not items:
        raise RouteError("shopping list is empty")
    return items


def resolve(store, items):
    """Return [(id, access_cells)] in list order; fail clearly on bad items."""
    grid, out, seen = store["grid"], [], set()
    for pid, name in items:
        if pid in seen:
            raise RouteError(f"duplicate id in list: {pid}")
        seen.add(pid)
        p = store["products"].get(pid)
        if p is None:
            raise RouteError(f"unknown product id in list: {pid}")
        if name and p["name"] and name != p["name"]:
            raise RouteError(f"product {pid} is named {p['name']!r} in the map, {name!r} in the list")
        r, c = p["pos"]
        cells = [(r, c)] if grid[r][c] != "#" else [
            (r + dr, c + dc) for dr, dc in MOVES
            if 0 <= r + dr < len(grid) and 0 <= c + dc < len(grid[0]) and grid[r + dr][c + dc] != "#"]
        out.append((pid, cells))
    return out


def bfs(grid, sources):
    h, w = len(grid), len(grid[0])
    dist = {s: 0 for s in sources}
    q = deque(sources)
    while q:
        r, c = q.popleft()
        for dr, dc in MOVES:
            n = (r + dr, c + dc)
            if 0 <= n[0] < h and 0 <= n[1] < w and grid[n[0]][n[1]] != "#" and n not in dist:
                dist[n] = dist[(r, c)] + 1
                q.append(n)
    return dist


def leg(grid, cur, targets):
    """Shortest path from cur to the nearest target cell; returns list of cells after cur, or None."""
    targets = set(targets)
    if cur in targets:
        return []
    h, w = len(grid), len(grid[0])
    par = {cur: None}
    q = deque([cur])
    while q:
        r, c = q.popleft()
        for dr, dc in MOVES:
            n = (r + dr, c + dc)
            if 0 <= n[0] < h and 0 <= n[1] < w and grid[n[0]][n[1]] != "#" and n not in par:
                par[n] = (r, c)
                if n in targets:
                    path = [n]
                    while par[path[-1]] != cur:
                        path.append(par[path[-1]])
                    return path[::-1]
                q.append(n)
    return None


def optimize(store, stops):
    """Order of indices into stops: nearest neighbour then 2-opt/or-opt on a closed tour from the start."""
    grid = store["grid"]
    sets = [[store["start"]]] + [cells for _, cells in stops]
    n = len(sets)
    D = [[0] * n for _ in range(n)]
    for i in range(n):
        d = bfs(grid, sets[i])
        for j in range(n):
            if j != i:
                v = min((d[c] for c in sets[j] if c in d), default=None)
                if v is None:
                    raise RouteError(f"product {stops[j - 1][0]} cannot be reached from the start")
                D[i][j] = v
    tour, left = [0], set(range(1, n))
    while left:
        nxt = min(left, key=lambda j: D[tour[-1]][j])
        tour.append(nxt)
        left.remove(nxt)
    tour.append(0)

    def cost(t):
        return sum(D[a][b] for a, b in zip(t, t[1:]))
    improved = True
    while improved:
        improved = False
        for i in range(1, len(tour) - 1):  # 2-opt
            for j in range(i + 1, len(tour) - 1):
                new = tour[:i] + tour[i:j + 1][::-1] + tour[j + 1:]
                if cost(new) < cost(tour):
                    tour, improved = new, True
        for i in range(1, len(tour) - 1):  # or-opt: move one stop
            for j in range(1, len(tour) - 1):
                if i != j:
                    new = tour[:i] + tour[i + 1:]
                    new.insert(j, tour[i])
                    if cost(new) < cost(tour):
                        tour, improved = new, True
    return [i - 1 for i in tour[1:-1]]


def simulate(store, stops, order, speed=1.0, pick_s=10.0):
    """Yield one event per step: dict(t, distance, pos, picked, event). Walks back to start at the end."""
    grid, cur = store["grid"], store["start"]
    t, dist, picked = 0.0, 0, 0
    yield {"t": t, "distance": dist, "pos": cur, "picked": 0, "event": "start"}
    for k in order:
        pid, cells = stops[k]
        path = leg(grid, cur, cells)
        if path is None:
            raise RouteError(f"product {pid} cannot be reached from the start")
        for cell in path:
            cur, dist, t = cell, dist + 1, t + 1 / speed
            yield {"t": t, "distance": dist, "pos": cur, "picked": picked, "event": "move"}
        picked, t = picked + 1, t + pick_s
        yield {"t": t, "distance": dist, "pos": cur, "picked": picked, "event": f"pick {pid}"}
    for cell in leg(grid, cur, [store["start"]]):
        cur, dist, t = cell, dist + 1, t + 1 / speed
        yield {"t": t, "distance": dist, "pos": cur, "picked": picked, "event": "move"}
    yield {"t": t, "distance": dist, "pos": cur, "picked": picked, "event": "done"}


def compare(store, items, speed=1.0, pick_s=10.0):
    stops = resolve(store, items)
    res = {}
    for name, order in (("list", list(range(len(stops)))), ("optimized", optimize(store, stops))):
        last = list(simulate(store, stops, order, speed, pick_s))[-1]
        res[name] = {"time_s": last["t"], "distance": last["distance"], "order": [stops[k][0] for k in order]}
    res["saving_pct"] = 100 * (1 - res["optimized"]["time_s"] / res["list"]["time_s"])
    return res


def make_store(rows, cols, layout="aisles", seed=0, n_products=None):
    """Generated store. layout: aisles | random | open-pillars. Products sit on shelf cells."""
    rng = random.Random(seed)
    g = [["."] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            if r in (0, rows - 1) or c in (0, cols - 1):
                g[r][c] = "#"
    if layout == "aisles":
        for c in range(3, cols - 2, 3):
            for r in range(2, rows - 2):
                g[r][c] = "#"
    elif layout == "random":
        for _ in range(rows * cols // 6):
            g[rng.randrange(1, rows - 1)][rng.randrange(1, cols - 1)] = "#"
    elif layout == "open-pillars":
        for r in range(2, rows - 2, 3):
            for c in range(2, cols - 2, 3):
                g[r][c] = "#"
    else:
        raise RouteError(f"unknown layout {layout}")
    for k in range(1, max(rows, cols) - 1):  # open ring along the inner walls so the start is never boxed in
        for r, c in ((1, k), (k, 1), (rows - 2, k), (k, cols - 2)):
            if r < rows - 1 and c < cols - 1:
                g[r][c] = "."
    g[1][1] = "S"
    reach = bfs(["".join(r) for r in g], [(1, 1)])
    shelves = [(r, c) for r in range(rows) for c in range(cols) if g[r][c] == "#"
               and any((r + dr, c + dc) in reach for dr, dc in MOVES)]
    rng.shuffle(shelves)
    n = min(len(shelves), n_products or max(10, len(shelves) // 2))
    prods = [{"id": f"p{i}", "name": f"item{i}", "row": r, "col": c} for i, (r, c) in enumerate(shelves[:n])]
    return {"grid": ["".join(r) for r in g], "products": prods}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "demo"):
        p = sub.add_parser(name)
        if name == "run":
            p.add_argument("map")
            p.add_argument("list")
        else:
            p.add_argument("--size", default="40x60", help="ROWSxCOLS")
            p.add_argument("--layout", default="aisles")
            p.add_argument("--seed", type=int, default=1)
            p.add_argument("--items", type=int, default=20)
        p.add_argument("--speed", type=float, default=1.0, help="cells per second")
        p.add_argument("--pick-s", type=float, default=10.0, help="seconds to pick one product")
        p.add_argument("--steps", action="store_true", help="print every step with live KPIs")
    a = ap.parse_args(argv)
    try:
        if a.speed <= 0 or a.pick_s < 0:
            raise RouteError("--speed must be positive and --pick-s not negative")
        if a.cmd == "run":
            store, items = load_store(a.map), load_list(a.list)
        else:
            try:
                rows, cols = (int(x) for x in a.size.lower().split("x"))
                if rows < 5 or cols < 5:
                    raise ValueError
            except ValueError:
                raise RouteError("--size must look like 40x60 (at least 5x5)")
            if a.items < 1:
                raise RouteError("--items must be at least 1")
            store = parse_store(make_store(rows, cols, a.layout, a.seed))
            ids = sorted(store["products"], key=lambda s: int(s[1:]))
            pick = random.Random(a.seed).sample(ids, min(a.items, len(ids)))
            items = [(i, store["products"][i]["name"]) for i in pick]
        stops = resolve(store, items)
        for name, order in (("list-order", list(range(len(stops)))), ("optimized", optimize(store, stops))):
            print(f"== {name} route")
            ev = None
            for ev in simulate(store, stops, order, a.speed, a.pick_s):
                if a.steps or ev["event"] not in ("move",):
                    print(f"t={ev['t']:8.1f}s distance={ev['distance']:6d} picked={ev['picked']:3d} at={ev['pos']} {ev['event']}")
            print(f"{name}: time-to-prepare-basket={ev['t']:.1f}s distance-covered={ev['distance']}")
        res = compare(store, items, a.speed, a.pick_s)
        print(f"time saved: {res['saving_pct']:.1f}% (list {res['list']['time_s']:.1f}s, optimized {res['optimized']['time_s']:.1f}s)")
    except RouteError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
