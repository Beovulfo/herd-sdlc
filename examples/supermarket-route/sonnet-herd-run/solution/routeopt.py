"""Supermarket pick-route optimizer: stdlib only.

Map (JSON): {"grid": ["#...", ...], "start": [x, y], "end": [x, y] (optional),
             "products": [{"id": "P1", "name": "milk", "x": 3, "y": 0}, ...],
             "cell_m": 1.0, "speed_mps": 1.2, "pick_s": 5.0 (all optional)}
'#' is blocked (wall or shelf), '.' is walkable. A product may sit on a shelf
cell or a walkable cell; it is picked from a walkable cell next to it.
List (text): one "id:short name" per line, '#' comments allowed.

    python3 routeopt.py run map.json list.txt [--live] [--every N]
"""
import argparse
import json
import math
import sys
import time
from collections import namedtuple
from dataclasses import dataclass

Event = namedtuple("Event", "kind t dist_m pos item picked total")


class StoreMap:
    def __init__(self, raw):
        grid = raw.get("grid")
        if not grid or not all(isinstance(r, str) for r in grid):
            raise ValueError("map: 'grid' must be a non-empty list of strings")
        bad = {c for r in grid for c in r} - set("#.")
        if bad:
            raise ValueError(f"map: grid may only contain '#' (blocked) and '.' (walkable), found {sorted(bad)}")
        self.h, self.w = len(grid), len(grid[0])
        if self.w == 0 or any(len(r) != self.w for r in grid):
            raise ValueError("map: grid rows must all have the same non-zero length")
        # padded with a blocked border so BFS needs no bounds checks
        self.W = self.w + 2
        self.opn = bytearray(self.W * (self.h + 2))
        for y, row in enumerate(grid):
            for x, c in enumerate(row):
                if c == ".":
                    self.opn[(y + 1) * self.W + x + 1] = 1
        self.start = self._cell(raw.get("start"), "start")
        self.end = self._cell(raw.get("end", raw.get("start")), "end")
        for name, c in (("start", self.start), ("end", self.end)):
            if not self.walkable(*c):
                raise ValueError(f"map: {name} {list(c)} is not on a walkable cell")
        self.cell_m = self._pos(raw, "cell_m", 1.0)
        self.speed_mps = self._pos(raw, "speed_mps", 1.2)
        self.pick_s = self._pos(raw, "pick_s", 5.0)
        self.products = {}
        for p in raw.get("products", []):
            pid = str(p.get("id", "")).strip()
            if not pid:
                raise ValueError("map: product without an id")
            if pid in self.products:
                raise ValueError(f"map: duplicate product id {pid!r}")
            x, y = self._cell([p.get("x"), p.get("y")], f"product {pid}")
            self.products[pid] = (str(p.get("name", "")), x, y)
        self._access = {}
        self._dstart = None

    def _cell(self, c, what):
        try:
            x, y = c[0], c[1]
        except (TypeError, IndexError, KeyError):
            raise ValueError(f"map: {what} needs integer x,y") from None
        if type(x) is not int or type(y) is not int:
            raise ValueError(f"map: {what} needs integer x,y")
        if not (0 <= x < self.w and 0 <= y < self.h):
            raise ValueError(f"map: {what} {[x, y]} is outside the {self.w}x{self.h} grid")
        return (x, y)

    @staticmethod
    def _pos(raw, key, default):
        v = raw.get(key, default)
        if type(v) not in (int, float) or not math.isfinite(v) or v <= 0:
            raise ValueError(f"map: {key} must be a positive finite number")
        return v

    def walkable(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h and bool(self.opn[self.flat((x, y))])

    def flat(self, c):
        return (c[1] + 1) * self.W + c[0] + 1

    def unflat(self, i):
        return (i % self.W - 1, i // self.W - 1)

    def bfs(self, src, targets=None):
        """Step distances from cell src (-1 = unreachable). Stops early once every target cell is found."""
        opn, W = self.opn, self.W
        s = self.flat(src)
        dist = [-1] * len(opn)
        dist[s] = 0
        left = {self.flat(t) for t in targets} - {s} if targets else None
        if left is not None and not left:
            return dist
        q = [s]
        for u in q:  # q grows while iterating: this is the BFS queue
            d = dist[u] + 1
            for v in (u - 1, u + 1, u - W, u + W):
                if opn[v] and dist[v] < 0:
                    dist[v] = d
                    q.append(v)
                    if left is not None and v in left:
                        left.discard(v)
                        if not left:
                            return dist
        return dist

    def access(self, pid):
        """Walkable cell the product is picked from: the reachable neighbour nearest to the start."""
        if pid not in self._access:
            if self._dstart is None:
                self._dstart = self.bfs(self.start)
            _, x, y = self.products[pid]
            near = [(x, y)] if self.walkable(x, y) else [
                c for c in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)) if self.walkable(*c)]
            reach = [(self._dstart[self.flat(c)], c[1], c[0]) for c in near if self._dstart[self.flat(c)] >= 0]
            if not reach:
                raise ValueError(f"unreachable: product {pid!r} cannot be reached from the start")
            _, cy, cx = min(reach)  # ponytail: one fixed pick cell per product; choose per route if shelves matter
            self._access[pid] = (cx, cy)
        return self._access[pid]

    def path(self, a, b):
        """Shortest cell path a..b inclusive."""
        dist = self.bfs(b, [a])
        u = self.flat(a)
        if dist[u] < 0:
            raise ValueError(f"unreachable: no path between {list(a)} and {list(b)}")
        cells = [a]
        while dist[u] > 0:
            for v in (u - 1, u + 1, u - self.W, u + self.W):
                if dist[v] == dist[u] - 1:
                    u = v
                    break
            cells.append(self.unflat(u))
        return cells


