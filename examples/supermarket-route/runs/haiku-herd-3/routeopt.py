"""routeopt: picking-route optimizer for a supermarket. Standard library only.

Map (JSON): {"rows": ["#######", "#E....#", ...], "products": [{"id": "P1", "name": "milk", "cell": [1, 2]}]}
  '#' is a wall, '.' a free cell, 'E' the entrance (exactly one). A product's cell is the free
  cell the picker stands on to take it (the access cell in front of the shelf).
List (text): one "id:short name" per line. Blank lines and lines starting with '#' are ignored.

Route: starts at the entrance, takes every listed item once, ends at the last pick (basket ready).
Time model: seconds per step (one cell) plus seconds per pick. Distance is counted in cells.
"""

import argparse
import collections
import json
import random
import sys
import time

WALL = "#"
STEP_S = 1.0  # one cell is about one metre; a model, not a measurement
PICK_S = 5.0  # seconds to find and take one item
FAMILIES = ("open", "aisles", "random", "split")


class RouteError(Exception):
    pass


Store = collections.namedtuple("Store", "rows entrance products bad")
Product = collections.namedtuple("Product", "name cell")


def parse_map(data):
    if not isinstance(data, dict):
        raise RouteError("map must be a JSON object with 'rows' and 'products'")
    rows = data.get("rows")
    if not isinstance(rows, list) or not rows or not all(isinstance(r, str) for r in rows):
        raise RouteError("map 'rows' must be a non-empty list of strings")
    width = len(rows[0])
    if width == 0 or any(len(r) != width for r in rows):
        raise RouteError("map rows must all have the same non-zero length")
    entrances = []
    for r, line in enumerate(rows):
        for c, ch in enumerate(line):
            if ch == "E":
                entrances.append((r, c))
            elif ch not in ".#":
                raise RouteError(f"map row {r} has unknown character {ch!r} at column {c}")
    if len(entrances) != 1:
        raise RouteError(f"map must have exactly one entrance 'E', found {len(entrances)}")
    raw = data.get("products", [])
    if not isinstance(raw, list):
        raise RouteError("map 'products' must be a list")
    products, bad = {}, {}
    for i, p in enumerate(raw):
        pid = p.get("id") if isinstance(p, dict) else None
        key = pid if isinstance(pid, str) and pid else f"#{i}"
        if key in products or key in bad:  # ambiguous id: unusable if requested
            products.pop(key, None)
            bad[key] = "listed more than once on the map"
            continue
        problem = _product_problem(p, rows, width)
        if problem:
            bad[key] = problem
        else:
            products[key] = Product(p["name"], tuple(p["cell"]))
    return Store(rows, entrances[0], products, bad)


def _product_problem(p, rows, width):
    if not isinstance(p, dict):
        return "entry is not an object"
    if not isinstance(p.get("id"), str) or not p["id"]:
        return "id must be a non-empty string"
    if not isinstance(p.get("name"), str):
        return "name must be a string"
    cell = p.get("cell")
    if not (isinstance(cell, list) and len(cell) == 2 and all(type(x) is int for x in cell)):
        return "cell must be [row, col]"
    r, c = cell
    if not (0 <= r < len(rows) and 0 <= c < width):
        return f"cell {cell} is outside the map"
    if rows[r][c] == WALL:
        return f"cell {cell} is a wall"
    return None


