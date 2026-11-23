#!/usr/bin/env python3
"""Supermarket pick-route optimizer + step-by-step simulator. Stdlib only.

  python3 router.py gen  --cols 101 --rows 61 --items 40 --out store      # makes store.json, store_list.txt
  python3 router.py run  store.json store_list.txt [--every 25] [--delay 0.05]

Map JSON: {"grid": ["#.#", ...], "start": [x,y], "end": [x,y],
           "products": {"id": {"name": "milk", "x": 3, "y": 4}}}
Grid: '#' = shelf/wall (not walkable), anything else = floor. A product sits on a cell;
it is picked from the cell itself (if floor) or any floor cell next to it.
List file: one "id:short name" per line (only the id is used).
"""
import argparse, json, random, sys, time
from collections import deque

SPEED = 1.2   # cells (metres) per second walking
PICK = 8.0    # seconds to find + grab + drop one item in the basket
N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


class Store:
    def __init__(self, d):
        self.g = d["grid"]; self.h = len(self.g); self.w = len(self.g[0])
        self.start = tuple(d["start"]); self.end = tuple(d["end"])
        self.products = d["products"]

    def floor(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h and self.g[y][x] != "#"

    def access(self, pid):
        p = self.products[pid]; c = (p["x"], p["y"])
        cells = [c] if self.floor(*c) else [(c[0] + dx, c[1] + dy) for dx, dy in N4 if self.floor(c[0] + dx, c[1] + dy)]
        if not cells:
            raise ValueError(f"product {pid} is not reachable from any floor cell")
        return cells

    def bfs(self, sources, targets=None):
        """Multi-source BFS. Returns (dist, parent); stops early when a target cell is reached."""
        dist = {s: 0 for s in sources}; par = {s: None for s in sources}
        q = deque(sources); targets = set(targets or ())
        while q:
            c = q.popleft()
            if c in targets:
                return dist, par, c
            for dx, dy in N4:
                n = (c[0] + dx, c[1] + dy)
                if n not in dist and self.floor(*n):
                    dist[n] = dist[c] + 1; par[n] = c; q.append(n)
        return dist, par, None

    def path(self, a, targets):
        """Shortest walk from cell a to the nearest cell in targets: list of cells after a."""
        _, par, hit = self.bfs([a], targets)
        if hit is None:
            raise ValueError("unreachable target")
        out = []
        while hit != a:
            out.append(hit); hit = par[hit]
        return out[::-1]


def tour_cost(t, D):
    return sum(D[a][b] for a, b in zip(t, t[1:]))


def optimize(store, ids):
    """Order ids to minimise walking from start to end. Returns the ordered ids.
    Nodes: 0 = start, 1..n = items, n+1 = end. Nearest neighbour, then 2-opt + or-opt until stable."""
    n = len(ids)
    acc = [[store.start]] + [store.access(i) for i in ids] + [[store.end]]
    D = [[0] * (n + 2) for _ in range(n + 2)]
    for a in range(n + 2):
        dist, _, _ = store.bfs(acc[a])
        for b in range(n + 2):
            D[a][b] = min(dist.get(c, 10**9) for c in acc[b]) if a != b else 0
    for a in range(n + 2):          # symmetrise (multi-access cells can differ slightly)
        for b in range(a):
            D[a][b] = D[b][a] = min(D[a][b], D[b][a])
    left = set(range(1, n + 1)); t = [0]
    while left:
        nxt = min(left, key=lambda j: D[t[-1]][j]); t.append(nxt); left.remove(nxt)
    t.append(n + 1)
    improved = True
    while improved:
        improved = False
        for i in range(1, n):                       # 2-opt: reverse t[i..j]
            for j in range(i + 1, n + 1):
                if D[t[i-1]][t[j]] + D[t[i]][t[j+1]] < D[t[i-1]][t[i]] + D[t[j]][t[j+1]]:
                    t[i:j+1] = t[i:j+1][::-1]; improved = True
        for seg in (1, 2, 3):                       # or-opt: move a run of 1-3 items elsewhere
            i = 1
            while i + seg <= n:
                s = t[i:i+seg]; rest = t[:i] + t[i+seg:]
                gain = D[t[i-1]][s[0]] + D[s[-1]][t[i+seg]] - D[t[i-1]][t[i+seg]]
                best = None
                for k in range(len(rest) - 1):
                    for sv in (s, s[::-1]):
                        add = D[rest[k]][sv[0]] + D[sv[-1]][rest[k+1]] - D[rest[k]][rest[k+1]]
                        if add < gain - 1e-9 and (best is None or add < best[0]):
                            best = (add, k, sv)
                if best:
                    _, k, sv = best; t = rest[:k+1] + sv + rest[k+1:]; improved = True
                i += 1
    return [ids[j - 1] for j in t[1:-1]]


def simulate(store, order, every=25, delay=0.0, out=print, label=""):
    """Walk the order step by step, printing live KPIs. Returns (steps, seconds)."""
    pos = store.start; steps = picks = 0
    def kpi(ev):
        return f"[{label}] t={steps / SPEED + picks * PICK:8.1f}s dist={steps:6d}m picked={picks}/{len(order)} {ev}"
    out(kpi("start"))
    for pid in order + [None]:
        targets = [store.end] if pid is None else store.access(pid)
        for cell in store.path(pos, targets):
            pos = cell; steps += 1
            if every and steps % every == 0:
                out(kpi(f"at {pos}"))
                if delay: time.sleep(delay)
        if pid is not None:
            picks += 1; out(kpi(f"PICK {pid} {store.products[pid]['name']} at {pos}"))
    out(kpi("DONE (basket ready at checkout)"))
    return steps, steps / SPEED + picks * PICK


def read_list(path):
    return [l.split(":", 1)[0].strip() for l in open(path) if l.strip() and not l.startswith("#")]


def compare(store, ids, every=25, delay=0.0, out=print):
    """Returns dict of KPIs for the list-order and optimized routes."""
    opt = optimize(store, ids)
    ds, ts = simulate(store, ids, every, delay, out, "list-order")
    do, to = simulate(store, opt, every, delay, out, "optimized ")
    r = dict(list_dist=ds, list_time=ts, opt_dist=do, opt_time=to,
             dist_saved=100 * (1 - do / ds) if ds else 0, time_saved=100 * (1 - to / ts) if ts else 0, order=opt)
    out(f"\nlist-order : {ts:8.1f}s  {ds}m\noptimized  : {to:8.1f}s  {do}m\n"
        f"time saved : {r['time_saved']:.1f}%   distance saved: {r['dist_saved']:.1f}%   "
        f"{'PASS' if r['time_saved'] > 30 else 'FAIL'} (target > 30% time)")
    return r


def generate(cols, rows, items, seed):
    """Warehouse-style store: double-sided shelf blocks, cross aisles every 10 columns,
    entrance bottom-left, checkout bottom-right. Returns (map dict, shopping list lines)."""
    rng = random.Random(seed); cols = cols // 10 * 10 + 1; rows = rows // 3 * 3 + 1
    grid = ["".join("." if y % 3 == 0 or x % 10 == 0 else "#" for x in range(cols)) for y in range(rows)]
    shelves = [(x, y) for y in range(rows) for x in range(cols) if grid[y][x] == "#"]
    names = ["milk", "bread", "eggs", "rice", "pasta", "apples", "cola", "soap", "tea", "salt"]
    ids = rng.sample(range(1000, 1000 + max(len(shelves), items * 5)), min(len(shelves), items * 5))
    prods = {str(i): {"name": f"{names[i % 10]}{i}", "x": x, "y": y}
             for i, (x, y) in zip(ids, rng.sample(shelves, len(ids)))}
    want = rng.sample(list(prods), items)
    return ({"grid": grid, "start": [0, rows - 1], "end": [cols - 1, rows - 1], "products": prods},
            [f"{p}:{prods[p]['name']}" for p in want])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen"); g.add_argument("--cols", type=int, default=101); g.add_argument("--rows", type=int, default=61)
    g.add_argument("--items", type=int, default=40); g.add_argument("--seed", type=int, default=1); g.add_argument("--out", default="store")
    r = sub.add_parser("run"); r.add_argument("map"); r.add_argument("list")
    r.add_argument("--every", type=int, default=25, help="print KPIs every N steps (0 = only at picks)")
    r.add_argument("--delay", type=float, default=0.0, help="seconds to sleep per printed frame (real-time feel)")
    a = ap.parse_args(argv)
    if a.cmd == "gen":
        m, lst = generate(a.cols, a.rows, a.items, a.seed)
        json.dump(m, open(a.out + ".json", "w")); open(a.out + "_list.txt", "w").write("\n".join(lst) + "\n")
        print(f"wrote {a.out}.json ({len(m['grid'][0])}x{len(m['grid'])}, {len(m['products'])} products) and {a.out}_list.txt ({len(lst)} items)")
        return 0
    store = Store(json.load(open(a.map))); ids = read_list(a.list)
    missing = [i for i in ids if i not in store.products]
    if missing:
        sys.exit(f"unknown product ids: {missing}")
    return 0 if compare(store, ids, a.every, a.delay)["time_saved"] > 30 else 1


if __name__ == "__main__":
    sys.exit(main())
