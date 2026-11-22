"""Supermarket picking-route optimizer with a step-by-step simulator.

Inputs:
  store.txt     grid map: '#' shelf/wall, '.' aisle, 'S' start / packing station
  products.csv  id,short_name,row,col   (row/col of the shelf cell holding the product)
  order.txt     one 'id:short_name' per line (the customer's shopping list)

Usage:
  python3 route.py simulate [--algo opt|random] [--seed N] [--delay SEC]
  python3 route.py compare  [--runs N]     # exits 1 if savings <= 20%
"""
import argparse
import csv
import random
import sys
import time
from collections import deque

CELL_M = 1.0      # metres per grid cell
SPEED_MPS = 1.0   # walking speed with a trolley
PICK_S = 15.0     # seconds to take one product off the shelf
MOVES = ((1, 0), (-1, 0), (0, 1), (0, -1))


def load_map(path):
    grid = [line.rstrip("\n") for line in open(path) if line.strip()]
    start = next((r, row.index("S")) for r, row in enumerate(grid) if "S" in row)
    return grid, start


def load_products(path):
    with open(path, newline="") as f:
        return {row["id"]: (row["short_name"], (int(row["row"]), int(row["col"])))
                for row in csv.DictReader(f)}


def load_order(path, products):
    ids = []
    for line in open(path):
        if not line.strip():
            continue
        pid, _, name = line.strip().partition(":")
        if pid not in products:
            sys.exit(f"order: unknown product id {pid!r}")
        if name and name != products[pid][0]:
            sys.exit(f"order: {pid} is {products[pid][0]!r}, not {name!r}")
        ids.append(pid)
    return ids


def walkable(grid, cell):
    r, c = cell
    return 0 <= r < len(grid) and 0 <= c < len(grid[r]) and grid[r][c] != "#"


def neighbours(grid, cell):
    return [(cell[0] + dr, cell[1] + dc) for dr, dc in MOVES
            if walkable(grid, (cell[0] + dr, cell[1] + dc))]


def bfs(grid, src):
    """Shortest-path tree from src: {cell: parent}."""
    parent = {src: None}
    q = deque([src])
    while q:
        cur = q.popleft()
        for n in neighbours(grid, cur):
            if n not in parent:
                parent[n] = cur
                q.append(n)
    return parent


def path_to(parent, dst):
    out = []
    while dst is not None:
        out.append(dst)
        dst = parent[dst]
    return out[::-1]


def pick_cell(grid, shelf):
    # ponytail: first aisle cell next to the shelf; choosing the best side per tour is an upgrade
    cells = [(shelf[0] + dr, shelf[1] + dc) for dr, dc in MOVES]
    cells = [c for c in cells if walkable(grid, c)]
    if not cells:
        sys.exit(f"shelf {shelf} is not reachable from any aisle")
    return cells[0]


def optimized_route(grid, start, products, order):
    """Nearest-neighbour tour over BFS distances, improved with 2-opt. Returns cell path."""
    stops = [start] + sorted({pick_cell(grid, products[p][1]) for p in order})
    trees = {s: bfs(grid, s) for s in stops}
    d = {(a, b): len(path_to(trees[a], b)) - 1 for a in stops for b in stops}

    tour, left = [start], set(stops[1:])
    while left:
        nxt = min(left, key=lambda s: d[tour[-1], s])
        tour.append(nxt)
        left.remove(nxt)
    tour.append(start)

    improved = True
    while improved:  # ponytail: O(n^2) per pass, fine for basket sizes up to a few hundred
        improved = False
        for i in range(1, len(tour) - 2):
            for j in range(i + 1, len(tour) - 1):
                a, b, c, e = tour[i - 1], tour[i], tour[j], tour[j + 1]
                if d[a, c] + d[b, e] < d[a, b] + d[c, e]:
                    tour[i:j + 1] = tour[i:j + 1][::-1]
                    improved = True

    path = [start]
    for a, b in zip(tour, tour[1:]):
        path += path_to(trees[a], b)[1:]
    return path


