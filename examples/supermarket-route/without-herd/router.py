#!/usr/bin/env python3
"""Supermarket picking-route optimizer + step-by-step simulator. Stdlib only.

Map JSON: {"grid": ["#####", "S...#", ...],   # '#' blocked/shelf, 'S' packing station, else walkable
           "products": {"P1": {"name": "Milk", "pos": [row, col]}}}
A product's pos may be a shelf cell (picked from any adjacent walkable cell) or a walkable cell.
Shopping list: lines "id:short name" (name optional/ignored for routing).

  python3 router.py gen  --out store.json [--w 120 --h 80 --seed 1]
  python3 router.py run  store.json list.txt [--every 25] [--speed 1.2] [--pick 5]
  python3 router.py demo [--items 25]        # generate store+list, run, assert >30% saving
"""
import argparse, json, random, sys
from collections import deque

DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


class Store:
    def __init__(self, data):
        g = data["grid"]
        self.h, self.w = len(g), len(g[0])
        if any(len(r) != self.w for r in g):
            raise ValueError("grid rows must have equal length")
        self.free = bytearray(self.w * self.h)
        self.station = None
        for r, row in enumerate(g):
            for c, ch in enumerate(row):
                if ch != "#":
                    self.free[r * self.w + c] = 1
                if ch == "S":
                    self.station = r * self.w + c
        if self.station is None:
            raise ValueError("map needs an 'S' station cell")
        self.names, self.access = {}, {}
        for pid, p in data["products"].items():
            r, c = p["pos"]
            cell = r * self.w + c
            cells = [cell] if self.free[cell] else [
                n for n in self.nbrs(cell) if self.free[n]]
            if not cells:
                raise ValueError(f"product {pid} has no reachable neighbour cell")
            self.names[pid], self.access[pid] = p["name"], cells

    def nbrs(self, i):
        r, c = divmod(i, self.w)
        for dr, dc in DIRS:
            rr, cc = r + dr, c + dc
            if 0 <= rr < self.h and 0 <= cc < self.w:
                yield rr * self.w + cc

    def bfs(self, sources):
        """Distance (steps) from nearest source to every walkable cell; -1 unreachable."""
        d = [-1] * (self.w * self.h)
        q = deque(sources)
        for s in sources:
            d[s] = 0
        while q:
            i = q.popleft()
            for n in self.nbrs(i):
                if self.free[n] and d[n] < 0:
                    d[n] = d[i] + 1
                    q.append(n)
        return d

    def path(self, src, targets):
        """Shortest walkable path src -> nearest of targets (list of cells, excl. src)."""
        targets = set(targets)
        if src in targets:
            return []
        par, q = {src: None}, deque([src])
        while q:
            i = q.popleft()
            for n in self.nbrs(i):
                if self.free[n] and n not in par:
                    par[n] = i
                    if n in targets:
                        out = []
                        while n != src:
                            out.append(n)
                            n = par[n]
                        return out[::-1]
                    q.append(n)
        raise ValueError("unreachable")


def optimize(store, ids):
    """Round trip station -> all items -> station. Returns item ids in visit order.
    Nearest neighbour + 2-opt + or-opt on the true-walking-distance matrix."""
    nodes = [[store.station]] + [store.access[i] for i in ids]
    n = len(nodes)
    maps = [store.bfs(c) for c in nodes]
    D = [[0] * n for _ in range(n)]
    for a in range(n):
        for b in range(n):
            if a != b:
                # symmetric: shortest of either direction
                D[a][b] = min(min(maps[b][c] for c in nodes[a]),
                              min(maps[a][c] for c in nodes[b]))
                if D[a][b] < 0:
                    raise ValueError(f"unreachable item: {(['station'] + ids)[a]}/{(['station'] + ids)[b]}")
    best = None
    for start in range(1, n):  # NN from several starts; ponytail: O(n^3), fine to ~200 items
        tour, left = [0, start], set(range(1, n)) - {start}
        while left:
            nxt = min(left, key=lambda j: D[tour[-1]][j])
            tour.append(nxt)
            left.remove(nxt)
        tour = improve(tour, D)
        L = cost(tour, D)
        if best is None or L < best[0]:
            best = (L, tour)
    if n == 1:
        return []
    t = best[1]
    # also try reverse direction irrelevant (symmetric)
    return [ids[i - 1] for i in t[1:]]


def cost(t, D):
    return sum(D[t[i]][t[(i + 1) % len(t)]] for i in range(len(t)))


def improve(t, D):
    n, better = len(t), True
    while better:
        better = False
        for i in range(1, n - 1):                      # 2-opt
            for j in range(i + 1, n):
                a, b, c, d = t[i - 1], t[i], t[j], t[(j + 1) % n]
                if D[a][c] + D[b][d] < D[a][b] + D[c][d]:
                    t[i:j + 1] = t[i:j + 1][::-1]
                    better = True
        for i in range(1, n):                          # or-opt (move 1 node)
            for j in range(1, n):
                if j == i or j == i - 1:
                    continue
                p, x, nx = t[i - 1], t[i], t[(i + 1) % n]
                u, v = t[j], t[(j + 1) % n]
                if x in (u, v):
                    continue
                if D[p][nx] + D[u][x] + D[x][v] < D[p][x] + D[x][nx] + D[u][v] - 0:
                    node = t.pop(i)
                    jj = t.index(u)
                    t.insert(jj + 1, node)
                    better = True
                    break
            if better:
                break
    return t