@dataclass
class Route:
    stops: list    # product ids in visiting order
    cells: list    # every (x, y) cell walked, start to end
    pick_at: list  # index into cells where each stop is picked

    @property
    def distance(self):
        return len(self.cells) - 1


def load_map(src):
    if isinstance(src, StoreMap):
        return src
    if isinstance(src, dict):
        return StoreMap(src)
    with open(src) as f:
        return StoreMap(json.load(f))


def parse_list(text):
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pid, _, name = line.partition(":")
        pid = pid.strip()
        if not pid:
            raise ValueError(f"list: line without a product id: {line!r}")
        items.append((pid, name.strip()))
    return items


def distance_matrix(store, cells):
    n = len(cells)
    dm = [[0] * n for _ in range(n)]
    for i in range(n - 1):
        dist = store.bfs(cells[i], cells[i + 1:])
        for j in range(i + 1, n):
            d = dist[store.flat(cells[j])]
            if d < 0:
                raise ValueError(f"unreachable: no path between {list(cells[i])} and {list(cells[j])}")
            dm[i][j] = dm[j][i] = d
    return dm


def _optimize(dm, k):
    """Visiting order of stops 1..k between fixed start 0 and end k+1.
    Local search (2-opt + or-opt) from a nearest-neighbour tour and from list order; the shorter wins,
    so the result is never longer than list order."""
    # ponytail: heuristic, not exact; local search is O(k^2) per pass, 500 stops on a 250x250 store plan in ~10 s
    p, todo = [0], set(range(1, k + 1))
    while todo:
        nxt = min(todo, key=lambda j: dm[p[-1]][j])
        p.append(nxt)
        todo.discard(nxt)
    p.append(k + 1)
    cands = [_local_search(dm, p), _local_search(dm, list(range(k + 2)))]
    return min(cands, key=lambda q: sum(dm[a][b] for a, b in zip(q, q[1:])))[1:-1]


def _local_search(dm, p):
    improved = True
    while improved:
        improved = False
        for i in range(1, len(p) - 1):  # 2-opt: reverse p[i..j]
            for j in range(i + 1, len(p) - 1):
                if dm[p[i - 1]][p[j]] + dm[p[i]][p[j + 1]] < dm[p[i - 1]][p[i]] + dm[p[j]][p[j + 1]]:
                    p[i:j + 1] = p[i:j + 1][::-1]
                    improved = True
        for n in (1, 2, 3):  # or-opt: move a run of n stops elsewhere, either way round
            i = 1
            while i + n < len(p):
                seg, rest = p[i:i + n], p[:i] + p[i + n:]
                gain = dm[p[i - 1]][seg[0]] + dm[seg[-1]][p[i + n]] - dm[p[i - 1]][p[i + n]]
                best = (0, None)
                for j in range(len(rest) - 1):
                    a, b = rest[j], rest[j + 1]
                    for s in (seg, seg[::-1]):
                        delta = dm[a][s[0]] + dm[s[-1]][b] - dm[a][b] - gain
                        if delta < best[0]:
                            best = (delta, (j, s))
                if best[1]:
                    j, s = best[1]
                    p = rest[:j + 1] + s + rest[j + 1:]
                    improved = True
                i += 1
    return p


