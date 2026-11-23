"""Supermarket pick-route optimizer. Python stdlib only.

Map JSON: {"grid": ["#####", "S..P."...], "start": [r, c], "products": [{"id": "P1", "name": "milk", "pos": [r, c]}]}
Grid chars: '#' blocked, anything else walkable. A product on a blocked cell (a shelf) is picked from
the nearest walkable neighbour. Moves are 4-directional, 1 cell = cell_m metres.
List file: one "id:short name" per line. A repeated id means another unit (picked again).
"""
import argparse
import json
import random
import sys
from collections import deque

SPEED = 1.2  # m/s walking
PICK_S = 5.0  # seconds per item
CELL_M = 1.0


class Err(Exception):
    pass


def load_map(path):
    try:
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
    except OSError as e:
        raise Err(f"cannot read map {path}: {e.strerror}")
    except ValueError as e:
        raise Err(f"map {path} is not valid JSON: {e}")
    try:
        grid = m["grid"]
        if not (isinstance(grid, list) and grid and all(isinstance(r, str) for r in grid)):
            raise ValueError
        w = len(grid[0])
        if w == 0 or any(len(r) != w for r in grid):
            raise Err("map grid must be non-empty rows of equal length")
        start = tuple(m["start"])
        if not (len(start) == 2 and all(type(v) is int for v in start)):
            raise ValueError
        if not isinstance(m["products"], list):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise Err("map needs 'grid' (list of equal-length strings), 'start' [row, col], 'products' (list)")
    if not walkable(grid, start):
        raise Err(f"map start {list(start)} is not a walkable cell")
    return m


def walkable(grid, p):
    r, c = p
    return 0 <= r < len(grid) and 0 <= c < len(grid[0]) and grid[r][c] != "#"


def parse_list(path):
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as e:
        raise Err(f"cannot read list {path}: {e.strerror}")
    except UnicodeDecodeError:
        raise Err(f"list {path} is not text")
    items = []
    for n, ln in enumerate(lines, 1):
        if not ln.strip():
            continue
        pid, sep, name = ln.partition(":")
        if not sep or not pid.strip():
            raise Err(f"list line {n}: expected 'id:short name', got {ln!r}")
        items.append((pid.strip(), name.strip()))
    if not items:
        raise Err("shopping list is empty")
    return items


def bfs(grid, src, want=None):
    """Distances and parents from src over walkable cells; stops early once all `want` cells are seen."""
    h, w = len(grid), len(grid[0])
    dist = {src: 0}
    par = {src: None}
    left = set(want or ())
    left.discard(src)
    q = deque([src])
    while q and (want is None or left):
        cur = q.popleft()
        r, c = cur
        for nxt in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if nxt not in dist and 0 <= nxt[0] < h and 0 <= nxt[1] < w and grid[nxt[0]][nxt[1]] != "#":
                dist[nxt] = dist[cur] + 1
                par[nxt] = cur
                left.discard(nxt)
                q.append(nxt)
    return dist, par


def resolve(m, items):
    """Map each requested item to a walkable access cell. Only requested products are validated."""
    grid = m["grid"]
    by_id = {}
    for p in m["products"]:
        if isinstance(p, dict) and "id" in p:
            by_id.setdefault(str(p["id"]), []).append(p)
    dist0, _ = bfs(grid, tuple(m["start"]))
    stops = []
    for pid, name in items:
        ps = by_id.get(pid)
        if not ps:
            raise Err(f"product id {pid!r} is not in the map")
        if len(ps) > 1:
            raise Err(f"product id {pid!r} appears {len(ps)} times in the map")
        p = ps[0]
        if name and p.get("name") and name != p["name"]:
            raise Err(f"product {pid!r}: list says {name!r}, map says {p['name']!r}")
        pos = p.get("pos")
        if not (isinstance(pos, list) and len(pos) == 2 and all(type(v) is int for v in pos)):
            raise Err(f"product {pid!r} has a malformed position")
        r, c = pos
        if not (0 <= r < len(grid) and 0 <= c < len(grid[0])):
            raise Err(f"product {pid!r} is outside the map")
        cands = [q for q in ((r, c), (r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)) if walkable(grid, q)]
        cands = [q for q in cands if q in dist0]
        if not cands:
            raise Err(f"product {pid!r} at {pos} is unreachable from the start")
        stops.append((pid, min(cands, key=lambda q: (dist0[q], q))))
    return stops


def tour_len(order, d):
    return sum(d[a][b] for a, b in zip(order, order[1:]))


def optimize(d):
    """Closed tour over nodes 0..n (0 = start): best of nearest-neighbour+2-opt and list order+2-opt."""
    n = len(d)

    def two_opt(t):
        improved = True
        while improved:
            improved = False
            for i in range(1, n - 1):
                for j in range(i + 1, n):
                    a, b, c, e = t[i - 1], t[i], t[j], t[(j + 1) % n]
                    if d[a][c] + d[b][e] < d[a][b] + d[c][e]:
                        t[i:j + 1] = t[i:j + 1][::-1]
                        improved = True
        return t

    nn, left = [0], set(range(1, n))
    while left:
        nxt = min(left, key=lambda k: (d[nn[-1]][k], k))
        nn.append(nxt)
        left.remove(nxt)
    best = None
    for t in (two_opt(nn), two_opt(list(range(n)))):
        if best is None or tour_len(t + [0], d) < tour_len(best + [0], d):
            best = t
    return best


