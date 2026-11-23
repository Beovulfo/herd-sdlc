"""Supermarket pick-route optimizer and step-by-step simulator. Standard library only.

Map JSON: {"grid": ["..#.", ...], "start": [x, y], "checkout": [x, y] (optional),
           "products": [{"id": "P1", "name": "milk", "x": 2, "y": 0}, ...]}
Grid: '#' blocked (shelf, wall), any other char walkable. A product may sit on a blocked
cell (shelf); it is picked from the walkable neighbour nearest the start.
List file: one "id:short name" per line; blank lines and '#' comments are ignored.
Cell = 1 m. Time = walking distance / speed + pick time per item.
"""
import argparse
import json
import random
import sys
import time
from collections import deque

SPEED = 1.4   # m/s walking
PICK_S = 5.0  # seconds per item picked


class MapError(ValueError):
    pass


# ---------- loading ----------

def load_map(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise MapError(f"cannot read map {path}: {e.strerror}")
    except (ValueError, UnicodeDecodeError) as e:
        raise MapError(f"map {path} is not valid JSON: {e}")
    return parse_map(data)


def parse_map(data):
    if not isinstance(data, dict):
        raise MapError("map must be a JSON object")
    grid = data.get("grid")
    if (not isinstance(grid, list) or not grid
            or not all(isinstance(r, str) for r in grid) or not grid[0]):
        raise MapError("map 'grid' must be a non-empty list of strings")
    w, h = len(grid[0]), len(grid)
    if any(len(r) != w for r in grid):
        raise MapError("map 'grid' rows must all have the same length")
    walk = [[c != "#" for c in r] for r in grid]

    def cell(key, required):
        v = data.get(key)
        if v is None and not required:
            return None
        if (not isinstance(v, list) or len(v) != 2
                or not all(isinstance(i, int) and not isinstance(i, bool) for i in v)):
            raise MapError(f"map '{key}' must be [x, y] integers")
        x, y = v
        if not (0 <= x < w and 0 <= y < h):
            raise MapError(f"map '{key}' {v} is outside the {w}x{h} grid")
        if not walk[y][x]:
            raise MapError(f"map '{key}' {v} is on a blocked cell")
        return (x, y)

    start = cell("start", True)
    end = cell("checkout", False) or start
    prods, bad, warnings = {}, {}, []
    plist = data.get("products")
    if not isinstance(plist, list):
        raise MapError("map 'products' must be a list")
    for i, p in enumerate(plist):
        pid = p.get("id") if isinstance(p, dict) else None
        if not isinstance(pid, (str, int)) or isinstance(pid, bool) or str(pid) == "":
            warnings.append(f"products[{i}] has no usable id: skipped")
            continue
        pid = str(pid)
        x, y = p.get("x"), p.get("y")
        ok = all(isinstance(v, int) and not isinstance(v, bool) for v in (x, y)) \
            and 0 <= x < w and 0 <= y < h
        if pid in prods or pid in bad:
            raise MapError(f"duplicate product id {pid} in map")
        if not ok:
            bad[pid] = f"product {pid} has a missing or out-of-grid position"
            continue
        prods[pid] = (str(p.get("name", "")), x, y)
    return {"w": w, "h": h, "walk": walk, "start": start, "end": end,
            "products": prods, "bad": bad, "warnings": warnings}


def load_list(path):
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as e:
        raise MapError(f"cannot read list {path}: {e.strerror}")
    except UnicodeDecodeError:
        raise MapError(f"list {path} is not valid text")
    items = []
    for n, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pid, sep, name = line.partition(":")
        if not sep or not pid.strip():
            raise MapError(f"list line {n} must be 'id:short name', got {line!r}")
        items.append((pid.strip(), name.strip()))
    if not items:
        raise MapError("shopping list is empty")
    return items


# ---------- grid search ----------

class Grid:
    """Flat padded grid: a blocked border removes bounds checks from the BFS."""

    def __init__(self, m):
        self.W = m["w"] + 2
        self.H = m["h"] + 2
        self.ok = [False] * (self.W * self.H)
        for y, row in enumerate(m["walk"]):
            for x, v in enumerate(row):
                self.ok[(y + 1) * self.W + x + 1] = v
        self.d4 = (1, -1, self.W, -self.W)

    def idx(self, c):
        return (c[1] + 1) * self.W + c[0] + 1

    def xy(self, i):
        return (i % self.W - 1, i // self.W - 1)

    def bfs(self, src, targets=None):
        """Distances from src; stops early once every target is reached."""
        dist = [-1] * len(self.ok)
        dist[src] = 0
        q = deque([src])
        left = set(targets) if targets else None
        ok, d4 = self.ok, self.d4
        while q:
            u = q.popleft()
            if left is not None:
                left.discard(u)
                if not left:
                    break
            du = dist[u] + 1
            for d in d4:
                v = u + d
                if ok[v] and dist[v] < 0:
                    dist[v] = du
                    q.append(v)
        return dist

    def path(self, a, b):
        """Cells from a to b (excluding a) along a shortest path."""
        dist = self.bfs(b, [a])  # search from b so we can walk downhill from a
        out, u = [], a
        while u != b:
            for d in self.d4:
                v = u + d
                if self.ok[v] and dist[v] == dist[u] - 1:
                    u = v
                    break
            out.append(u)
        return out


def resolve(m, grid, items):
    """Map each requested item to (id, name, access cell index). Fails on a bad requested item."""
    from_start = grid.bfs(grid.idx(m["start"]))
    stops = []
    for pid, name in items:
        if pid in m["bad"]:
            raise MapError(m["bad"][pid])
        if pid not in m["products"]:
            raise MapError(f"requested product {pid} is not in the map")
        mname, x, y = m["products"][pid]
        if name and mname and name != mname:
            m["warnings"].append(f"product {pid}: list says {name!r}, map says {mname!r}")
        i = grid.idx((x, y))
        cands = [i] if grid.ok[i] else [i + d for d in grid.d4 if grid.ok[i + d]]
        cands = [c for c in cands if from_start[c] >= 0]
        if not cands:
            raise MapError(f"requested product {pid} ({mname}) is unreachable from the start")
        stops.append((pid, mname or name, min(cands, key=lambda c: from_start[c])))
    end = grid.idx(m["end"])
    if from_start[end] < 0:
        raise MapError("checkout is unreachable from the start")
    return stops, end


# ---------- optimization ----------

def matrix(grid, start, cells, end):
    """Distance matrix over nodes [start] + cells + [end]."""
    nodes = [start] + cells + [end]
    uniq = sorted(set(nodes))
    rows = {u: grid.bfs(u, uniq) for u in uniq}
    return [[rows[a][b] for b in nodes] for a in nodes]


def tour_len(d, order):
    n = len(d) - 1
    seq = [0] + order + [n]
    return sum(d[a][b] for a, b in zip(seq, seq[1:]))


def optimize(d, seconds=10.0):
    """Order of nodes 1..n-2 (picks). Best of nearest-neighbour and list order, then 2-opt + Or-opt."""
    n = len(d) - 1
    todo, cur, nn = set(range(1, n)), 0, []
    while todo:
        cur = min(todo, key=lambda j: d[cur][j])
        nn.append(cur)
        todo.discard(cur)
    order = min(nn, list(range(1, n)), key=lambda o: tour_len(d, o))
    deadline = time.time() + seconds
    seq = [0] + order + [n]
    improved = True
    while improved and time.time() < deadline:
        improved = False
        m = len(seq)
        for i in range(1, m - 2):  # 2-opt: reverse seq[i..j]
            for j in range(i + 1, m - 1):
                if d[seq[i - 1]][seq[j]] + d[seq[i]][seq[j + 1]] < d[seq[i - 1]][seq[i]] + d[seq[j]][seq[j + 1]]:
                    seq[i:j + 1] = reversed(seq[i:j + 1])
                    improved = True
        for i in range(1, m - 1):  # Or-opt: move one node elsewhere
            a, b, c = seq[i - 1], seq[i], seq[i + 1]
            gain = d[a][b] + d[b][c] - d[a][c]
            if gain <= 0:
                continue
            rest = seq[:i] + seq[i + 1:]
            best, at = 0, None
            for k in range(len(rest) - 1):
                add = d[rest[k]][b] + d[b][rest[k + 1]] - d[rest[k]][rest[k + 1]]
                if gain - add > best:
                    best, at = gain - add, k + 1
            if at is not None:
                seq = rest[:at] + [b] + rest[at:]
                improved = True
    return seq[1:-1]


# ---------- simulation ----------

def simulate(grid, start, stops, end, order, speed=SPEED, pick_s=PICK_S):
    """Yield one dict per step: t (s), dist (m), x, y, event. Steps are single cell moves or picks."""
    t, dist, cur = 0.0, 0, start
    yield {"t": 0.0, "dist": 0, "x": grid.xy(cur)[0], "y": grid.xy(cur)[1], "event": "start"}
    targets = [(stops[i][2], f"pick {stops[i][0]} {stops[i][1]}") for i in order] + [(end, "checkout")]
    for cell, label in targets:
        for nxt in grid.path(cur, cell):
            dist += 1
            t += 1 / speed
            cur = nxt
            x, y = grid.xy(cur)
            yield {"t": t, "dist": dist, "x": x, "y": y, "event": "move"}
        if label != "checkout":
            t += pick_s
        x, y = grid.xy(cur)
        yield {"t": t, "dist": dist, "x": x, "y": y, "event": label}


def run_both(m, items, seconds=10.0, speed=SPEED, pick_s=PICK_S):
    grid = Grid(m)
    stops, end = resolve(m, grid, items)
    start = grid.idx(m["start"])
    d = matrix(grid, start, [s[2] for s in stops], end)
    opt = [i - 1 for i in optimize(d, seconds)]
    lst = list(range(len(stops)))
    res = {}
    for name, order in (("list", lst), ("optimized", opt)):
        steps = list(simulate(grid, start, stops, end, order, speed, pick_s))
        res[name] = steps
    return res


def kpis(steps):
    return steps[-1]["t"], steps[-1]["dist"]


# ---------- store generator (tests and demo) ----------

def generate(layout, seed, w, h, n_items):
    """Return (map dict, list lines). Layouts: aisles, open, maze, perimeter. Always connected enough to pick."""
    rnd = random.Random(seed)
    g = [["."] * w for _ in range(h)]
    if layout == "aisles":
        for x in range(2, w - 2, 3):  # shelf column every 3 cells, 1-wide aisles between
            for y in range(2, h - 2):
                g[y][x] = "#"
    elif layout == "open":
        for _ in range(w * h // 25):
            x, y = rnd.randrange(2, w - 2), rnd.randrange(2, h - 2)
            for dx in range(rnd.randint(1, 3)):
                for dy in range(rnd.randint(1, 3)):
                    if x + dx < w - 1 and y + dy < h - 1:
                        g[y + dy][x + dx] = "#"
    elif layout == "maze":
        for y in range(2, h - 2, 2):
            for x in range(1, w - 1):
                g[y][x] = "#"
            for gap in rnd.sample(range(1, w - 1), max(2, w // 8)):
                g[y][gap] = "."
    elif layout == "perimeter":
        for x in range(2, w - 2):
            g[2][x] = g[h - 3][x] = "#"
        for y in range(2, h - 2):
            g[y][2] = g[y][w - 3] = "#"
        for _ in range(w * h // 40):
            g[rnd.randrange(4, h - 4)][rnd.randrange(4, w - 4)] = "#"
    else:
        raise MapError(f"unknown layout {layout}")
    g[0][0] = "."
    shelf = [(x, y) for y in range(h) for x in range(w) if g[y][x] == "#"]
    floor = [(x, y) for y in range(h) for x in range(w) if g[y][x] == "."]
    spots = shelf if len(shelf) >= n_items * 2 else floor
    chosen = rnd.sample(spots, min(len(spots), n_items * 3))
    prods = [{"id": f"P{i}", "name": f"item{i}", "x": x, "y": y} for i, (x, y) in enumerate(chosen)]
    m = {"grid": ["".join(r) for r in g], "start": [0, 0], "products": prods}
    # keep the shopping list to products reachable from the start
    pm = parse_map(m)
    grid = Grid(pm)
    reach = [p for p in prods if _reachable(pm, grid, p)]
    want = rnd.sample(reach, min(n_items, len(reach)))
    return m, [f"{p['id']}:{p['name']}" for p in want]


def _reachable(pm, grid, p):
    try:
        resolve(pm, grid, [(p["id"], "")])
        return True
    except MapError:
        return False


# ---------- CLI ----------

def show(name, steps, live, every):
    print(f"== {name} route ==")
    for k, s in enumerate(steps):
        if s["event"] != "move" or every and k % every == 0:
            print(f"  t={s['t']:8.1f}s  dist={s['dist']:6d}m  at=({s['x']},{s['y']})  {s['event']}")
        if live:
            time.sleep(min(0.05, 1 / (SPEED * live)))
    t, dist = kpis(steps)
    print(f"  time-to-prepare-basket={t:.1f}s  distance-covered={dist}m")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="optimize and simulate; compare with list order")
    r.add_argument("map")
    r.add_argument("list")
    r.add_argument("--every", type=int, default=0, help="also print every Nth move step")
    r.add_argument("--live", type=float, default=0, help="sleep between steps (speed-up factor)")
    r.add_argument("--trace", help="write every step of both routes to this CSV file")
    r.add_argument("--seconds", type=float, default=10.0, help="optimizer time limit")
    r.add_argument("--speed", type=float, default=SPEED)
    r.add_argument("--pick-s", type=float, default=PICK_S)
    g = sub.add_parser("gen", help="write a demo store")
    g.add_argument("layout")
    g.add_argument("outdir")
    g.add_argument("--seed", type=int, default=1)
    g.add_argument("--w", type=int, default=60)
    g.add_argument("--h", type=int, default=40)
    g.add_argument("--items", type=int, default=20)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "gen":
            import os
            m, lines = generate(a.layout, a.seed, a.w, a.h, a.items)
            os.makedirs(a.outdir, exist_ok=True)
            with open(os.path.join(a.outdir, "store.json"), "w") as f:
                json.dump(m, f)
            with open(os.path.join(a.outdir, "list.txt"), "w") as f:
                f.write("\n".join(lines) + "\n")
            print(f"wrote {a.outdir}/store.json and list.txt ({len(lines)} items)")
            return 0
        if a.speed <= 0 or a.pick_s < 0 or a.seconds <= 0:
            raise MapError("--speed and --seconds must be positive, --pick-s not negative")
        m = load_map(a.map)
        items = load_list(a.list)
        res = run_both(m, items, a.seconds, a.speed, a.pick_s)
    except (MapError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    for w in m["warnings"]:
        print(f"warning: {w}", file=sys.stderr)
    for name in ("list", "optimized"):
        show(name, res[name], a.live, a.every)
    (tl, dl), (to, do) = kpis(res["list"]), kpis(res["optimized"])
    print(f"time saved: {100 * (tl - to) / tl:.1f}%  distance saved: {100 * (dl - do) / dl:.1f}%"
          if tl else "time saved: n/a")
    if a.trace:
        try:
            with open(a.trace, "w") as f:
                f.write("route,step,t,dist,x,y,event\n")
                for name in ("list", "optimized"):
                    for k, s in enumerate(res[name]):
                        f.write(f"{name},{k},{s['t']:.4f},{s['dist']},{s['x']},{s['y']},{s['event']}\n")
        except OSError as e:
            print(f"error: cannot write trace {a.trace}: {e.strerror}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
