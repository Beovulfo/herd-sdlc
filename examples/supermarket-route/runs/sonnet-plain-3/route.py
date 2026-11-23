#!/usr/bin/env python3
"""Supermarket picking-route optimizer + step-by-step simulator. Stdlib only.

Map JSON: {"grid": ["#...", ...], "start": [x, y], "end": [x, y],
           "products": [{"id": "P1", "name": "milk", "x": 3, "y": 2}, ...]}
Grid chars: '#' = shelf/wall (products sit on shelf cells), anything else = walkable floor.
Shopping list: text file, one "id:short name" per line (only the id is used for lookup).

  python3 route.py gen --aisles 12 --length 40 --seed 1 --out store.json
  python3 route.py run store.json --list list.txt            # simulate both routes
  python3 route.py demo                                      # generate + random list + compare
"""
import argparse, json, random, sys, time
from collections import deque

WALK_SPEED = 1.2   # m/s, 1 grid cell = 1 m
PICK_TIME = 6.0    # s per item (same for both routes)
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def load(path):
    with open(path) as f:
        return json.load(f)


def floor(grid, x, y):
    return 0 <= y < len(grid) and 0 <= x < len(grid[y]) and grid[y][x] != '#'


def bfs(grid, src, goals=None):
    """Distances/parents from src over floor cells (src itself may be a shelf)."""
    dist, par, q = {src: 0}, {src: None}, deque([src])
    while q:
        c = q.popleft()
        for dx, dy in DIRS:
            n = (c[0] + dx, c[1] + dy)
            if n not in dist and floor(grid, *n):
                dist[n], par[n] = dist[c] + 1, c
                q.append(n)
    return dist, par


def access(grid, p):
    return [(p[0] + dx, p[1] + dy) for dx, dy in DIRS if floor(grid, p[0] + dx, p[1] + dy)]


def build(m, items):
    """Nodes: 0=start, 1..n=items, n+1=end. Returns node cells and distance matrix."""
    g = m["grid"]
    nodes = [tuple(m["start"])] + [(p["x"], p["y"]) for p in items] + [tuple(m["end"])]
    acc = [access(g, c) if g[c[1]][c[0]] == '#' else [c] for c in nodes]
    for c, a in zip(nodes, acc):
        if not a:
            raise SystemExit(f"cell {c} is not reachable (no walkable neighbour)")
    # ponytail: picker may stand on any adjacent floor cell; matrix assumes best side on both ends.
    D = [[0] * len(nodes) for _ in nodes]
    for i, c in enumerate(nodes):
        d, _ = bfs(g, c)
        off = 1 if g[c[1]][c[0]] == '#' else 0
        for j, a in enumerate(acc):
            if i != j:
                best = min((d[f] for f in a if f in d), default=None)
                if best is None:
                    raise SystemExit(f"node {j} unreachable from node {i}")
                D[i][j] = max(0, best - off)
    return nodes, D


def length(order, D):
    return sum(D[a][b] for a, b in zip(order, order[1:]))


def optimize(D):
    """Fixed start 0 and end n+1; nearest neighbour then 2-opt + or-opt until no gain.
    ponytail: heuristic (not exact); fine to ~150 items, swap in Or-tools/LKH beyond."""
    n = len(D) - 2
    left, order = set(range(1, n + 1)), [0]
    while left:
        nxt = min(left, key=lambda j: D[order[-1]][j])
        order.append(nxt); left.remove(nxt)
    order.append(n + 1)
    best = length(order, D)
    improved = True
    while improved:
        improved = False
        for i in range(1, n):
            for j in range(i + 1, n + 1):
                cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                if (c := length(cand, D)) < best:
                    order, best, improved = cand, c, True
        for i in range(1, n + 1):          # or-opt: move one stop
            for j in range(1, n + 1):
                if i == j:
                    continue
                cand = order[:i] + order[i + 1:]
                cand.insert(j, order[i])
                if (c := length(cand, D)) < best:
                    order, best, improved = cand, c, True
    return order


