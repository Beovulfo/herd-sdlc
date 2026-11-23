#!/usr/bin/env python3
"""Supermarket pick-route optimizer + step-by-step simulator. Stdlib only.

  python3 route.py demo  --width 120 --height 60 --items 25 --out demo   # make demo/store.json + demo/list.txt
  python3 route.py run   demo/store.json demo/list.txt [--steps] [--live 0.02]

Map (JSON): {"grid": ["#####", "S...E", ...], "products": [{"id": "P1", "name": "milk", "x": 3, "y": 0}]}
  '#' blocked (walls, shelves), anything else walkable; 'S' = start, 'E' = checkout/end (default: first/last free cell).
  A product sits on a cell (x=column, y=row); it is picked from that cell if walkable, else from any walkable
  neighbour (so both sides of a shelf are usable). One cell = 1 metre.
List (text): one "id:short name" per line, in the customer's order. That order is the baseline route.
"""
import argparse, json, random, sys, time
from collections import deque

WALK = 1.2   # m/s  ponytail: calibration knobs, tune per store
PICK = 5.0   # s per item
NB = ((1, 0), (-1, 0), (0, 1), (0, -1))


class Store:
    def __init__(self, data):
        self.rows = data["grid"]
        self.h, self.w = len(self.rows), max(map(len, self.rows))
        self.free = {(x, y) for y, r in enumerate(self.rows) for x, c in enumerate(r) if c != "#"}
        cells = sorted(self.free, key=lambda c: (c[1], c[0]))
        mark = lambda ch: next(((x, y) for y, r in enumerate(self.rows) for x, c in enumerate(r) if c == ch), None)
        self.start = mark("S") or cells[0]
        self.end = mark("E") or cells[-1]
        self.products = {p["id"]: p for p in data["products"]}

    def access(self, pid):
        p = self.products[pid]
        c = (p["x"], p["y"])
        cs = [c] if c in self.free else [(c[0] + dx, c[1] + dy) for dx, dy in NB if (c[0] + dx, c[1] + dy) in self.free]
        if not cs:
            raise ValueError(f"product {pid} is unreachable (no walkable cell next to it)")
        return cs

    def bfs(self, src, targets=None):
        """Distances from src; stops early once all targets are reached. Returns (dist, parent)."""
        dist, par, left = {src: 0}, {src: None}, set(targets or ()) - {src}
        q = deque([src])
        while q and (targets is None or left):
            c = q.popleft()
            for dx, dy in NB:
                n = (c[0] + dx, c[1] + dy)
                if n in self.free and n not in dist:
                    dist[n], par[n] = dist[c] + 1, c
                    left.discard(n)
                    q.append(n)
        return dist, par

    def path(self, a, b):
        _, par = self.bfs(a, [b])
        if b not in par:
            raise ValueError(f"no walkable path {a} -> {b}")
        out = []
        while b is not None:
            out.append(b)
            b = par[b]
        return out[::-1]


def parse_list(text, store):
    ids = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pid = line.split(":", 1)[0].strip()
        if pid not in store.products:
            raise ValueError(f"product {pid!r} is not on the map")
        if pid not in ids:
            ids.append(pid)
    return ids