def simulate(grid, start, stops, order):
    """Yield one event per step: (kind, cell, label, distance_m, time_s). kind is move or pick."""
    cur, dist_m, t = start, 0.0, 0.0
    for idx in order + [None]:
        dst = start if idx is None else stops[idx - 1][1]
        _, par = bfs(grid, cur, [dst])
        path = []
        p = dst
        while p != cur:
            path.append(p)
            p = par[p]
        for cell in reversed(path):
            dist_m += CELL_M
            t += CELL_M / SPEED
            yield "move", cell, "", dist_m, t
        cur = dst
        if idx is not None:
            t += PICK_S
            yield "pick", cur, stops[idx - 1][0], dist_m, t


def plan(m, items):
    grid, start = m["grid"], tuple(m["start"])
    stops = resolve(m, items)
    nodes = [start] + [s[1] for s in stops]
    d = [[0] * len(nodes) for _ in nodes]
    for i, a in enumerate(nodes):
        dist, _ = bfs(grid, a, nodes)
        for j, b in enumerate(nodes):
            if b not in dist:
                raise Err("a requested product cannot be reached from another (disconnected map)")
            d[i][j] = dist[b]
    opt = optimize(d)[1:]
    return grid, start, stops, list(range(1, len(nodes))), opt


def run(m, items, trace=None):
    grid, start, stops, naive, opt = plan(m, items)
    res = {}
    for name, order in (("list-order", naive), ("optimized", opt)):
        last = None
        for kind, cell, label, dm, t in simulate(grid, start, stops, order):
            if trace:
                trace(name, kind, cell, label, dm, t)
            last = (dm, t)
        res[name] = {"distance_m": last[0], "time_s": last[1]}
    a, b = res["list-order"], res["optimized"]
    res["time_saved_pct"] = 100 * (a["time_s"] - b["time_s"]) / a["time_s"]
    res["distance_saved_pct"] = 100 * (a["distance_m"] - b["distance_m"]) / a["distance_m"] if a["distance_m"] else 0.0
    return res


def gen_map(kind, size, n_products, seed):
    rnd = random.Random(seed)
    g = [["."] * size for _ in range(size)]
    if kind == "aisles":  # shelf rows with gaps, like a store; cross aisles every 8th row/col
        for r in range(2, size - 2):
            if r % 4 in (1, 2):
                for c in range(2, size - 2):
                    g[r][c] = "#"
        for r in range(size):
            for c in range(size):
                if g[r][c] == "#" and (c % 12 == 0):
                    g[r][c] = "."
    elif kind == "maze":  # random obstacles, then keep only the start's component
        for r in range(size):
            for c in range(size):
                if rnd.random() < 0.3:
                    g[r][c] = "#"
    elif kind != "open":
        raise Err(f"unknown layout {kind!r}: use aisles, open or maze")
    for r in range(min(3, size)):  # keep the start corner open so the store is never sealed
        for c in range(min(3, size)):
            g[r][c] = "."
    grid = ["".join(r) for r in g]
    dist, _ = bfs(grid, (0, 0))
    shelves = [(r, c) for r in range(size) for c in range(size) if grid[r][c] == "#"
               and any(q in dist for q in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)))]
    cells = shelves or sorted(dist)
    pos = rnd.sample(cells, min(n_products, len(cells)))
    products = [{"id": f"P{i}", "name": f"item{i}", "pos": list(p)} for i, p in enumerate(pos)]
    return {"grid": grid, "start": [0, 0], "products": products}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="routeopt")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen", help="write a generated store map")
    g.add_argument("--kind", default="aisles")
    g.add_argument("--size", type=int, default=60)
    g.add_argument("--products", type=int, default=500)
    g.add_argument("--seed", type=int, default=1)
    g.add_argument("--out", required=True)
    r = sub.add_parser("run", help="simulate list-order vs optimized picking")
    r.add_argument("map")
    r.add_argument("list")
    r.add_argument("--trace", action="store_true", help="print every step with running KPIs")
    r.add_argument("--min-saving", type=float, help="exit 1 if time saved is below this percent")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "gen":
            if a.size < 3 or a.products < 1:
                raise Err("--size must be >= 3 and --products >= 1")
            with open(a.out, "w", encoding="utf-8") as f:
                json.dump(gen_map(a.kind, a.size, a.products, a.seed), f)
            print(f"wrote {a.out}")
            return 0
        m = load_map(a.map)
        items = parse_list(a.list)

        def tr(name, kind, cell, label, dm, t):
            print(f"{name:10} {kind:4} {cell[0]},{cell[1]} {label:8} distance={dm:.0f}m time={t:.1f}s")

        res = run(m, items, tr if a.trace else None)
        for k in ("list-order", "optimized"):
            print(f"{k:10} distance={res[k]['distance_m']:.0f}m time-to-prepare-basket={res[k]['time_s']:.1f}s")
        print(f"saved: time {res['time_saved_pct']:.1f}% distance {res['distance_saved_pct']:.1f}%")
        if a.min_saving is not None and res["time_saved_pct"] < a.min_saving:
            print(f"FAIL: saving below {a.min_saving}%", file=sys.stderr)
            return 1
        return 0
    except Err as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
