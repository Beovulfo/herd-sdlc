"""Supermarket route optimizer: shortest picking walk for a basket (standard library only).

Store map (JSON):
  {"grid": ["#####", "#..##", ...],
   "entrance": {"x": 1, "y": 1},
   "products": [{"id": "P1", "name": "milk", "x": 2, "y": 1}]}
'.' is walkable, '#' is a wall or shelf. A product sits on a walkable access cell.

Basket (text): one "id:short name" per line.
"""

import argparse
import json
import random
import sys
import time
from collections import deque, namedtuple

CELL_M = 1.0        # metres per grid cell
WALK_M_PER_S = 1.2  # walking speed
PICK_S = 8.0        # seconds to pick one item

Step = namedtuple("Step", "kind cell distance_m seconds picked")


class RouteError(ValueError):
    pass


class Store:
    def __init__(self, grid, entrance, products):
        self.grid = grid
        self.width = len(grid[0])
        self.height = len(grid)
        self.entrance = entrance
        self.products = products  # id -> (cell, short name)

    def walkable(self, cell):
        x, y = cell
        return 0 <= x < self.width and 0 <= y < self.height and self.grid[y][x] == "."

    def neighbours(self, cell):
        x, y = cell
        for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if self.walkable(nb):
                yield nb


def _xy(obj, label):
    if not isinstance(obj, dict) or type(obj.get("x")) is not int or type(obj.get("y")) is not int:
        raise RouteError(f"{label} needs integer 'x' and 'y'")
    return (obj["x"], obj["y"])


def parse_store(data):
    if not isinstance(data, dict):
        raise RouteError("store map must be a JSON object")
    grid = data.get("grid")
    if not isinstance(grid, list) or not grid or not all(isinstance(r, str) for r in grid):
        raise RouteError("store map needs 'grid': a non-empty list of strings")
    width = len(grid[0])
    if width == 0 or any(len(r) != width for r in grid):
        raise RouteError("store map grid rows must all have the same non-zero length")
    if any(ch not in ".#" for r in grid for ch in r):
        raise RouteError("store grid may only contain '.' (walkable) and '#' (wall or shelf)")
    store = Store(grid, None, {})
    store.entrance = _xy(data.get("entrance"), "entrance")
    if not store.walkable(store.entrance):
        raise RouteError("entrance must be a walkable cell inside the grid")
    products = data.get("products")
    if not isinstance(products, list):
        raise RouteError("store map needs 'products': a list")
    # a broken product entry only fails the baskets that ask for it
    store.broken = {}
    for n, p in enumerate(products):
        pid = p.get("id") if isinstance(p, dict) else None
        key = pid if isinstance(pid, str) and pid.strip() else f"entry {n}"
        try:
            cell, name = _product(store, p, key)
        except RouteError as e:
            store.broken[key] = str(e)
            continue
        if key in store.products or key in store.broken:
            store.products.pop(key, None)
            store.broken[key] = f"duplicate product id {key} in store map"
            continue
        store.products[key] = (cell, name)
    return store


def _product(store, p, key):
    if not isinstance(p, dict):
        raise RouteError(f"product entry {key} must be an object")
    if key.startswith("entry "):
        raise RouteError(f"product entry {key} needs a non-empty string 'id'")
    name = p.get("name")
    if not isinstance(name, str):
        raise RouteError(f"product {key} needs a string 'name'")
    cell = _xy(p, f"product {key}")
    if not store.walkable(cell):
        raise RouteError(f"product {key} at {cell} is not on a walkable cell")
    return cell, name


def parse_basket(lines):
    ids = []
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        pid, sep, _name = line.partition(":")
        if not sep or not pid.strip():
            raise RouteError(f"basket line {n} must be 'id:short name': {line!r}")
        ids.append(pid.strip())
    if not ids:
        raise RouteError("basket is empty")
    return ids


def _read(path, what):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        raise RouteError(f"cannot read {what} {path}: {e.strerror}")
    except UnicodeDecodeError:
        raise RouteError(f"{what} {path} is not UTF-8 text")


def load_store(path):
    try:
        return parse_store(json.loads(_read(path, "store map")))
    except json.JSONDecodeError as e:
        raise RouteError(f"store map {path} is not valid JSON: {e}")


