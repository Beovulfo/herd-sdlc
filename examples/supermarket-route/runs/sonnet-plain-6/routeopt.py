#!/usr/bin/env python3
"""Supermarket pick-route optimizer + step-by-step simulator. Stdlib only.

Map JSON: {"grid": ["#..#", ...], "start": [x, y], "end": [x, y] (optional),
           "products": [{"id": "P1", "name": "milk", "x": 3, "y": 2}, ...]}
'#' = blocked (shelf/wall), any other char = walkable. Products sit on shelf
cells; they are picked from an adjacent walkable cell (or their own cell if walkable).
List file: one "id:short name" per line (the name is informational).
"""
import argparse, json, random, sys
from collections import deque

WALK_SPEED = 1.2   # cells (metres) per second
PICK_TIME = 8.0    # seconds to find/grab/place one item


class Store:
    def __init__(self, d):
        self.g = d["grid"]
        self.h, self.w = len(self.g), len(self.g[0])
        self.start = tuple(d["start"])
        self.end = tuple(d.get("end", d["start"]))
        self.products = {p["id"]: p for p in d["products"]}

    def ok(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h and self.g[y][x] != "#"

    def nbrs(self, x, y):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if self.ok(x + dx, y + dy):
                yield x + dx, y + dy

    def bfs(self, src):
        par = {src: None}
        q = deque([src])
        while q:
            c = q.popleft()
            for n in self.nbrs(*c):
                if n not in par:
                    par[n] = c
                    q.append(n)
        return par  # also doubles as reachability

    def access(self, pid, par0):
        """Pick-up cell: reachable walkable cell at/next to the product, nearest to start by BFS order."""
        p = self.products[pid]
        cells = [(p["x"], p["y"])] if self.ok(p["x"], p["y"]) else []
        cells += list(self.nbrs(p["x"], p["y"])) if not cells else []
        cells = [c for c in cells if c in par0]
        if not cells:
            raise ValueError(f"product {pid} unreachable from start")
        return cells[0]


def path(store, a, b):
    par, c, out = store.bfs(b), a, [a]   # walk a -> b following parents toward b
    while c != b:
        c = par[c]
        out.append(c)
    return out


def dist_matrix(store, nodes):
    m = []
    for a in nodes:
        par = store.bfs(a)
        # BFS depth: recompute via chain length is O(L); use a distance BFS instead
        d = {a: 0}
        q = deque([a])
        while q:
            c = q.popleft()
            for n in store.nbrs(*c):
                if n not in d:
                    d[n] = d[c] + 1
                    q.append(n)
        m.append([d.get(b, float("inf")) for b in nodes])
    return m


def optimize(m):
    """Open tour 0 -> ... -> last (fixed ends). Nearest neighbour, then 2-opt + or-opt until stable.
    ponytail: heuristic, not exact; fine to ~hundreds of items. Upgrade path: OR-tools / Lin-Kernighan."""
    n = len(m)
    mid = list(range(1, n - 1))
    tour, cur = [0], 0
    while mid:
        nxt = min(mid, key=lambda j: m[cur][j])
        mid.remove(nxt); tour.append(nxt); cur = nxt
    tour.append(n - 1)
    cost = lambda t: sum(m[t[i]][t[i + 1]] for i in range(len(t) - 1))
    best, improved = cost(tour), True
    while improved:
        improved = False
        for i in range(1, n - 1):
            for j in range(i + 1, n - 1):  # 2-opt: reverse tour[i..j]
                t = tour[:i] + tour[i:j + 1][::-1] + tour[j + 1:]
                c = cost(t)
                if c < best:
                    tour, best, improved = t, c, True
            for j in range(1, n - 1):      # or-opt: move node i to position j
                if j == i:
                    continue
                t = tour[:]; v = t.pop(i); t.insert(j, v)
                c = cost(t)
                if c < best:
                    tour, best, improved = t, c, True
    return tour


def plan(store, ids):
    par0 = store.bfs(store.start)
    if store.end not in par0:
        raise ValueError("end not reachable from start")
    acc = [store.access(i, par0) for i in ids]
    nodes = [store.start] + acc + [store.end]
    m = dist_matrix(store, nodes)
    listed = list(range(len(nodes)))                 # list-order route
    opt = optimize(m)
    return nodes, m, listed, opt


def simulate(store, nodes, order, ids, verbose=0):
    """Walk cell by cell; yields events and keeps live KPIs. Returns (distance_m, time_s)."""
    dist = t = 0.0
    picked = 0
    for k in range(len(order) - 1):
        a, b = nodes[order[k]], nodes[order[k + 1]]
        for c in path(store, a, b)[1:]:
            dist += 1; t += 1 / WALK_SPEED
            if verbose and int(dist) % verbose == 0:
                print(f"  step {int(dist):5d} at {c}  distance={dist:.0f} m  time={t:.0f} s  picked={picked}")
        if order[k + 1] != len(nodes) - 1:
            pid = ids[order[k + 1] - 1]
            t += PICK_TIME; picked += 1
            if verbose:
                nm = store.products[pid]["name"]
                print(f"PICK {pid} ({nm}) at {b}  distance={dist:.0f} m  time={t:.0f} s  picked={picked}/{len(ids)}")
    return dist, t


def run(store, ids, verbose=0):
    nodes, m, listed, opt = plan(store, ids)
    seq = lambda o: [ids[i - 1] for i in o[1:-1]]
    print("== list-order route =="); d0, t0 = simulate(store, nodes, listed, ids, verbose)
    print("== optimized route =="); d1, t1 = simulate(store, nodes, opt, ids, verbose)
    # time includes constant pick time, so time saving is the conservative KPI
    print(f"\nitems: {len(ids)}   order: {' '.join(seq(opt))}")
    print(f"{'':18}{'distance (m)':>14}{'time-to-prepare (s)':>22}")
    print(f"{'list order':18}{d0:14.0f}{t0:22.0f}")
    print(f"{'optimized':18}{d1:14.0f}{t1:22.0f}")
    ds, ts = 100 * (1 - d1 / d0), 100 * (1 - t1 / t0)
    print(f"{'saving':18}{ds:13.1f}%{ts:21.1f}%")
    print("TARGET >30% time saving:", "PASS" if ts > 30 else "FAIL")
    return ts


def demo_store(aisles=20, length=40, seed=1, items_per_shelf=1):
    """Generated store: `aisles` double-sided shelf rows, cross-aisles at both ends, entrance bottom-left."""
    rnd = random.Random(seed)
    w, h = length + 2, aisles * 3 + 3
    g = [["."] * w for _ in range(h)]
    prods, n = [], 0
    for a in range(aisles):
        y = 2 + a * 3                       # shelf row y, walking row y+1 and y-1 shared
        for x in range(1, w - 1):
            g[y][x] = "#"
            n += 1
            prods.append({"id": f"P{n}", "name": f"item{n}", "x": x, "y": y})
    # shelf rows at y=2,5,8..: walk rows at 1,3,4,6,7,...
    return {"grid": ["".join(r) for r in g], "start": [0, h - 1], "products": prods}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map"); ap.add_argument("--list")
    ap.add_argument("--demo", action="store_true", help="generate a store and a random shopping list")
    ap.add_argument("--aisles", type=int, default=20); ap.add_argument("--length", type=int, default=40)
    ap.add_argument("--items", type=int, default=30); ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--verbose", type=int, default=0, metavar="N", help="print live KPIs every N steps (and every pick)")
    a = ap.parse_args()
    if a.demo:
        d = demo_store(a.aisles, a.length, a.seed)
        ids = random.Random(a.seed).sample([p["id"] for p in d["products"]], a.items)
        if a.map:
            json.dump(d, open(a.map, "w")); print("wrote", a.map)
    elif a.map and a.list:
        d = json.load(open(a.map))
        ids = [l.split(":")[0].strip() for l in open(a.list) if l.strip()]
    else:
        ap.error("use --demo, or --map and --list")
    s = Store(d)
    unknown = [i for i in ids if i not in s.products]
    if unknown:
        sys.exit(f"unknown product ids: {unknown}")
    sys.exit(0 if run(s, ids, a.verbose) > 30 else 1)


if __name__ == "__main__":
    main()
