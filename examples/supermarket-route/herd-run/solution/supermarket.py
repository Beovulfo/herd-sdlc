"""Supermarket picker simulation.

python3 supermarket.py simulate --map MAP.json --list LIST.json --algo optimized|random|list-order --seed N
Prints one JSON line per step, then one final line. Cells are [x, y] = column, row from the top left.
"""
import argparse
import json
import random
import sys
from collections import deque

# One time model for every algorithm.
WALK_S = 1.0  # seconds per move
PICK_S = 5.0  # seconds per item picked
EXACT_MAX = 12  # ponytail: Held-Karp is O(2^n n^2); above this use nearest neighbour + 2-opt
MAX_RANDOM_STEPS = 2_000_000


class Store:
    def __init__(self, grid, start, products):
        self.grid, self.start, self.products = grid, start, products  # products: id -> (name, (x, y))

    @classmethod
    def from_dict(cls, d):
        grid = [str(r) for r in d["grid"]]
        store = cls(grid, tuple(d["start"]), {})
        if not store.walkable(store.start):
            raise ValueError(f"start {list(store.start)} is not a walkable cell")
        for pid, p in d["products"].items():
            cell = tuple(p["cell"])
            if len(cell) != 2 or not store.walkable(cell):
                raise ValueError(f"product {pid} cell {list(cell)} is not a walkable cell")
            store.products[pid] = (p["name"], cell)
        return store

    def walkable(self, cell):
        x, y = cell
        return 0 <= y < len(self.grid) and 0 <= x < len(self.grid[y]) and self.grid[y][x] != "#"

    def neighbors(self, cell):
        x, y = cell
        return [c for c in ((x, y - 1), (x, y + 1), (x - 1, y), (x + 1, y)) if self.walkable(c)]


def parse_items(d, store):
    """List dict -> distinct product ids in list order. Raises ValueError on unknown id or unreachable item."""
    ids = []
    for it in d["items"]:
        if not isinstance(it, dict) or "id" not in it:
            raise ValueError(f"list item {it!r} needs an id")
        if it["id"] not in store.products:
            raise ValueError(f"unknown product id {it['id']!r}")
        if it["id"] not in ids:
            ids.append(it["id"])
    reach = bfs(store, store.start)[0]
    for i in ids:
        if store.products[i][1] not in reach:
            raise ValueError(f"unreachable product {i} at {list(store.products[i][1])}")
    return ids


def bfs(store, src):
    """Return (dist, prev) dicts over cells reachable from src."""
    dist, prev, q = {src: 0}, {src: None}, deque([src])
    while q:
        cur = q.popleft()
        for n in store.neighbors(cur):
            if n not in dist:
                dist[n], prev[n] = dist[cur] + 1, cur
                q.append(n)
    return dist, prev


def path_to(prev, dst):
    """Cells after the source up to dst inclusive."""
    out = []
    while prev[dst] is not None:
        out.append(dst)
        dst = prev[dst]
    return out[::-1]


def _held_karp(d, n):
    """Exact shortest open path from node 0 through 1..n-1; returns visit order without node 0."""
    m = n - 1
    best = {(1 << j, j): (d[0][j + 1], None) for j in range(m)}
    for mask in range(1, 1 << m):
        for j in range(m):
            if (mask, j) not in best:
                continue
            c = best[(mask, j)][0]
            for k in range(m):
                if not mask >> k & 1:
                    key = (mask | 1 << k, k)
                    if key not in best or c + d[j + 1][k + 1] < best[key][0]:
                        best[key] = (c + d[j + 1][k + 1], j)
    full = (1 << m) - 1
    j = min(range(m), key=lambda j: best[(full, j)][0])
    order, mask = [], full
    while j is not None:
        order.append(j + 1)
        mask, j = mask ^ 1 << j, best[(mask, j)][1]
    return order[::-1]