def load_map(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise RouteError(f"cannot read map {path}: {e.strerror}")
    except UnicodeDecodeError:
        raise RouteError(f"map {path} is not UTF-8 text")
    except json.JSONDecodeError as e:
        raise RouteError(f"map {path} is not valid JSON (line {e.lineno})")
    return parse_map(data)


def load_list(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        raise RouteError(f"cannot read list {path}: {e.strerror}")
    except UnicodeDecodeError:
        raise RouteError(f"list {path} is not UTF-8 text")
    ids = []
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pid, sep, _ = line.partition(":")
        if not sep or not pid.strip():
            raise RouteError(f"list {path} line {n}: expected 'id:short name', got {line!r}")
        ids.append(pid.strip())
    if not ids:
        raise RouteError(f"list {path} has no products")
    return ids


def bfs(rows, src, targets=None):
    """Breadth-first search over flat cell indices. With targets, stops once every target is reached."""
    width = len(rows[0])
    dist = [-1] * (len(rows) * width)
    parent = [-1] * len(dist)
    start = src[0] * width + src[1]
    dist[start] = 0
    remaining = None if targets is None else {t[0] * width + t[1] for t in targets}
    if remaining is not None:
        remaining.discard(start)
    queue = collections.deque([start])
    while queue and remaining != set():
        cur = queue.popleft()
        r, c = divmod(cur, width)
        for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if 0 <= nr < len(rows) and 0 <= nc < width:
                nxt = nr * width + nc
                if dist[nxt] < 0 and rows[nr][nc] != WALL:
                    dist[nxt] = dist[cur] + 1
                    parent[nxt] = cur
                    queue.append(nxt)
                    if remaining is not None:
                        remaining.discard(nxt)
    return dist, parent


def path(rows, src, dst):
    dist, parent = bfs(rows, src, (dst,))
    width = len(rows[0])
    cur, start = dst[0] * width + dst[1], src[0] * width + src[1]
    if dist[cur] < 0:
        raise RouteError(f"cell {list(dst)} cannot be reached from {list(src)}")
    cells = []
    while cur != start:
        cells.append(divmod(cur, width))
        cur = parent[cur]
    cells.append(src)
    cells.reverse()
    return cells


def basket(store, ids):
    stops = []
    for pid in ids:
        if pid in store.bad:
            raise RouteError(f"requested product {pid} is unusable on the map: {store.bad[pid]}")
        if pid not in store.products:
            raise RouteError(f"requested product {pid} is not on the map")
        stops.append((pid, store.products[pid].cell))
    return stops


def leg_matrix(rows, cells):
    """Step distances between every pair of cells; -1 when unreachable. cells[0] is the entrance."""
    width = len(rows[0])
    targets = [(c[0], c[1]) for c in cells]
    dm = []
    for src in cells:
        dist, _ = bfs(rows, src, targets)
        dm.append([dist[t[0] * width + t[1]] for t in targets])
    return dm


def route_length(dm, order):
    total, prev = 0, 0
    for k in order:
        total += dm[prev][k]
        prev = k
    return total


def nearest_neighbour(dm):
    left = set(range(1, len(dm)))
    order, cur = [], 0
    while left:
        cur = min(left, key=lambda k: (dm[cur][k], k))
        order.append(cur)
        left.remove(cur)
    return order


def two_opt(dm, order):
    """Reverse segments while that shortens the open path from the entrance. Strictly shrinking, so it ends."""
    order = list(order)
    n = len(order)
    improved = True
    while improved:
        improved = False
        for i in range(n - 1):
            for j in range(i + 1, n):
                a = order[i - 1] if i else 0
                b, c = order[i], order[j]
                nxt = order[j + 1] if j + 1 < n else None
                old = dm[a][b] + (dm[c][nxt] if nxt is not None else 0)
                new = dm[a][c] + (dm[b][nxt] if nxt is not None else 0)
                if new < old:
                    order[i:j + 1] = order[i:j + 1][::-1]
                    improved = True
    return order


def optimize(dm):
    """Best of the customer's list order and nearest-neighbour, each improved by 2-opt."""
    n = len(dm) - 1
    candidates = [list(range(1, n + 1)), nearest_neighbour(dm)]
    return min((two_opt(dm, o) for o in candidates), key=lambda o: route_length(dm, o))


def solve(store, ids):
    """Return (list_order_stops, optimized_stops) as lists of (product id, cell)."""
    stops = basket(store, ids)
    cells = [store.entrance] + [cell for _, cell in stops]
    dm = leg_matrix(store.rows, cells)
    for k in range(1, len(cells)):
        if dm[0][k] < 0:
            raise RouteError(f"requested product {stops[k - 1][0]} at {list(cells[k])} cannot be reached from the entrance")
    return stops, [stops[k - 1] for k in optimize(dm)]


def simulate(store, stops, step_s=STEP_S, pick_s=PICK_S):
    """Walk the route. Yields one event per step and per pick, with running KPIs."""
    cur, distance, elapsed, picked = store.entrance, 0, 0.0, 0
    for pid, cell in stops:
        for step in path(store.rows, cur, cell)[1:]:
            distance += 1
            elapsed += step_s
            yield {"event": "step", "cell": step, "distance": distance, "time_s": elapsed, "picked": picked}
        elapsed += pick_s
        picked += 1
        yield {"event": "pick", "item": pid, "cell": cell, "distance": distance, "time_s": elapsed, "picked": picked}
        cur = cell


def kpis(events):
    last = None
    for last in events:
        pass
    return {"time_to_prepare_basket_s": last["time_s"], "distance_covered": last["distance"], "picks": last["picked"]}


def compare(store, ids, step_s=STEP_S, pick_s=PICK_S):
    list_stops, best = solve(store, ids)
    a = kpis(simulate(store, list_stops, step_s, pick_s))
    b = kpis(simulate(store, best, step_s, pick_s))

    def saving(x, y):
        return 100.0 * (x - y) / x if x else 0.0

    return {
        "list-order": a,
        "optimized": b,
        "time_saving_pct": saving(a["time_to_prepare_basket_s"], b["time_to_prepare_basket_s"]),
        "distance_saving_pct": saving(a["distance_covered"], b["distance_covered"]),
    }


def make_store(seed, family, width, height, n_products, list_size):
    """Generate a store map and a customer list (ids in customer order). Used by tests and the bench."""
    if family not in FAMILIES:
        raise RouteError(f"unknown layout family {family!r}; use one of {', '.join(FAMILIES)}")
    if width < 4 or height < 4:
        raise RouteError("store must be at least 4x4")
    if n_products < 1 or list_size < 1:
        raise RouteError("need at least one product and one list item")
    rng = random.Random(seed)
    grid = [["."] * width for _ in range(height)]
    if family == "aisles":  # shelving runs with one random gap each
        for c in range(2, width - 1, 3):
            gap = rng.randrange(1, height - 1)
            for r in range(1, height - 1):
                grid[r][c] = "." if r == gap else WALL
    elif family == "random":
        for r in range(height - 1):
            for c in range(width):
                if rng.random() < 0.25:
                    grid[r][c] = WALL
    elif family == "split":  # a full wall: the far side cannot be reached
        for r in range(height):
            grid[r][width // 2] = WALL
    grid[height - 1][0] = "E"
    rows = ["".join(r) for r in grid]
    entrance = (height - 1, 0)
    free = [(r, c) for r in range(height) for c in range(width) if grid[r][c] != WALL]
    cells = [rng.choice(free) for _ in range(n_products)]
    products = [{"id": f"P{i:04d}", "name": f"item-{i:04d}", "cell": list(cell)} for i, cell in enumerate(cells)]
    products[0]["cell"] = list(entrance)  # guarantees one reachable product
    dist, _ = bfs(rows, entrance)
    reachable = [p["id"] for p in products if dist[p["cell"][0] * width + p["cell"][1]] >= 0]
    if list_size <= len(reachable):
        ids = rng.sample(reachable, list_size)
    else:
        ids = rng.choices(reachable, k=list_size)
    return {"rows": rows, "products": products}, ids


def warn_skipped(store, ids):
    requested = set(ids)
    for pid, reason in store.bad.items():
        if pid not in requested:
            print(f"routeopt: warning: skipped map entry {pid}: {reason}", file=sys.stderr)


def _print_compare(res):
    a, b = res["list-order"], res["optimized"]
    print(f"{'route':<12} {'picks':>5} {'distance':>9} {'time_s':>10}")
    for name, k in (("list-order", a), ("optimized", b)):
        print(f"{name:<12} {k['picks']:>5} {k['distance_covered']:>9} {k['time_to_prepare_basket_s']:>10.2f}")
    print(f"time-to-prepare-basket saving: {res['time_saving_pct']:.1f}%   "
          f"distance-covered saving: {res['distance_saving_pct']:.1f}%")


def cmd_simulate(args, store, ids):
    list_stops, best = solve(store, ids)
    stops = list_stops if args.strategy == "list-order" else best
    total = len(stops)
    print(f"strategy: {args.strategy}  picks: {total}")
    for e in simulate(store, stops, args.step_s, args.pick_s):
        cell = f"({e['cell'][0]},{e['cell'][1]})"
        if e["event"] == "step":
            print(f"  step t={e['time_s']:9.2f}s dist={e['distance']:6d} picked={e['picked']}/{total} -> {cell}", flush=True)
            if args.tick:
                time.sleep(args.tick)
        else:
            print(f"  PICK t={e['time_s']:9.2f}s dist={e['distance']:6d} picked={e['picked']}/{total} {e['item']} at {cell}", flush=True)
    k = kpis(simulate(store, stops, args.step_s, args.pick_s))
    print(f"time-to-prepare-basket: {k['time_to_prepare_basket_s']:.2f} s")
    print(f"distance-covered: {k['distance_covered']} cells")
    return 0


def cmd_bench(args):
    if args.seeds < 1:
        raise RouteError("--seeds must be at least 1")
    savings = []
    for seed in range(args.seeds):
        m, ids = make_store(seed, "aisles", 60, 40, 400, 30)
        res = compare(parse_map(m), ids)
        savings.append(res["time_saving_pct"])
        print(f"seed {seed:2d}: time saving {res['time_saving_pct']:5.1f}%  distance saving {res['distance_saving_pct']:5.1f}%")
    mean = sum(savings) / len(savings)
    print(f"time-to-prepare-basket saving over {len(savings)} stores: mean {mean:.1f}%  "
          f"min {min(savings):.1f}%  max {max(savings):.1f}%")
    if mean <= args.min_saving:
        print(f"FAIL: mean saving {mean:.1f}% is not above {args.min_saving:g}%", file=sys.stderr)
        return 1
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="routeopt", description="Picking-route optimizer for a supermarket.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("compare", "simulate"):
        s = sub.add_parser(name, help=("compare the list-order and optimized routes" if name == "compare"
                                       else "step through a route with live KPIs"))
        s.add_argument("map")
        s.add_argument("list")
        s.add_argument("--step-s", type=float, default=STEP_S)
        s.add_argument("--pick-s", type=float, default=PICK_S)
        if name == "simulate":
            s.add_argument("--strategy", choices=["optimized", "list-order"], default="optimized")
            s.add_argument("--tick", type=float, default=0.0, help="sleep seconds after each step")
    b = sub.add_parser("bench", help="benchmark the time saving on generated aisle stores")
    b.add_argument("--seeds", type=int, default=20)
    b.add_argument("--min-saving", type=float, default=30.0)
    g = sub.add_parser("gen", help="write a generated store map and customer list")
    g.add_argument("family", choices=FAMILIES)
    g.add_argument("--seed", type=int, default=1)
    g.add_argument("--width", type=int, default=60)
    g.add_argument("--height", type=int, default=40)
    g.add_argument("--products", type=int, default=400)
    g.add_argument("--list-size", type=int, default=30)
    g.add_argument("--map-out", required=True)
    g.add_argument("--list-out", required=True)
    args = p.parse_args(argv)
    try:
        if args.cmd == "bench":
            return cmd_bench(args)
        if args.cmd == "gen":
            m, ids = make_store(args.seed, args.family, args.width, args.height, args.products, args.list_size)
            with open(args.map_out, "w", encoding="utf-8") as f:
                json.dump(m, f)
            with open(args.list_out, "w", encoding="utf-8") as f:
                f.writelines(f"{pid}:{m['products'][int(pid[1:])]['name']}\n" for pid in ids)
            print(f"wrote {args.map_out} and {args.list_out} ({len(ids)} items)")
            return 0
        if args.step_s < 0 or args.pick_s < 0 or getattr(args, "tick", 0.0) < 0:
            raise RouteError("step, pick and tick times must be zero or more")
        store = load_map(args.map)
        ids = load_list(args.list)
        warn_skipped(store, ids)
        if args.cmd == "simulate":
            return cmd_simulate(args, store, ids)
        _print_compare(compare(store, ids, args.step_s, args.pick_s))
        return 0
    except RouteError as e:
        print(f"routeopt: error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
