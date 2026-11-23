#!/usr/bin/env python3
"""Supermarket pick-route optimizer + step-by-step simulator. Stdlib only.

Map JSON: {"grid": ["#####", "S...E", ...],
           "products": [{"id": "P1", "name": "milk", "x": 3, "y": 0}, ...]}
Grid legend: '#' wall/shelf (blocked), '.' walkable, 'S' start, 'E' exit/checkout.
A product sits on a blocked cell (x=column, y=row) and is picked from any
walkable 4-neighbour of that cell.
List file: one "id:short name" per line (only the id is used for lookup).

  python3 route.py demo                      # generate a big store, run, compare
  python3 route.py run map.json list.txt [--live N]
  python3 route.py gen map.json list.txt [--aisles 20 --length 60 --items 40 --seed 1]
"""
import argparse, json, random, sys
from collections import deque

SPEED = 1.2   # cells (metres) per second; calibration knob
PICK = 5.0    # seconds to find and grab one item; calibration knob
INF = 10 ** 9


class Store:
    def __init__(self, data):
        self.rows = data["grid"]
        self.h, self.w = len(self.rows), len(self.rows[0])
        if any(len(r) != self.w for r in self.rows):
            raise ValueError("grid rows must all have the same length")
        self.walk = [c not in "#" for r in self.rows for c in r]
        self.start = self.exit = None
        for y, r in enumerate(self.rows):
            for x, c in enumerate(r):
                if c == "S": self.start = y * self.w + x
                if c == "E": self.exit = y * self.w + x
        if self.start is None:
            raise ValueError("map needs an S cell")
        if self.exit is None:
            self.exit = self.start
        self.products = {}
        for p in data["products"]:
            c = self.neighbours_walkable(p["x"], p["y"])
            if not c:
                raise ValueError(f"product {p['id']} has no walkable neighbour")
            self.products[str(p["id"])] = (p["name"], c)

    def neighbours_walkable(self, x, y):
        return [ny * self.w + nx for nx, ny in ((x+1, y), (x-1, y), (x, y+1), (x, y-1))
                if 0 <= nx < self.w and 0 <= ny < self.h and self.walk[ny * self.w + nx]]

    def bfs(self, src):
        """Return (dist, parent) lists over all cells."""
        d = [INF] * (self.w * self.h); par = [-1] * len(d)
        d[src] = 0; q = deque([src]); w = self.w
        while q:
            u = q.popleft(); x = u % w
            for v in (u + 1 if x + 1 < w else -1, u - 1 if x else -1, u + w, u - w):
                if 0 <= v < len(d) and d[v] == INF and self.walk[v]:
                    d[v] = d[u] + 1; par[v] = u; q.append(v)
        return d, par

    def path(self, a, b, cache):
        d, par = cache(a)
        cells = [b]
        while cells[-1] != a:
            cells.append(par[cells[-1]])
        return cells[::-1]


def parse_list(text):
    ids = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            ids.append(line.split(":", 1)[0].strip())
    return ids


def solve(store, ids):
    """Return (optimized_order, list_order, cells_for_order(order))."""
    cache = {}
    def bfs(c):
        if c not in cache: cache[c] = store.bfs(c)
        return cache[c]
    cands = [store.products[i][1] for i in ids]
    for i, c in zip(ids, cands):
        if all(bfs(store.start)[0][x] == INF for x in c):
            raise ValueError(f"product {i} unreachable from start")
    n = len(ids)
    # node distance = best over pickup cells (approx; exact cells chosen later by DP)
    def nd(a, b): return min(bfs(x)[0][y] for x in cands[a] for y in cands[b])
    D = [[0 if a == b else nd(a, b) for b in range(n)] for a in range(n)]
    ds = [min(bfs(store.start)[0][c] for c in cs) for cs in cands]
    de = [min(bfs(store.exit)[0][c] for c in cs) for cs in cands]

    def cost(o):
        if not o: return 0
        return ds[o[0]] + sum(D[o[i]][o[i+1]] for i in range(len(o)-1)) + de[o[-1]]

    # nearest neighbour seed
    left, cur, order = set(range(n)), None, []
    while left:
        nxt = min(left, key=lambda j: (ds[j] if cur is None else D[cur][j]))
        order.append(nxt); left.remove(nxt); cur = nxt
    # 2-opt + or-opt until no improvement (ponytail: O(n^2) passes, fine to ~500 items)
    best, improved = cost(order), True
    while improved:
        improved = False
        for i in range(n):
            for j in range(i + 1, n):
                t = order[:i] + order[i:j+1][::-1] + order[j+1:]
                c = cost(t)
                if c < best: order, best, improved = t, c, True
        for i in range(n):
            for k in (1, 2, 3):
                seg = order[i:i+k]; rest = order[:i] + order[i+k:]
                for j in range(len(rest) + 1):
                    t = rest[:j] + seg + rest[j:]
                    c = cost(t)
                    if c < best: order, best, improved = t, c, True; break
                if improved: break
            if improved: break

    def route(o):
        """Exact shortest cell route visiting o in order, picking pickup cells by DP."""
        layers = [[store.start]] + [cands[i] for i in o] + [[store.exit]]
        best_cost = {store.start: 0}; back = []
        for L in layers[1:]:
            nxt, bk = {}, {}
            for c in L:
                v, p = min((pc + bfs(p)[0][c], p) for p, pc in best_cost.items())
                nxt[c], bk[c] = v, p
            best_cost = nxt; back.append(bk)
        c = store.exit; stops = [c]
        for bk in reversed(back):
            c = bk[c]; stops.append(c)
        stops.reverse()          # start, pickup cells..., exit
        cells = [stops[0]]
        for a, b in zip(stops, stops[1:]):
            cells += store.path(a, b, bfs)[1:]
        return stops, cells

    return order, list(range(n)), route