def load_basket(path):
    return parse_basket(_read(path, "basket").splitlines())


def _bfs(store, src, targets=()):
    dist, parent = {src: 0}, {src: None}
    left = set(targets) - {src}
    full = not targets  # no targets: explore everything reachable
    q = deque([src])
    while q and (full or left):
        cur = q.popleft()
        for nb in store.neighbours(cur):
            if nb not in dist:
                dist[nb] = dist[cur] + 1
                parent[nb] = cur
                left.discard(nb)
                q.append(nb)
    return dist, parent


def _path(store, a, b):
    """Cells walked from a to b, excluding a."""
    _, parent = _bfs(store, a, (b,))
    out, cur = [], b
    while cur != a:
        out.append(cur)
        cur = parent[cur]
    return out[::-1]


class Plan:
    def __init__(self, store, nodes, picks, seq, dist):
        self.store = store
        self.nodes = nodes  # nodes[0] is the entrance
        self.picks = picks  # items picked at each node
        self.seq = seq      # visit order, indexes into nodes
        self.dist = dist    # dist[i][j] in cells

    def kpis(self):
        cells = sum(self.dist[a][b] for a, b in zip(self.seq, self.seq[1:]))
        distance_m = cells * CELL_M
        seconds = distance_m / WALK_M_PER_S + PICK_S * sum(self.picks)
        return {"time_to_prepare_s": seconds, "distance_covered_m": distance_m}


def _nearest(dist):
    left, cur, order = set(range(1, len(dist))), 0, [0]
    while left:
        cur = min(left, key=lambda j: (dist[cur][j], j))
        left.remove(cur)
        order.append(cur)
    return order


def _two_opt(dist, order):
    # ponytail: nearest neighbour + 2-opt on the walk from the entrance; ceiling about 200 stops, not optimal.
    n, improved = len(order), True
    while improved:
        improved = False
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                a, b, c = order[i - 1], order[i], order[j]
                if j + 1 < n:
                    d = order[j + 1]
                    delta = dist[a][c] + dist[b][d] - dist[a][b] - dist[c][d]
                else:
                    delta = dist[a][c] - dist[a][b]
                if delta < -1e-9:
                    order[i:j + 1] = order[i:j + 1][::-1]
                    improved = True
    return order


def plan_route(store, ids, order="optimized"):
    if order not in ("optimized", "list"):
        raise RouteError(f"unknown order {order!r}")
    for pid in ids:
        if pid in store.broken:
            raise RouteError(f"basket product {pid} is broken in the store map: {store.broken[pid]}")
        if pid not in store.products:
            raise RouteError(f"unknown product id {pid!r} in basket")
    nodes, picks, index = [store.entrance], [0], {store.entrance: 0}
    for pid in ids:
        cell = store.products[pid][0]
        if cell not in index:
            index[cell] = len(nodes)
            nodes.append(cell)
            picks.append(0)
        picks[index[cell]] += 1
    reach, _ = _bfs(store, store.entrance)
    for pid in ids:
        if store.products[pid][0] not in reach:
            raise RouteError(f"product {pid} at {store.products[pid][0]} cannot be reached from the entrance")
    dist = []
    for a in nodes:
        reached = _bfs(store, a, nodes)[0]
        dist.append([reached[b] for b in nodes])
    if order == "list":
        seq = list(range(len(nodes)))
    else:
        seq = _two_opt(dist, _nearest(dist))
    return Plan(store, nodes, picks, seq, dist)


def simulate(plan):
    """Yield one Step per cell walked and per item picked, with running KPIs."""
    store, t, dist_m, picked = plan.store, 0.0, 0.0, 0
    yield Step("start", plan.nodes[plan.seq[0]], 0.0, 0.0, 0)
    for k, node in enumerate(plan.seq):
        if k > 0:
            for cell in _path(store, plan.nodes[plan.seq[k - 1]], plan.nodes[node]):
                dist_m += CELL_M
                t += CELL_M / WALK_M_PER_S
                yield Step("walk", cell, dist_m, t, picked)
        for _ in range(plan.picks[node]):
            picked += 1
            t += PICK_S
            yield Step("pick", plan.nodes[node], dist_m, t, picked)


