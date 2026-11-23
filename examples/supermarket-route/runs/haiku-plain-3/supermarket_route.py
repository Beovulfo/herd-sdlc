#!/usr/bin/env python3
"""Picking route optimizer for supermarkets (standard library only, Python 3.11+).

Inputs
  map (JSON): {"grid": ["..#..", ...], "start": [x, y],
               "products": [{"id": "P001", "name": "milk", "x": 1, "y": 0}]}
      '#' is a blocked cell (shelf, wall, counter). Any other character is a
      walkable aisle cell. A product sits on the aisle cell it is picked from.
  request (text): one "id:short name" per line, in the customer's list order.
      Only the id is used. Lines starting with "#" are comments.

Model
  One grid step is one cell (STEP_SECONDS). Each pick takes PICK_SECONDS.
  The basket is ready when the last item is picked.
  Distances are exact shortest walking paths (BFS), so any layout works.
  Route = nearest-neighbour start, then 2-opt on the open path (start fixed).

Usage
  python3 supermarket_route.py                 # uses examples/
  python3 supermarket_route.py --live --speed 50
"""

import argparse
import collections
import json
import os
import sys
import time

STEP_SECONDS = 1.0  # one cell = 1 m, walking at 1 m/s
PICK_SECONDS = 5.0  # time to take one item off a shelf


