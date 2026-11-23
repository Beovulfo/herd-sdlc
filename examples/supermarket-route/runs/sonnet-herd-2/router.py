"""Supermarket pick-route optimizer: BFS distances on a grid map + TSP-style ordering."""
import argparse
import itertools
import json
import math
import random
import sys
from collections import deque

SPEED, PICK_S, CELL_M = 1.2, 4.0, 1.0  # defaults, overridable in the map file


class RouteError(Exception):
    """A user-facing input problem: printed as one line, exit code 2."""


class Store:
    def __init__(self, data):
        if not isinstance(data, dict):
            raise RouteError("map: must be a JSON object")
        rows = data.get("rows")
        if not isinstance(rows, list) or not rows or not all(isinstance(r, str) for r in rows):
            raise RouteError("map: 'rows' must be a non-empty list of strings")
        self.h, self.w = len(rows), len(rows[0])
        if any(len(r) != self.w for r in rows) or self.w == 0:
            raise RouteError("map: all rows must have the same non-zero length")
        self.rows = rows
        self.walk = [c != "#" for r in rows for c in r]
        flat = "".join(rows)
        if "S" not in flat:
            raise RouteError("map: no start cell 'S'")
        self.start = flat.index("S")
        self.end = flat.index("C") if "C" in flat else self.start
        for key, default in (("walk_speed_mps", SPEED), ("pick_s", PICK_S), ("cell_m", CELL_M)):
            v = data.get(key, default)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v < 0 or (key != "pick_s" and v == 0):
                raise RouteError(f"map: '{key}' must be a positive number")
            setattr(self, key, float(v))
        prods = data.get("products")
        if not isinstance(prods, list):
            raise RouteError("map: 'products' must be a list")
        d0 = self.bfs(self.start)
        if d0[self.end] < 0:
            raise RouteError("map: checkout 'C' is not reachable from start 'S'")
        self.warnings = []
        self.products, self.bad = {}, {}  # id -> (name, access cell); id -> reason
        for p in prods:
            try:
                pid, x, y = str(p["id"]), p["x"], p["y"]
                name = str(p.get("name", ""))
                if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, int) or not isinstance(y, int):
                    raise TypeError
            except (KeyError, TypeError, AttributeError):
                self.bad[str(p.get("id", "?")) if isinstance(p, dict) else "?"] = "malformed product record"
                continue
            if pid in self.products or pid in self.bad:
                self.warnings.append(f"product '{pid}' listed twice on the map, first entry kept")
                continue  # ponytail: nearest-copy choice if ids must repeat
            if not (0 <= x < self.w and 0 <= y < self.h):
                self.bad[pid] = "outside the map"
                continue
            cands = [y * self.w + x] if self.walk[y * self.w + x] else [
                j for j in self.neighbors(y * self.w + x) if self.walk[j]]
            cands = [c for c in cands if d0[c] >= 0]
            if not cands:
                self.bad[pid] = "unreachable from the start"
                continue
            self.products[pid] = (name, min(cands, key=lambda c: (d0[c], c)))  # ponytail: one access cell per product

    def neighbors(self, i):
        y, x = divmod(i, self.w)
        if x > 0:
            yield i - 1
        if x < self.w - 1:
            yield i + 1
        if y > 0:
            yield i - self.w
        if y < self.h - 1:
            yield i + self.w

    def bfs(self, src):
        dist = [-1] * (self.w * self.h)
        dist[src] = 0
        q = deque([src])
        while q:
            i = q.popleft()
            for j in self.neighbors(i):
                if self.walk[j] and dist[j] < 0:
                    dist[j] = dist[i] + 1
                    q.append(j)
        return dist

    def xy(self, i):
        return i % self.w, i // self.w


def parse_list(text):
    """Lines 'id:short name' or 'id'; blank lines and '#' comments ignored. Duplicates mean quantity."""
    ids = []
    for ln in text.splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            pid = ln.split(":", 1)[0].strip()
            if not pid:
                raise RouteError(f"list: line without a product id: {ln!r}")
            ids.append(pid)
    if not ids:
        raise RouteError("list: no products requested")
    return ids


def _held_karp(D, n):
    """Optimal order of items 1..n between node 0 and node n+1."""
    end = n + 1
    best = {(1 << i, i): (D[0][i + 1], None) for i in range(n)}
    for size in range(2, n + 1):
        for sub in itertools.combinations(range(n), size):
            m = sum(1 << i for i in sub)
            for j in sub:
                pm = m ^ (1 << j)
                best[(m, j)] = min((best[(pm, k)][0] + D[k + 1][j + 1], k) for k in sub if k != j)
    full = (1 << n) - 1
    _, j = min((best[(full, j)][0] + D[j + 1][end], j) for j in range(n)) if n else (0, None)
    order, m = [], full
    while j is not None:
        order.append(j + 1)
        m, j = m ^ (1 << j), best[(m, j)][1]
    return order[::-1]