class Planner:
    """Nodes: 0 = start, 1..k = items, k+1 = end. Each node has candidate access cells."""

    def __init__(self, store, ids):
        self.s = store
        self.cells = [[store.start]] + [store.access(i) for i in ids] + [[store.end]]
        allc = {c for cs in self.cells for c in cs}
        self.dd = {}
        for cs in self.cells:
            for c in cs:
                if c not in self.dd:
                    d, _ = store.bfs(c, allc)
                    missing = allc - d.keys()
                    if missing:
                        raise ValueError(f"unreachable from {c}: {sorted(missing)[:3]}")
                    self.dd[c] = d
        n = len(self.cells)
        self.D = [[min(self.dd[a][b] for a in self.cells[i] for b in self.cells[j]) for j in range(n)] for i in range(n)]

    def cost(self, seq):
        return sum(self.D[a][b] for a, b in zip(seq, seq[1:]))

    def optimize(self, restarts=12, seed=1):
        n = len(self.cells)
        k, D = n - 2, self.D
        if k <= 1:
            return list(range(n))
        rnd = random.Random(seed)
        best = None
        for r in range(restarts):
            if r == 0:  # nearest neighbour
                left, cur, mid = set(range(1, k + 1)), 0, []
                while left:
                    cur = min(left, key=lambda j: D[cur][j])
                    left.remove(cur)
                    mid.append(cur)
            else:
                mid = list(range(1, k + 1))
                rnd.shuffle(mid)
            seq = self._local([0] + mid + [n - 1])
            if best is None or self.cost(seq) < self.cost(best):
                best = seq
        return best

    def _local(self, seq):
        D, n = self.D, len(seq)
        improved = True
        while improved:
            improved = False
            for i in range(1, n - 1):  # 2-opt (symmetric distances)
                for j in range(i + 1, n - 1):
                    a, b, c, d = seq[i - 1], seq[i], seq[j], seq[j + 1]
                    if D[a][c] + D[b][d] < D[a][b] + D[c][d]:
                        seq[i:j + 1] = seq[i:j + 1][::-1]
                        improved = True
            for L in (1, 2, 3):  # or-opt: move a segment elsewhere, maybe reversed
                i = 1
                while i + L <= n - 1:
                    seg = seq[i:i + L]
                    rest = seq[:i] + seq[i + L:]
                    gain = D[seq[i - 1]][seg[0]] + D[seg[-1]][seq[i + L]] - D[seq[i - 1]][seq[i + L]]
                    move = None
                    for p in range(len(rest) - 1):
                        for s in (seg, seg[::-1]):
                            add = D[rest[p]][s[0]] + D[s[-1]][rest[p + 1]] - D[rest[p]][rest[p + 1]]
                            if add < gain and (move is None or add < move[0]):
                                move = (add, p, s)
                    if move:
                        _, p, s = move
                        seq[:] = rest[:p + 1] + s + rest[p + 1:]
                        improved = True
                    i += 1
        return seq

    def cells_for(self, order):
        """DP over each node's access cells: pick the cheapest real walking route for a fixed order."""
        prev = {c: (0, None) for c in self.cells[order[0]]}
        layers = [prev]
        for node in order[1:]:
            cur = {}
            for c in self.cells[node]:
                cur[c] = min(((pc + self.dd[p][c], p) for p, (pc, _) in prev.items()))
            layers.append(cur)
            prev = cur
        c = min(prev, key=lambda x: prev[x][0])
        out = []
        for layer in reversed(layers):
            out.append(c)
            c = layer[c][1]
        return out[::-1]


def build_route(store, ids, order, planner):
    """Return step list [(cell, picked_id|None)] for the given node order."""
    cells = planner.cells_for(order)
    steps = [(cells[0], None)]
    for node, a, b in zip(order[1:], cells, cells[1:]):
        for c in store.path(a, b)[1:]:
            steps.append((c, None))
        if 1 <= node <= len(ids):
            steps[-1] = (b, ids[node - 1])
    return steps


def simulate(steps, store, label, emit=None, every_step=False, delay=0.0):
    """Walk the route one step at a time, updating KPIs live. Returns (distance_m, time_s)."""
    dist, t, picked = 0, 0.0, 0
    prev = None
    for cell, pid in steps:
        if prev is not None:
            dist += 1
            t += 1 / WALK
        prev = cell
        ev = None
        if pid:
            t += PICK
            picked += 1
            ev = f"PICK {pid} {store.products[pid]['name']}"
        if emit and (every_step or ev):
            emit(f"[{label}] t={t:7.1f}s dist={dist:5d}m at={cell} items={picked} {ev or ''}".rstrip())
            if delay:
                time.sleep(delay)
    return dist, t


def mmss(s):
    return f"{int(s // 60)}m{int(s % 60):02d}s"