def make_store(width, height, n_products, seed=0, shelves=True):
    """Generated store as the JSON map dict: border walls, shelf columns with cross aisles."""
    rng = random.Random(seed)
    grid = []
    for y in range(height):
        row = ""
        for x in range(width):
            border = x in (0, width - 1) or y in (0, height - 1)
            wall = border or (shelves and x % 3 == 0 and y % 8 != 4)
            row += "#" if wall else "."
        grid.append(row)
    entrance = {"x": 1, "y": height - 2}
    free = [(x, y) for y in range(height) for x in range(width)
            if grid[y][x] == "." and (x, y) != (entrance["x"], entrance["y"])]
    if not 0 < n_products <= len(free):
        raise RouteError(f"store has {len(free)} free cells, cannot place {n_products} products")
    cells = rng.sample(free, n_products)
    products = [{"id": f"P{i:04d}", "name": f"item{i}", "x": x, "y": y} for i, (x, y) in enumerate(cells)]
    return {"grid": grid, "entrance": entrance, "products": products}


def benchmark(width, height, n_products, n_items, baskets, seed=1):
    """Time saving of the optimized walk over the list-order walk, one value per random basket."""
    if not (0 < n_items <= n_products and baskets > 0):
        raise RouteError("need 0 < items <= products and baskets > 0")
    store = parse_store(make_store(width, height, n_products, seed))
    rng, ids, savings = random.Random(seed + 1), list(store.products), []
    for _ in range(baskets):
        basket = rng.sample(ids, n_items)  # the customer's list, in the order it was written
        base = plan_route(store, basket, "list").kpis()["time_to_prepare_s"]
        best = plan_route(store, basket, "optimized").kpis()["time_to_prepare_s"]
        savings.append(1 - best / base)
    return savings


def _load_pair(args):
    store = load_store(args.store)
    return store, load_basket(args.basket)


def cmd_run(args):
    store, ids = _load_pair(args)
    plan = plan_route(store, ids, args.order)
    print(f"route ({args.order}): {len(plan.seq)} stops, {len(ids)} items")
    last = None
    for s in simulate(plan):
        last = s
        print(f"{s.kind:5} cell={s.cell} time={s.seconds:8.1f}s distance={s.distance_m:7.1f}m picked={s.picked}")
        if args.delay:
            time.sleep(args.delay)
    print(f"time-to-prepare-basket: {last.seconds:.1f} s; distance-covered: {last.distance_m:.1f} m")
    return 0


def cmd_compare(args):
    store, ids = _load_pair(args)
    base = plan_route(store, ids, "list").kpis()
    best = plan_route(store, ids, "optimized").kpis()
    for name, k in (("list-order", base), ("optimized", best)):
        print(f"{name:10} time-to-prepare-basket={k['time_to_prepare_s']:.1f} s  "
              f"distance-covered={k['distance_covered_m']:.1f} m")
    saving = 100 * (1 - best["time_to_prepare_s"] / base["time_to_prepare_s"])
    print(f"time saved by optimized route: {saving:.1f} %")
    return 0


def cmd_benchmark(args):
    s = sorted(benchmark(args.width, args.height, args.products, args.items, args.baskets, args.seed))
    median = s[len(s) // 2]
    print(f"baskets={len(s)} min={100 * s[0]:.1f} % median={100 * median:.1f} % max={100 * s[-1]:.1f} %")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Supermarket picking route optimizer")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="simulate one route step by step")
    r.add_argument("store")
    r.add_argument("basket")
    r.add_argument("--order", choices=["list", "optimized"], default="optimized")
    r.add_argument("--delay", type=float, default=0.0, help="seconds to wait per step (real-time playback)")
    r.set_defaults(fn=cmd_run)
    c = sub.add_parser("compare", help="list-order versus optimized route")
    c.add_argument("store")
    c.add_argument("basket")
    c.set_defaults(fn=cmd_compare)
    b = sub.add_parser("benchmark", help="saving over random baskets on a generated store")
    b.add_argument("--width", type=int, default=200)
    b.add_argument("--height", type=int, default=200)
    b.add_argument("--products", type=int, default=400)
    b.add_argument("--items", type=int, default=25)
    b.add_argument("--baskets", type=int, default=50)
    b.add_argument("--seed", type=int, default=1)
    b.set_defaults(fn=cmd_benchmark)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except RouteError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
