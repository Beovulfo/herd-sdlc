#!/usr/bin/env python3
"""Tiny reference `supermarket.py simulate` used only to test the verifier. Not the example solution."""
import argparse
import json
import random
import sys
from collections import deque


def bfs(grid, src):
    d, q = {src: 0}, deque([src])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if grid[n[1]][n[0]] == "." and n not in d:
                d[n] = d[(x, y)] + 1
                q.append(n)
    return d


def path(grid, a, b):
    prev, q = {a: None}, deque([a])
    while q:
        c = q.popleft()
        if c == b:
            break
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (c[0] + dx, c[1] + dy)
            if grid[n[1]][n[0]] == "." and n not in prev:
                prev[n] = c
                q.append(n)
    out, c = [], b
    while prev[c] is not None:
        out.append(c)
        c = prev[c]
    return out[::-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("--map")
    ap.add_argument("--list")
    ap.add_argument("--algo")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    store, lst = json.load(open(a.map)), json.load(open(a.list))
    grid = store["grid"]
    cell = {i["id"]: tuple(store["products"][i["id"]]["cell"]) for i in lst["items"]}
    pos, t, dist, n, left = tuple(store["start"]), 0.0, 0, 0, dict(cell)

    def emit(p, picked):
        nonlocal t, dist, n
        n += 1
        t += 1.0 + 5.0 * len(picked)
        dist += 1
        print(json.dumps({"type": "step", "n": n, "pos": list(p), "time": t, "distance": dist, "picked": picked}))

    def pick_here():
        got = [i for i, c in left.items() if c == pos]
        for i in got:
            del left[i]
        return got

    if a.algo == "random":
        rnd = random.Random(a.seed)
        pick_here()
        while left and n < 2_000_000:
            opts = [(pos[0] + dx, pos[1] + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            opts = [o for o in opts if grid[o[1]][o[0]] == "."]
            pos = rnd.choice(opts)
            emit(pos, pick_here())
    else:
        order = list(cell) if a.algo == "list-order" else None
        while left:
            if order is not None:
                target = cell[next(i for i in order if i in left)]
            else:
                d = bfs(grid, pos)
                target = min(left.values(), key=lambda c: d[c])
            for p in path(grid, pos, target):
                pos = p
                emit(pos, pick_here() if pos == target else [])
            if pos == target and pos in left.values():
                pass
    print(json.dumps({"type": "final", "algo": a.algo, "time_to_prepare": t, "distance": dist,
                      "picked": len(cell)}))


if __name__ == "__main__":
    sys.exit(main())