def compare(store, ids, emit=print, every_step=False, delay=0.0):
    pl = Planner(store, ids)
    k = len(ids)
    naive = build_route(store, ids, list(range(k + 2)), pl)
    opt = build_route(store, ids, pl.optimize(), pl)
    emit("== list-order route (baseline) ==")
    dn, tn = simulate(naive, store, "list", emit, every_step, delay)
    emit("== optimized route ==")
    do, to = simulate(opt, store, "opt ", emit, every_step, delay)
    res = dict(items=k, dist_list=dn, dist_opt=do, time_list=tn, time_opt=to,
               dist_saved=1 - do / dn if dn else 0, time_saved=1 - to / tn if tn else 0)
    emit("\n== KPIs ==")
    emit(f"items: {k}")
    emit(f"distance-covered      list: {dn:6d} m   optimized: {do:6d} m   saved: {res['dist_saved']:.1%}")
    emit(f"time-to-prepare-basket list: {mmss(tn)}   optimized: {mmss(to)}   saved: {res['time_saved']:.1%}")
    emit(f"target >30% time saved: {'PASS' if res['time_saved'] > 0.30 else 'FAIL'}")
    return res


def make_demo(width, height, n_items, seed=7, obstacles=0.0):
    """Aisle layout: double shelf rows, gaps for cross-aisles, free perimeter. Optional random blocked cells."""
    rnd = random.Random(seed)
    g = [["."] * width for _ in range(height)]
    for y in range(2, height - 3):
        if y % 4 in (2, 3):
            for x in range(2, width - 2):
                if x % 17 != 0:
                    g[y][x] = "#"
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            if g[y][x] == "." and rnd.random() < obstacles and 2 <= y < height - 3:
                g[y][x] = "#"
    for x in range(width):
        g[0][x] = g[height - 1][x] = "#"
    for y in range(height):
        g[y][0] = g[y][width - 1] = "#"
    g[height - 2][1], g[height - 2][width - 2] = "S", "E"
    words = "milk bread eggs rice pasta apple tea coffee soap salt sugar flour jam oil beans corn fish tuna soda juice".split()
    shelf = [(x, y) for y in range(height) for x in range(width) if g[y][x] == "#" and 2 <= y < height - 3 and 2 <= x < width - 2]
    rnd.shuffle(shelf)
    prods = [{"id": f"P{i:04d}", "name": f"{words[i % len(words)]}-{i}", "x": x, "y": y} for i, (x, y) in enumerate(shelf)]
    store = {"grid": ["".join(r) for r in g], "products": prods}
    picks = rnd.sample(prods, min(n_items, len(prods)))
    return store, [f"{p['id']}:{p['name']}" for p in picks]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="generate a demo store and shopping list")
    d.add_argument("--width", type=int, default=120)
    d.add_argument("--height", type=int, default=60)
    d.add_argument("--items", type=int, default=25)
    d.add_argument("--seed", type=int, default=7)
    d.add_argument("--obstacles", type=float, default=0.0, help="fraction of random blocked cells in aisles")
    d.add_argument("--out", default="demo")
    r = sub.add_parser("run", help="optimize + simulate + compare")
    r.add_argument("map")
    r.add_argument("list")
    r.add_argument("--steps", action="store_true", help="print every single step (default: one line per pick)")
    r.add_argument("--live", type=float, default=0.0, metavar="SEC", help="sleep SEC between printed lines")
    a = ap.parse_args(argv)
    if a.cmd == "demo":
        import os
        os.makedirs(a.out, exist_ok=True)
        store, lst = make_demo(a.width, a.height, a.items, a.seed, a.obstacles)
        json.dump(store, open(f"{a.out}/store.json", "w"))
        open(f"{a.out}/list.txt", "w").write("\n".join(lst) + "\n")
        print(f"wrote {a.out}/store.json ({len(store['products'])} products) and {a.out}/list.txt ({len(lst)} items)")
        return 0
    store = Store(json.load(open(a.map)))
    ids = parse_list(open(a.list).read(), store)
    res = compare(store, ids, every_step=a.steps, delay=a.live)
    return 0 if res["time_saved"] > 0.30 else 1


if __name__ == "__main__":
    sys.exit(main())