def _local_search(D, n):
    end = n + 1
    left, tour = set(range(1, n + 1)), [0]
    while left:  # nearest neighbour
        nxt = min(left, key=lambda j: D[tour[-1]][j])
        tour.append(nxt)
        left.discard(nxt)
    tour.append(end)
    improved = True
    while improved:
        improved = False
        for i in range(1, n):  # 2-opt
            for j in range(i + 1, n + 1):
                if D[tour[i - 1]][tour[j]] + D[tour[i]][tour[j + 1]] < D[tour[i - 1]][tour[i]] + D[tour[j]][tour[j + 1]]:
                    tour[i:j + 1] = tour[i:j + 1][::-1]
                    improved = True
        for L in (1, 2, 3):  # or-opt: move a segment elsewhere
            i = 1
            while i + L <= n:
                seg = tour[i:i + L]
                rest = tour[:i] + tour[i + L:]
                cur = D[tour[i - 1]][seg[0]] + D[seg[-1]][tour[i + L]] - D[tour[i - 1]][tour[i + L]]
                for pos in range(1, len(rest)):
                    if pos == i:
                        continue
                    for s in (seg, seg[::-1]):
                        add = D[rest[pos - 1]][s[0]] + D[s[-1]][rest[pos]] - D[rest[pos - 1]][rest[pos]]
                        if add < cur - 1e-9:
                            tour = rest[:pos] + s + rest[pos:]
                            improved = True
                            break
                    else:
                        continue
                    break
                i += 1
    return tour[1:-1]


def plan(store, ids, optimize=True):
    """Return dict: order (product ids in visit order), cells, dist (cells, whole route), exact."""
    for pid in ids:
        if pid in store.products:
            continue
        raise RouteError(f"list: product '{pid}' " + (f"cannot be fetched ({store.bad[pid]})" if pid in store.bad else "is not on the map"))
    cells = [store.start] + [store.products[p][1] for p in ids] + [store.end]
    cache = {}
    for c in set(cells):
        cache[c] = store.bfs(c)
    D = [[cache[a][b] for b in cells] for a in cells]
    n = len(ids)
    exact = n <= 12
    idx = list(range(1, n + 1))
    if optimize and n > 1:
        idx = _held_karp(D, n) if exact else _local_search(D, n)
    seq = [0] + idx + [n + 1]
    dist = sum(D[a][b] for a, b in zip(seq, seq[1:]))
    return {"order": [ids[i - 1] for i in idx], "cells": [cells[i] for i in seq], "dist": dist, "exact": exact}


def simulate(store, ids, optimize=True):
    """Yield one event per step or pick: dict(kind, x, y, steps, distance_m, time_s, item)."""
    p = plan(store, ids, optimize)
    order = ["START"] + p["order"]
    steps = picks = 0
    cur = p["cells"][0]

    def st(k, item=None):
        return {"kind": k, "x": store.xy(cur)[0], "y": store.xy(cur)[1], "steps": steps,
                "distance_m": steps * store.cell_m,
                "time_s": steps * store.cell_m / store.walk_speed_mps + picks * store.pick_s, "item": item}

    yield st("start")
    for k, target in enumerate(p["cells"][1:], 1):
        d = store.bfs(target)
        while cur != target:  # walk down the distance field
            cur = min((j for j in store.neighbors(cur) if store.walk[j] and d[j] >= 0), key=lambda j: d[j])
            steps += 1
            yield st("step")
        if k < len(p["cells"]) - 1:
            picks += 1
            yield st("pick", order[k] if k < len(order) else None)
    yield st("done")


def run(store, ids, optimize, on_event=None):
    last = None
    for ev in simulate(store, ids, optimize):
        if on_event:
            on_event(ev)
        last = ev
    return last


def compare(store, ids, on_event=None):
    base = run(store, ids, False, on_event and (lambda e: on_event("list-order", e)))
    opt = run(store, ids, True, on_event and (lambda e: on_event("optimized", e)))
    return {"list_order": base, "optimized": opt,
            "time_saved_pct": 100 * (1 - opt["time_s"] / base["time_s"]) if base["time_s"] else 0.0,
            "distance_saved_pct": 100 * (1 - opt["steps"] / base["steps"]) if base["steps"] else 0.0}