def plan(store, items, optimize=True):
    """Route from start through every requested product to end. optimize=False keeps list order."""
    ids = list(dict.fromkeys(i for i, _ in items))  # ponytail: quantity is not modelled, a repeated id is one stop
    if not ids:
        raise ValueError("shopping list is empty")
    for i in ids:
        if i not in store.products:
            raise ValueError(f"unknown product {i!r}: not on the map")
    cells = [store.start] + [store.access(i) for i in ids] + [store.end]
    k = len(ids)
    order = _optimize(distance_matrix(store, cells), k) if optimize else list(range(1, k + 1))
    walk, stops, pick_at = [store.start], [], []
    seq = [0] + order + [k + 1]
    for a, b in zip(seq, seq[1:]):
        walk.extend(store.path(cells[a], cells[b])[1:])
        if b <= k:
            stops.append(ids[b - 1])
            pick_at.append(len(walk) - 1)
    return Route(stops, walk, pick_at)


def simulate(store, route):
    """Yield one Event per step and per pick, with running distance-covered and elapsed time."""
    step_s = store.cell_m / store.speed_mps
    at = {}
    for pid, idx in zip(route.stops, route.pick_at):
        at.setdefault(idx, []).append(pid)
    total, picked = len(route.stops), 0
    yield Event("start", 0.0, 0.0, route.cells[0], None, 0, total)
    for idx, cell in enumerate(route.cells):
        if idx:
            yield Event("move", idx * step_s + picked * store.pick_s, idx * store.cell_m, cell, None, picked, total)
        for pid in at.get(idx, []):
            picked += 1
            yield Event("pick", idx * step_s + picked * store.pick_s, idx * store.cell_m, cell, pid, picked, total)
    n = route.distance
    yield Event("done", n * step_s + picked * store.pick_s, n * store.cell_m, route.cells[-1], None, picked, total)


def kpis(store, route):
    dist = route.distance * store.cell_m
    return {"distance_m": dist, "time_s": dist / store.speed_mps + len(route.stops) * store.pick_s,
            "stops": list(route.stops)}


def _saving(base, opt):
    return 100.0 * (1 - opt / base) if base else 0.0


def compare(store, items):
    """KPIs of the optimized route against list order. Basket is ready on arrival at the end cell."""
    opt, base = kpis(store, plan(store, items)), kpis(store, plan(store, items, optimize=False))
    return {"items": len(opt["stops"]), "optimized": opt, "list_order": base,
            "time_saving_pct": _saving(base["time_s"], opt["time_s"]),
            "distance_saving_pct": _saving(base["distance_m"], opt["distance_m"])}


def _live(store, route, label, every, speedup):
    print(f"-- {label}")
    prev = 0.0
    for e in simulate(store, route):
        if speedup:
            time.sleep((e.t - prev) / speedup)
        prev = e.t
        if e.kind == "pick":
            print(f"[{label}] t={e.t:8.1f}s distance-covered={e.dist_m:8.1f}m picked {e.picked}/{e.total} "
                  f"{e.item} {store.products[e.item][0]}", flush=True)
        elif e.kind == "move" and (every and int(round(e.dist_m / store.cell_m)) % every == 0):
            print(f"[{label}] t={e.t:8.1f}s distance-covered={e.dist_m:8.1f}m at {e.pos[0]},{e.pos[1]}", flush=True)
        elif e.kind == "done":
            print(f"[{label}] basket ready: time-to-prepare-basket={e.t:.1f}s distance-covered={e.dist_m:.1f}m", flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="routeopt", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="plan, simulate and compare against list order")
    run.add_argument("map")
    run.add_argument("list")
    run.add_argument("--live", action="store_true", help="stream the step-by-step simulation with running KPIs")
    run.add_argument("--every", type=int, default=25, help="with --live, print a position line every N steps (0 = picks only)")
    run.add_argument("--speedup", type=float, default=0, help="with --live, pace events at N x real time (0 = no waiting)")
    run.add_argument("--json", action="store_true", help="print the comparison as JSON")
    a = ap.parse_args(argv)
    if a.json and a.live:
        ap.error("--json and --live cannot be combined")
    try:
        store = load_map(a.map)
        with open(a.list) as f:
            items = parse_list(f.read())
        rep = compare(store, items)
        if a.live:
            _live(store, plan(store, items, optimize=False), "list-order", a.every, a.speedup)
            _live(store, plan(store, items), "optimized", a.every, a.speedup)
    except (ValueError, TypeError, AttributeError, OSError) as e:  # JSONDecodeError is a ValueError
        print(f"error: {e}", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(rep, indent=2))
        return 0
    o, b = rep["optimized"], rep["list_order"]
    print(f"{rep['items']} items")
    print(f"{'':24}{'list-order':>12}{'optimized':>12}{'saving':>9}")
    print(f"{'time-to-prepare-basket':24}{b['time_s']:11.1f}s{o['time_s']:11.1f}s{rep['time_saving_pct']:8.1f}%")
    print(f"{'distance-covered':24}{b['distance_m']:11.1f}m{o['distance_m']:11.1f}m{rep['distance_saving_pct']:8.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