def random_walk(grid, start, products, order, seed):
    """Unoptimized baseline: wander to a random neighbour each step until every
    product has been passed, then return to the station by the shortest path."""
    rng = random.Random(seed)
    shelves = {products[p][1] for p in order}
    pos, path = start, [start]
    while True:
        shelves -= {(pos[0] + dr, pos[1] + dc) for dr, dc in MOVES}
        if not shelves:
            break
        pos = rng.choice(neighbours(grid, pos))
        path.append(pos)
    return path + path_to(bfs(grid, start), pos)[::-1][1:]


def simulate(path, products, order):
    """Yield one state per step: (step, cell, distance_m, elapsed_s, picked_ids)."""
    todo = {p: products[p][1] for p in order}
    picked, dist, t = [], 0.0, 0.0
    for step, cell in enumerate(path):
        if step:
            dist += CELL_M
            t += CELL_M / SPEED_MPS
        for pid, shelf in list(todo.items()):
            if abs(shelf[0] - cell[0]) + abs(shelf[1] - cell[1]) == 1:
                picked.append(pid)
                del todo[pid]
                t += PICK_S
        yield step, cell, dist, t, list(picked)
    if todo:
        raise RuntimeError(f"route never reached {sorted(todo)}")


def kpis(path, products, order):
    *_, (_, _, dist, t, _) = simulate(path, products, order)
    return dist, t


def render(grid, cell, visited, products, picked):
    shelves = {products[p][1] for p in picked}
    rows = []
    for r, line in enumerate(grid):
        row = []
        for c, ch in enumerate(line):
            if (r, c) == cell:
                ch = "@"
            elif (r, c) in shelves:
                ch = "+"
            elif (r, c) in visited and ch == ".":
                ch = "·"
            row.append(ch)
        rows.append("".join(row))
    return "\n".join(rows)


def cmd_simulate(args, grid, start, products, order):
    path = (optimized_route(grid, start, products, order) if args.algo == "opt"
            else random_walk(grid, start, products, order, args.seed))
    visited = set()
    for step, cell, dist, t, picked in simulate(path, products, order):
        visited.add(cell)
        if args.delay:
            print("\033[H\033[J" + render(grid, cell, visited, products, picked))
        last = products[picked[-1]][0] if picked else "-"
        print(f"[{args.algo}] step {step:5d}  pos {cell}  distance-covered {dist:7.1f} m  "
              f"time-to-prepare-basket {t:7.1f} s  picked {len(picked)}/{len(order)} (last: {last})")
        if args.delay:
            time.sleep(args.delay)
    print(f"DONE [{args.algo}] distance-covered={dist:.1f} m time-to-prepare-basket={t:.1f} s")


def cmd_compare(args, grid, start, products, order):
    od, ot = kpis(optimized_route(grid, start, products, order), products, order)
    runs = [kpis(random_walk(grid, start, products, order, s), products, order)
            for s in range(args.runs)]
    rd = sum(r[0] for r in runs) / len(runs)
    rt = sum(r[1] for r in runs) / len(runs)
    worst_case_saving = 1 - ot / min(r[1] for r in runs)
    saving = 1 - ot / rt
    print(f"items in basket       : {len(order)}")
    print(f"optimized             : distance {od:8.1f} m   time {ot:8.1f} s")
    print(f"random walk (mean/{args.runs:<3d}): distance {rd:8.1f} m   time {rt:8.1f} s")
    print(f"time saved vs mean    : {saving:.1%}")
    print(f"time saved vs best rw : {worst_case_saving:.1%}")
    ok = worst_case_saving > 0.20
    print("PASS: optimizer saves >20% time vs every random-walk run" if ok
          else "FAIL: savings <= 20%")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["simulate", "compare"])
    ap.add_argument("--map", default="store.txt")
    ap.add_argument("--products", default="products.csv")
    ap.add_argument("--order", default="order.txt")
    ap.add_argument("--algo", choices=["opt", "random"], default="opt")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--delay", type=float, default=0.0, help="seconds per step; >0 animates the map")
    ap.add_argument("--runs", type=int, default=30)
    args = ap.parse_args()
    grid, start = load_map(args.map)
    products = load_products(args.products)
    order = load_order(args.order, products)
    if args.cmd == "simulate":
        cmd_simulate(args, grid, start, products, order)
    else:
        sys.exit(cmd_compare(args, grid, start, products, order))


if __name__ == "__main__":
    main()
