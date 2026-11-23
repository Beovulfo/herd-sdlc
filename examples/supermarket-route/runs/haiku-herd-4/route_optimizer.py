"""Supermarket picking route optimizer. Python standard library only.

Map: a grid of rows, '#' for shelves and walls, '.' for floor. One cell is one metre.
Each product sits on a floor cell the picker can reach. Distances are walking steps
found by breadth-first search, so any layout works. Run: python3 -m route_optimizer MAP BASKET [--steps]
"""
import json
import sys
from collections import deque
from dataclasses import dataclass

WALK_M_PER_S = 1.2  # ponytail: fixed walking speed, add a per-store setting when a store needs one
PICK_S = 8.0        # ponytail: fixed seconds per pick, the same for every product


class PlanError(ValueError):
    pass


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    cell: tuple


@dataclass
class Frame:
    step: int
    x: int
    y: int
    distance: int
    picked: int
    picked_id: str
    time_s: float


@dataclass(frozen=True)
class Route:
    stops: tuple
    distance: int

    def time_s(self):
        return self.distance / WALK_M_PER_S + len(self.stops) * PICK_S


class Store:
    def __init__(self, grid, start, products):
        self.grid = grid
        self.start = start
        self.products = products
        self.width = len(grid[0])
        self.height = len(grid)

    @classmethod
    def from_dict(cls, data):
        try:
            grid = [str(row) for row in data["grid"]]
            start = tuple(int(v) for v in data["start"])
            entries = data["products"]
            if not isinstance(entries, list):
                raise TypeError("products must be a list")
        except (KeyError, TypeError, ValueError) as e:
            raise PlanError(f"map is missing a field or has a wrong type: {e}") from e
        if not grid or any(len(row) != len(grid[0]) for row in grid):
            raise PlanError("grid must be non-empty rows of equal length")
        if any(ch not in "#." for row in grid for ch in row):
            raise PlanError("grid may only contain '#' and '.'")
        store = cls(grid, start, {})
        if not store.is_open(store.start):
            raise PlanError(f"start {store.start} is not a floor cell")
        for p in entries:
            try:
                pid, name, cell = str(p["id"]), str(p["name"]), (int(p["x"]), int(p["y"]))
            except (KeyError, TypeError, ValueError) as e:
                raise PlanError(f"product entry needs id, name, x and y: {p!r}") from e
            if not store.is_open(cell):
                raise PlanError(f"product {pid!r} is not on a floor cell")
            if pid in store.products:
                raise PlanError(f"duplicate product id {pid!r} on the map")
            store.products[pid] = Product(pid, name, cell)
        return store

    def is_open(self, cell):
        x, y = cell
        return 0 <= x < self.width and 0 <= y < self.height and self.grid[y][x] == "."


def parse_basket(lines):
    """Lines like 'P001:milk' give ['P001']. Blank lines are skipped."""
    return [line.split(":", 1)[0].strip() for line in lines if line.strip()]


def _bfs(store, src):
    """Walking distance and parent index for every cell from src. -1 means unreachable."""
    w, h, grid = store.width, store.height, store.grid
    dist = [-1] * (w * h)
    parent = [-1] * (w * h)
    s = src[1] * w + src[0]
    dist[s] = 0
    queue = deque([s])
    while queue:
        c = queue.popleft()
        y, x = divmod(c, w)
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and grid[ny][nx] == "." and dist[ny * w + nx] < 0:
                n = ny * w + nx
                dist[n] = dist[c] + 1
                parent[n] = c
                queue.append(n)
    return dist, parent


def _matrix(store, ids):
    """Distance matrix over nodes: 0 is the start, node k is ids[k-1]."""
    if len(set(ids)) != len(ids):
        raise PlanError("the list names a product twice")
    for pid in ids:
        if pid not in store.products:
            raise PlanError(f"product id {pid!r} is not on the map")
    if not ids:
        return [[0]]
    w = store.width
    nodes = [store.start] + [store.products[pid].cell for pid in ids]
    rows = []
    for src in nodes:
        dist, _ = _bfs(store, src)
        rows.append([dist[y * w + x] for x, y in nodes])
    for k, pid in enumerate(ids):
        if rows[0][k + 1] < 0:
            raise PlanError(f"product {pid!r} cannot be reached from the start")
    return rows