class Store:
    def __init__(self, data):
        grid = data["grid"]
        self.h = len(grid)
        self.w = len(grid[0])
        if any(len(row) != self.w for row in grid):
            raise ValueError("all grid rows must have the same length")
        self.open = [ch != "#" for row in grid for ch in row]
        self.start = self.index(data["start"])
        self.products = {}  # id -> (short name, cell index)
        for p in data["products"]:
            pid = str(p["id"])
            if pid in self.products:
                raise ValueError(f"duplicate product id {pid}")
            self.products[pid] = (p.get("name", ""), self.index((p["x"], p["y"])))

    def index(self, xy):
        x, y = xy
        if not (0 <= x < self.w and 0 <= y < self.h) or not self.open[y * self.w + x]:
            raise ValueError(f"cell {xy} is outside the map or blocked")
        return y * self.w + x

    def xy(self, i):
        return (i % self.w, i // self.w)

    def bfs(self, src):
        """Walking steps from src to every cell (-1 = unreachable), plus parents."""
        n = self.w * self.h
        dist = [-1] * n
        parent = [-1] * n
        dist[src] = 0
        queue = collections.deque([src])
        while queue:
            cur = queue.popleft()
            x = cur % self.w
            for nxt in (cur - 1 if x else -1, cur + 1 if x < self.w - 1 else -1,
                        cur - self.w, cur + self.w):
                if 0 <= nxt < n and self.open[nxt] and dist[nxt] < 0:
                    dist[nxt] = dist[cur] + 1
                    parent[nxt] = cur
                    queue.append(nxt)
        return dist, parent

    def distances(self, cells):
        """Matrix of walking steps between every pair of cells."""
        m = len(cells)
        mat = [[0] * m for _ in range(m)]
        for a, src in enumerate(cells):
            dist, _ = self.bfs(src)
            for b, dst in enumerate(cells):
                if dist[dst] < 0:
                    raise ValueError(f"no walkable path from {self.xy(src)} to {self.xy(dst)}")
                mat[a][b] = dist[dst]
        return mat


def parse_request(text, store):
    ids = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pid = line.split(":", 1)[0].strip()
        if pid not in store.products:
            raise ValueError(f"product {pid!r} is not on the map")
        ids.append(pid)
    return ids


def path_cost(mat, order):
    return sum(mat[order[k]][order[k + 1]] for k in range(len(order) - 1))


def optimize_order(mat):
    """Visit order over stop indices, index 0 (start) fixed first.

    ponytail: nearest-neighbour + 2-opt is O(n^2) per pass; fine for a basket
    of up to a few hundred items. Upgrade to Or-opt or OR-tools if it gets slow.
    """
    m = len(mat)
    order = [0]
    left = set(range(1, m))
    while left:
        cur = order[-1]
        nxt = min(left, key=lambda j: (mat[cur][j], j))
        order.append(nxt)
        left.remove(nxt)
    improved = True
    while improved:
        improved = False
        for i in range(1, m - 1):
            for j in range(i + 1, m):
                a, b, c = order[i - 1], order[i], order[j]
                old = mat[a][b]
                new = mat[a][c]
                if j + 1 < m:  # open path: the last leg has no closing edge
                    d = order[j + 1]
                    old += mat[c][d]
                    new += mat[b][d]
                if new < old:
                    order[i:j + 1] = order[i:j + 1][::-1]
                    improved = True
    return order


def simulate(store, cells, names):
    """Walk the route cell by cell. Yields one event per step and per pick."""
    t = 0.0
    steps = 0
    picks = 0
    pos = cells[0]
    for target, name in zip(cells[1:], names[1:]):
        _, parent = store.bfs(pos)
        legs = []
        c = target
        while c != pos:
            legs.append(c)
            c = parent[c]
        for cell in reversed(legs):
            steps += 1
            t += STEP_SECONDS
            pos = cell
            yield {"event": "step", "item": None, "time_s": t, "distance": steps,
                   "picked": picks, "xy": store.xy(pos)}
        t += PICK_SECONDS
        picks += 1
        yield {"event": "pick", "item": name, "time_s": t, "distance": steps,
               "picked": picks, "xy": store.xy(pos)}


def plan(store, ids):
    cells = [store.start] + [store.products[i][1] for i in ids]
    names = ["start"] + list(ids)
    mat = store.distances(cells)
    return {
        "cells": cells,
        "names": names,
        "optimized": optimize_order(mat),
        "list": list(range(len(cells))),
        "mat": mat,
    }


def run_route(store, planned, order, on_event=None):
    """Simulate one visit order; return the final KPIs."""
    last = {"time_s": 0.0, "distance": 0, "picked": 0}
    for ev in simulate(store, [planned["cells"][i] for i in order],
                       [planned["names"][i] for i in order]):
        last = ev
        if on_event:
            on_event(ev)
    return last


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Supermarket picking route optimizer")
    ap.add_argument("--map", default=os.path.join(here, "examples", "store.json"))
    ap.add_argument("--request", default=os.path.join(here, "examples", "request.txt"))
    ap.add_argument("--live", action="store_true", help="print each pick as it happens")
    ap.add_argument("--speed", type=float, default=0.0,
                    help="replay speed factor (e.g. 50 = 50x real time); 0 = no sleep")
    ap.add_argument("--target", type=float, default=0.30, help="required time saving")
    args = ap.parse_args(argv)

    with open(args.map, encoding="utf-8") as f:
        store = Store(json.load(f))
    with open(args.request, encoding="utf-8") as f:
        ids = parse_request(f.read(), store)
    if not ids:
        raise SystemExit("request is empty")

    planned = plan(store, ids)

    def live_printer(label):
        def show(ev):
            if args.speed > 0 and ev["event"] == "step":
                time.sleep(STEP_SECONDS / args.speed)
            if args.live and ev["event"] == "pick":
                print(f"  [{label}] pick {ev['item']:<12} t={ev['time_s']:7.1f}s "
                      f"distance={ev['distance']:5d} cells  ({ev['picked']}/{len(ids)})")
        return show

    results = {}
    for label, order in (("list-order", planned["list"]), ("optimized", planned["optimized"])):
        results[label] = run_route(store, planned, order, live_printer(label))

    base, opt = results["list-order"], results["optimized"]
    saving = (base["time_s"] - opt["time_s"]) / base["time_s"] if base["time_s"] else 0.0
    dist_saving = (base["distance"] - opt["distance"]) / base["distance"] if base["distance"] else 0.0
    verdict = "MET" if saving > args.target else "NOT MET"

    print(f"Map {store.w}x{store.h} cells, {len(ids)} items, start at {store.xy(store.start)}")
    print(f"{'KPI':<24}{'list-order':>14}{'optimized':>14}")
    print(f"{'time-to-prepare (s)':<24}{base['time_s']:>14.1f}{opt['time_s']:>14.1f}")
    print(f"{'distance-covered (cells)':<24}{base['distance']:>14d}{opt['distance']:>14d}")
    print(f"Time saving: {saving:.1%}  (distance saving: {dist_saving:.1%})  "
          f"target >{args.target:.0%}: {verdict}")
    print("Optimized order: " + " -> ".join(planned["names"][i] for i in planned["optimized"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