def simulate(store, ids, order, route, label, live=0, out=print):
    """Walk the route one step at a time; return (time_s, distance, trace)."""
    stops, cells = route(order)
    pickup_at = {}  # index in cells -> product index (first time we reach each stop)
    pos = 0
    for k, s in enumerate(stops[1:-1]):
        while cells[pos] != s: pos += 1
        pickup_at[pos] = order[k]
    dist, t, steps = 0, 0.0, 0
    for i, c in enumerate(cells):
        if i:
            dist += 1; t += 1 / SPEED; steps += 1
        if i in pickup_at:
            t += PICK
            if live:
                nm = store.products[ids[pickup_at[i]]][0]
                out(f"  [{label}] t={t:7.1f}s dist={dist:5d}m  picked {ids[pickup_at[i]]}:{nm}")
        elif live and i and i % live == 0:
            out(f"  [{label}] t={t:7.1f}s dist={dist:5d}m  step {i}/{len(cells)-1}")
    return t, dist


def compare(store, ids, live=0, out=print):
    order, naive, route = solve(store, ids)
    tn, dn = simulate(store, ids, naive, route, "list-order", live, out)
    to, do = simulate(store, ids, order, route, "optimized ", live, out)
    sv_t, sv_d = 100 * (tn - to) / tn, 100 * (dn - do) / dn
    out(f"\nItems: {len(ids)}   Store: {store.w}x{store.h}")
    out(f"{'route':<12}{'time-to-prepare-basket':>26}{'distance-covered':>20}")
    out(f"{'list-order':<12}{tn:>24.1f} s{dn:>18d} m")
    out(f"{'optimized':<12}{to:>24.1f} s{do:>18d} m")
    out(f"Saved: {sv_t:.1f}% time, {sv_d:.1f}% distance  ->  "
        f"{'PASS' if sv_t > 30 else 'FAIL'} (target > 30% time)")
    return sv_t, sv_d


def gen(aisles=20, length=60, items=40, seed=1, catalog=None):
    """Aisles of shelves (2-wide shelf blocks, walkable lanes between), cross aisles top/bottom."""
    rnd = random.Random(seed)
    W = aisles * 3 + 1; H = length + 4
    g = [["."] * W for _ in range(H)]
    shelf = []
    for a in range(aisles):
        x = 1 + a * 3
        for y in range(2, H - 2):
            g[y][x] = g[y][x + 1] = "#"
            shelf += [(x, y), (x + 1, y)]
    g[H - 1][0] = "S"; g[H - 1][W - 1] = "E"
    cells = rnd.sample(shelf, min(len(shelf), max(items * 4, 200)))
    prods = [{"id": f"P{i:05d}", "name": f"item{i}", "x": x, "y": y}
             for i, (x, y) in enumerate(cells)]
    ids = [p["id"] for p in rnd.sample(prods, items)]
    return {"grid": ["".join(r) for r in g], "products": prods}, ids


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["demo", "run", "gen"])
    ap.add_argument("files", nargs="*")
    ap.add_argument("--live", type=int, default=0, help="print KPIs every N steps (and every pick)")
    ap.add_argument("--aisles", type=int, default=20)
    ap.add_argument("--length", type=int, default=60)
    ap.add_argument("--items", type=int, default=40)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    if a.cmd == "gen":
        data, ids = gen(a.aisles, a.length, a.items, a.seed)
        json.dump(data, open(a.files[0], "w"))
        open(a.files[1], "w").write("\n".join(f"{i}:{data['products'][int(i[1:])]['name']}" for i in ids) + "\n")
        print(f"wrote {a.files[0]} and {a.files[1]}")
    elif a.cmd == "demo":
        data, ids = gen(a.aisles, a.length, a.items, a.seed)
        compare(Store(data), ids, a.live)
    else:
        store = Store(json.load(open(a.files[0])))
        ids = parse_list(open(a.files[1]).read())
        missing = [i for i in ids if i not in store.products]
        if missing: sys.exit(f"unknown product ids: {missing}")
        compare(store, ids, a.live)


if __name__ == "__main__":
    main()