def _length(matrix, seq):
    return sum(matrix[a][b] for a, b in zip(seq, seq[1:]))


def _list_route(ids, matrix):
    return Route(tuple(ids), _length(matrix, range(len(ids) + 1)))


def _optimized_route(ids, matrix):
    n = len(ids)
    left = set(range(1, n + 1))
    seq = [0]
    while left:
        cur = seq[-1]
        nxt = min(left, key=lambda j: (matrix[cur][j], j))
        seq.append(nxt)
        left.remove(nxt)
    improved = True
    while improved:  # 2-opt on the open path: start stays first, end is free
        improved = False
        for i in range(1, n):
            for j in range(i + 1, n + 1):
                a, b, c = seq[i - 1], seq[i], seq[j]
                d = seq[j + 1] if j + 1 <= n else None
                old = matrix[a][b] + (matrix[c][d] if d is not None else 0)
                new = matrix[a][c] + (matrix[b][d] if d is not None else 0)
                if new < old:
                    seq[i:j + 1] = seq[i:j + 1][::-1]
                    improved = True
    return Route(tuple(ids[k - 1] for k in seq[1:]), _length(matrix, seq))


def plan_list_order(store, ids):
    return _list_route(list(ids), _matrix(store, list(ids)))


def plan_optimized(store, ids):
    return _optimized_route(list(ids), _matrix(store, list(ids)))


def _kpi(route):
    return {"time_s": route.time_s(), "distance_m": route.distance}


def compare(store, ids):
    ids = list(ids)
    matrix = _matrix(store, ids)
    lst = _kpi(_list_route(ids, matrix))
    opt = _kpi(_optimized_route(ids, matrix))
    saving = (lst["time_s"] - opt["time_s"]) / lst["time_s"] * 100 if lst["time_s"] else 0.0
    return {"list": lst, "optimized": opt, "saving_pct": saving}


def simulate(store, route):
    """Yield a Frame per walked cell and per pick, in walking order, with live KPIs."""
    w = store.width
    cur = store.start
    distance = picked = step = 0
    for pid in route.stops:
        target = store.products[pid].cell
        _, parent = _bfs(store, cur)
        path = []
        idx = target[1] * w + target[0]
        src = cur[1] * w + cur[0]
        while idx != src:
            path.append(idx)
            idx = parent[idx]
        for idx in reversed(path):
            cur = (idx % w, idx // w)
            distance += 1
            step += 1
            yield Frame(step, cur[0], cur[1], distance, picked, None, distance / WALK_M_PER_S + picked * PICK_S)
        picked += 1
        step += 1
        yield Frame(step, cur[0], cur[1], distance, picked, pid, distance / WALK_M_PER_S + picked * PICK_S)


def main(argv):
    if len(argv) not in (3, 4) or (len(argv) == 4 and argv[3] != "--steps"):
        print("usage: python3 -m route_optimizer MAP.json BASKET.txt [--steps]", file=sys.stderr)
        return 2
    try:
        with open(argv[1]) as f:
            store = Store.from_dict(json.load(f))
        with open(argv[2]) as f:
            ids = parse_basket(f)
        result = compare(store, ids)
    except OSError as e:
        print(f"error: cannot read file: {e}", file=sys.stderr)
        return 1
    except ValueError as e:  # bad JSON and PlanError both land here
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"items: {len(ids)}")
    for name in ("list", "optimized"):
        print(f"{name:>10}: time-to-prepare-basket {result[name]['time_s']:.1f} s, "
              f"distance-covered {result[name]['distance_m']} m")
    print(f"saving: {result['saving_pct']:.1f} %")
    if len(argv) == 4:
        route = plan_optimized(store, ids)
        for f in simulate(store, route):
            if f.picked_id:
                print(f"step {f.step:4d} picked {f.picked_id} at ({f.x},{f.y}) "
                      f"distance {f.distance} m time {f.time_s:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