def simulate(store, order, speed=1.2, pick=5.0, every=25, label="", out=print):
    """Walk the route cell by cell. Prints live KPIs; returns (distance_m, time_s, trace)."""
    cur, dist, t, picked = store.station, 0, 0.0, 0
    trace = []
    legs = [(pid, store.access[pid]) for pid in order] + [("STATION", [store.station])]
    for pid, targets in legs:
        for cell in store.path(cur, targets):
            cur, dist, t = cell, dist + 1, t + 1 / speed
            trace.append(cell)
            if every and dist % every == 0:
                out(f"[{label}] t={t:7.1f}s dist={dist:5d}m picked={picked}/{len(order)} -> {pid}")
        if pid != "STATION":
            t += pick
            picked += 1
            out(f"[{label}] t={t:7.1f}s dist={dist:5d}m PICK {pid} {store.names[pid]} ({picked}/{len(order)})")
    return dist, t, trace


def read_list(path):
    items = []
    for ln in open(path):
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            pid, _, name = ln.partition(":")
            items.append((pid.strip(), name.strip()))
    return items


def compare(store, ids, speed=1.2, pick=5.0, every=25, out=print):
    opt = optimize(store, ids)
    d0, t0, _ = simulate(store, ids, speed, pick, every, "LIST", out)
    d1, t1, _ = simulate(store, opt, speed, pick, every, "OPT ", out)
    out(f"\n{'':14}{'list-order':>12}{'optimized':>12}")
    out(f"{'distance (m)':14}{d0:12d}{d1:12d}")
    out(f"{'time-to-basket':14}{t0:11.0f}s{t1:11.0f}s")
    sd, st = 100 * (1 - d1 / d0) if d0 else 0, 100 * (1 - t1 / t0) if t0 else 0
    out(f"saving: distance {sd:.1f}%, time {st:.1f}%")
    return st


def gen_store(w=120, h=80, seed=1, nprod=2000):
    """Aisles of shelves (2 wide) with cross-aisles, random pillars/blocked areas, station bottom-left."""
    rnd = random.Random(seed)
    g = [["." for _ in range(w)] for _ in range(h)]
    for c in range(0, w):
        if c % 4 in (1, 2) and 0 < c < w - 1:
            for r in range(2, h - 2):
                if r % 20 not in (0, 1):  # cross aisles every 20 rows
                    g[r][c] = "#"
    for _ in range(w * h // 400):  # arbitrary obstacles (islands/pillars)
        r, c, rh, cw = rnd.randrange(h), rnd.randrange(w), rnd.randint(1, 4), rnd.randint(1, 6)
        for rr in range(r, min(h - 1, r + rh)):
            for cc in range(c, min(w - 1, c + cw)):
                g[rr][cc] = "#"
    g[h - 1][0] = "S"
    g[h - 2][0] = g[h - 1][1] = "."
    store = Store({"grid": ["".join(r) for r in g], "products": {"X": {"name": "x", "pos": [h - 1, 0]}}})
    reach = store.bfs([store.station])
    shelves = [(r, c) for r in range(h) for c in range(w) if g[r][c] == "#"
               and any(0 <= r + dr < h and 0 <= c + dc < w and reach[(r + dr) * w + c + dc] >= 0 for dr, dc in DIRS)]
    products = {}
    for k, (r, c) in enumerate(rnd.sample(shelves, min(nprod, len(shelves)))):
        products[f"P{k:04d}"] = {"name": f"item{k}", "pos": [r, c]}
    return {"grid": ["".join(r) for r in g], "products": products}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["gen", "run", "demo"])
    ap.add_argument("files", nargs="*")
    ap.add_argument("--out", default="store.json")
    ap.add_argument("--w", type=int, default=120)
    ap.add_argument("--h", type=int, default=80)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--items", type=int, default=25)
    ap.add_argument("--every", type=int, default=25, help="print progress every N metres (0=picks only)")
    ap.add_argument("--speed", type=float, default=1.2, help="walking m/s (1 cell = 1 m)")
    ap.add_argument("--pick", type=float, default=5.0, help="seconds to pick one item")
    a = ap.parse_args(argv)
    if a.cmd == "gen":
        json.dump(gen_store(a.w, a.h, a.seed), open(a.out, "w"))
        print("wrote", a.out)
        return 0
    if a.cmd == "run":
        store = Store(json.load(open(a.files[0])))
        ids = []
        for pid, _ in read_list(a.files[1]):
            if pid not in store.access:
                sys.exit(f"unknown product id: {pid}")
            ids.append(pid)
        return 0 if compare(store, ids, a.speed, a.pick, a.every) > 30 else 1
    data = gen_store(a.w, a.h, a.seed)
    store = Store(data)
    ids = random.Random(a.seed).sample(sorted(data["products"]), a.items)
    print(f"store {a.w}x{a.h}, {len(data['products'])} products, list of {len(ids)} (list order = random)")
    st = compare(store, ids, a.speed, a.pick, a.every)
    assert st > 30, f"saving {st:.1f}% < 30%"
    print("PASS: time saving > 30%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