def gen_map(layout, w, h, n_products, seed=0):
    rnd = random.Random(seed)
    g = [["."] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if layout == "aisles":  # horizontal shelf pairs, cross aisles every 12 columns
                g[y][x] = "#" if y % 4 in (1, 2) and 0 < y < h - 1 and 0 < x < w - 1 and x % 12 != 0 else "."
            elif layout == "islands":  # open hall with random shelf blocks
                g[y][x] = "#" if (x // 4 + y // 3) % 3 == 0 and x % 5 not in (0, 4) and y % 3 == 1 else "."
            elif layout == "random":
                g[y][x] = "#" if rnd.random() < 0.25 else "."
            elif layout != "open":
                raise RouteError(f"gen: unknown layout '{layout}'")
    g[0][0], g[0][w - 1] = "S", "C"
    st = Store({"rows": ["".join(r) for r in g], "products": []})
    d0 = st.bfs(st.start)
    ok = [i for i in range(w * h) if (not st.walk[i] and any(d0[j] >= 0 for j in st.neighbors(i))) or (st.walk[i] and d0[i] > 0 and layout in ("open",))]
    ok = rnd.sample(ok, min(n_products, len(ok)))
    prods = [{"id": f"P{k:04d}", "name": f"item{k}", "x": i % w, "y": i // w} for k, i in enumerate(ok)]
    return {"rows": ["".join(r) for r in g], "products": prods}


def gen_list(data, k, seed=0):
    rnd = random.Random(seed)
    ps = data["products"]
    return [f"{p['id']}:{p['name']}" for p in rnd.sample(ps, min(k, len(ps)))]


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        raise RouteError(f"map: cannot read {path}: {e.strerror}")
    except ValueError as e:
        raise RouteError(f"map: {path} is not valid JSON ({e})")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="router.py", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("simulate", help="walk both routes and print the KPIs")
    s.add_argument("map")
    s.add_argument("list")
    s.add_argument("--trace", action="store_true", help="print every step, not only picks")
    g = sub.add_parser("gen", help="write a demo map and list")
    g.add_argument("layout", choices=["aisles", "islands", "random", "open"])
    g.add_argument("out_prefix")
    g.add_argument("--width", type=int, default=60)
    g.add_argument("--height", type=int, default=40)
    g.add_argument("--products", type=int, default=200)
    g.add_argument("--list-size", type=int, default=20)
    g.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "gen":
            if min(a.width, a.height) < 3:
                raise RouteError("gen: width and height must be at least 3")
            data = gen_map(a.layout, a.width, a.height, a.products, a.seed)
            try:
                with open(a.out_prefix + ".map.json", "w") as f:
                    json.dump(data, f)
                with open(a.out_prefix + ".list.txt", "w") as f:
                    f.write("\n".join(gen_list(data, a.list_size, a.seed)) + "\n")
            except OSError as e:
                raise RouteError(f"gen: cannot write {a.out_prefix}.*: {e.strerror}")
            print(f"wrote {a.out_prefix}.map.json and {a.out_prefix}.list.txt")
            return 0
        store = Store(_load_json(a.map))
        try:
            ids = parse_list(open(a.list, encoding="utf-8").read())
        except (OSError, UnicodeDecodeError) as e:
            raise RouteError(f"list: cannot read {a.list}: {getattr(e, 'strerror', None) or e}")
        for pid, why in store.bad.items():
            print(f"warning: product '{pid}' ignored: {why}", file=sys.stderr)
        for w in store.warnings:
            print(f"warning: {w}", file=sys.stderr)
        names = {k: v[0] for k, v in store.products.items()}

        def show(label, e):
            if e["kind"] == "step" and not a.trace:
                return
            what = {"step": "step", "pick": f"pick {e['item']} {names.get(e['item'], '')}", "start": "start", "done": "checkout"}[e["kind"]]
            print(f"[{label:10}] ({e['x']:>3},{e['y']:>3}) {what:<28} distance-covered={e['distance_m']:.1f}m time-to-prepare-basket={e['time_s']:.1f}s")

        r = compare(store, ids, show)
        for label, k in (("list-order", "list_order"), ("optimized", "optimized")):
            print(f"{label:10}: {r[k]['distance_m']:.1f} m, {r[k]['time_s']:.1f} s")
        print(f"time saved: {r['time_saved_pct']:.1f}%   distance saved: {r['distance_saved_pct']:.1f}%")
        return 0
    except RouteError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