def plan(store, ids):
    """Visiting order of ids minimising total walking distance."""
    if not ids:
        return []
    pts = [store.start] + [store.products[i][1] for i in ids]
    n = len(pts)
    dist = [bfs(store, p)[0] for p in pts]
    d = [[dist[i][pts[j]] for j in range(n)] for i in range(n)]
    if n - 1 <= EXACT_MAX:
        return [ids[k - 1] for k in _held_karp(d, n)]
    order, left = [0], set(range(1, n))
    while left:
        nxt = min(left, key=lambda j: d[order[-1]][j])
        order.append(nxt)
        left.remove(nxt)

    def cost(o):
        return sum(d[a][b] for a, b in zip(o, o[1:]))

    improved = True
    while improved:
        improved = False
        for i in range(1, n):
            for j in range(i + 1, n):
                cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                if cost(cand) < cost(order):
                    order, improved = cand, True
    return [ids[k - 1] for k in order[1:]]


def simulate(store, ids, algo, seed=0):
    """Yield (n, pos, time, distance, picked_ids) per step. Any wanted item on a visited cell is picked."""
    if algo not in ("optimized", "random", "list-order"):
        raise ValueError(f"unknown algo {algo!r}")
    rng = random.Random(seed)
    left = {}
    for i in ids:
        left.setdefault(store.products[i][1], []).append(i)
    s = {"pos": store.start, "t": 0.0, "d": 0, "n": 0}

    def arrive(moved):
        got = left.pop(s["pos"], [])
        if not moved and not got:
            return None
        s["n"] += 1
        s["t"] += PICK_S * len(got)
        return (s["n"], s["pos"], s["t"], s["d"], got)

    def move(cell):
        s["pos"], s["d"], s["t"] = cell, s["d"] + 1, s["t"] + WALK_S
        return arrive(True)

    first = arrive(False)  # items lying on the start cell
    if first:
        yield first
    if algo == "random":
        while left:
            if s["d"] >= MAX_RANDOM_STEPS:
                raise ValueError(f"random walk exceeded {MAX_RANDOM_STEPS} moves")
            yield move(rng.choice(store.neighbors(s["pos"])))
        return
    for i in (plan(store, ids) if algo == "optimized" else ids):
        target = store.products[i][1]
        if target not in left:  # already picked on the way
            continue
        for cell in path_to(bfs(store, s["pos"])[1], target):
            yield move(cell)


def summary(steps):
    last = steps[-1] if steps else (0, None, 0.0, 0, [])
    return {"time_to_prepare": last[2], "distance": last[3], "picked": sum(len(st[4]) for st in steps)}


def main(argv=None, out=sys.stdout):
    ap = argparse.ArgumentParser(prog="supermarket", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("simulate")
    p.add_argument("--map", required=True)
    p.add_argument("--list", required=True)
    p.add_argument("--algo", choices=("optimized", "random", "list-order"), default="optimized")
    p.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    try:
        with open(a.map) as f:
            store = Store.from_dict(json.load(f))
        with open(a.list) as f:
            ids = parse_items(json.load(f), store)
        t, d, picked = 0.0, 0, 0
        for n, pos, t, d, got in simulate(store, ids, a.algo, a.seed):
            picked += len(got)
            print(json.dumps({"type": "step", "n": n, "pos": list(pos), "time": t, "distance": d, "picked": got}),
                  file=out, flush=True)
        print(json.dumps({"type": "final", "algo": a.algo, "time_to_prepare": t, "distance": d, "picked": picked}),
              file=out, flush=True)
    except BrokenPipeError:
        return 0
    except (ValueError, OSError, KeyError, TypeError, IndexError, AttributeError) as e:  # bad input
        why = f"missing key {e}" if isinstance(e, KeyError) else f"malformed input ({type(e).__name__}: {e})" \
            if isinstance(e, (TypeError, IndexError, AttributeError)) else str(e)
        print(f"error: {why}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