def simulate(m, items, order, nodes):
    """Yield one event per step: (step, cell, distance_m, time_s, picked_item_or_None)."""
    g = m["grid"]
    pos, dist, t, step = nodes[0], 0, 0.0, 0
    yield step, pos, dist, t, None
    for k in order[1:]:
        goal = nodes[k]
        targets = set(access(g, goal)) if g[goal[1]][goal[0]] == '#' else {goal}
        d, par = bfs(g, pos)
        end = min((f for f in targets if f in d), key=lambda f: d[f])
        path = []
        while end != pos:
            path.append(end); end = par[end]
        for cell in reversed(path):
            pos, step, dist, t = cell, step + 1, dist + 1, t + 1 / WALK_SPEED
            yield step, pos, dist, t, None
        if 1 <= k <= len(items):
            t += PICK_TIME
            yield step, pos, dist, t, items[k - 1]


def run_route(label, m, items, order, nodes, verbose, realtime):
    last = None
    print(f"\n== {label} ==")
    for step, pos, dist, t, picked in simulate(m, items, order, nodes):
        last = (dist, t)
        if verbose or picked or step == 0:
            tag = f"PICK {picked['id']}:{picked['name']}" if picked else ""
            print(f"step {step:5d} pos={pos} distance={dist:6.0f} m  time={t:7.1f} s  {tag}", flush=True)
        if realtime:
            time.sleep(0.02)
    print(f"{label}: time-to-prepare-basket={last[1]:.1f} s  distance-covered={last[0]:.0f} m")
    return last


def parse_list(path, m):
    byid = {p["id"]: p for p in m["products"]}
    items, seen = [], set()
    for line in open(path):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        pid = line.split(':', 1)[0].strip()
        if pid not in byid:
            raise SystemExit(f"unknown product id {pid!r} in shopping list")
        if pid not in seen:
            seen.add(pid); items.append(byid[pid])
    return items


def compare(m, items, verbose=False, realtime=False):
    nodes, D = build(m, items)
    base = list(range(len(nodes)))                       # list order
    opt = optimize(D)
    b = run_route("LIST ORDER (baseline)", m, items, base, nodes, verbose, realtime)
    o = run_route("OPTIMIZED", m, items, opt, nodes, verbose, realtime)
    saved = 100 * (1 - o[1] / b[1])
    print(f"\nTime saved: {saved:.1f}%   Distance saved: {100 * (1 - o[0] / b[0]):.1f}%   "
          f"({'PASS' if saved > 30 else 'FAIL'} vs 30% target)")
    return saved


def gen(aisles, length_, seed):
    """Aisles of shelves (2 products deep reachable from both sides) with cross-aisles every 10 cols."""
    rnd = random.Random(seed)
    W, H = length_ + 2, aisles * 3 + 1
    grid = [['.'] * W for _ in range(H)]
    for r in range(aisles):
        y = 2 + r * 3
        for x in range(2, W - 2):
            if (x - 2) % 11 not in (5, 6) and y < H - 1:
                grid[y][x] = '#'
    prods, n = [], 0
    names = ["milk", "bread", "eggs", "rice", "pasta", "tea", "soap", "salt", "jam", "oil"]
    for y, row in enumerate(grid):
        for x, c in enumerate(row):
            if c == '#':
                n += 1
                prods.append({"id": f"P{n}", "name": f"{rnd.choice(names)}{n}", "x": x, "y": y})
    return {"grid": [''.join(r) for r in grid], "start": [0, H - 1], "end": [W - 1, H - 1], "products": prods}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen"); g.add_argument("--aisles", type=int, default=10)
    g.add_argument("--length", type=int, default=40); g.add_argument("--seed", type=int, default=1)
    g.add_argument("--out", required=True)
    r = sub.add_parser("run"); r.add_argument("map"); r.add_argument("--list", required=True)
    r.add_argument("-v", "--verbose", action="store_true", help="print every step")
    r.add_argument("--realtime", action="store_true", help="slow down so KPIs tick live")
    d = sub.add_parser("demo"); d.add_argument("--items", type=int, default=25)
    d.add_argument("--aisles", type=int, default=12); d.add_argument("--length", type=int, default=60)
    d.add_argument("--seed", type=int, default=1); d.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "gen":
        json.dump(gen(a.aisles, a.length, a.seed), open(a.out, "w"))
        print("wrote", a.out)
    elif a.cmd == "run":
        m = load(a.map)
        compare(m, parse_list(a.list, m), a.verbose, a.realtime)
    else:
        m = gen(a.aisles, a.length, a.seed)
        items = random.Random(a.seed).sample(m["products"], a.items)   # random = list order unrelated to layout
        print(f"store {len(m['grid'][0])}x{len(m['grid'])}, {len(m['products'])} products, list of {len(items)}")
        compare(m, items, a.verbose)


if __name__ == "__main__":
    main()
