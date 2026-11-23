"""Supermarket pick-route optimizer: grid map in, shortest pick route out, with a step simulation.

Map JSON: {"grid": ["#..", ...], "entrance": [row, col], "checkout": [row, col],
           "products": [{"id": "P1", "name": "milk", "row": 3, "col": 4}, ...],
           "cell_m": 1.0}      # '#' = wall or shelf, anything else = walkable floor
Shopping list: one "id:short name" (or just "id") per line; '#' starts a comment.
"""
import argparse
import json
import random
import sys
from collections import deque

WALK_MPS = 1.2   # walking speed, metres per second
EXACT_MAX = 10   # up to this many stops the order is optimal; above, 2-opt + or-opt heuristic
PICK_S = 5.0     # seconds to take one item from the shelf


class RouteError(Exception):
    """A user-facing input problem: printed as one line, exit code 2."""


def load_map(path):
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except OSError as e:
        raise RouteError(f"cannot read map {path}: {e.strerror or e}")
    except ValueError as e:
        raise RouteError(f"map {path} is not valid JSON: {e}")
    if not isinstance(raw, dict):
        raise RouteError("map must be a JSON object")
    grid = raw.get("grid")
    if (not isinstance(grid, list) or not grid
            or not all(isinstance(r, str) for r in grid)
            or not grid[0] or len({len(r) for r in grid}) != 1):
        raise RouteError("map 'grid' must be a non-empty list of equal-length strings")
    h, w = len(grid), len(grid[0])
    cell_m = raw.get("cell_m", 1.0)
    if isinstance(cell_m, bool) or not isinstance(cell_m, (int, float)) or cell_m <= 0:
        raise RouteError("map 'cell_m' must be a positive number")
    m = {"h": h, "w": w, "cell_m": float(cell_m),
         "walk": [c != "#" for row in grid for c in row]}
    for key in ("entrance", "checkout"):
        m[key] = _cell(raw.get(key), m, key)
        if not m["walk"][m[key]]:
            raise RouteError(f"map '{key}' is on a wall")
    products = raw.get("products")
    if not isinstance(products, list):
        raise RouteError("map 'products' must be a list")
    # ponytail: a broken product record is kept as an error string, so only a
    # request for it fails, never the whole map.
    m["products"] = {}
    for i, p in enumerate(products):
        pid, why, cell = None, None, None
        try:
            pid = str(p["id"])
            cell = _cell([p["row"], p["col"]], m, "product")
        except (KeyError, TypeError, RouteError) as e:
            why = f"bad record #{i}: {e}"
            pid = str(p.get("id")) if isinstance(p, dict) and "id" in p else None
        if pid is None:
            print(f"warning: skipped product record #{i}: {why}", file=sys.stderr)
            continue
        name = p.get("name", "") if isinstance(p, dict) else ""
        old = m["products"].get(pid)
        if why:
            m["products"][pid] = {"name": name, "error": why}
        elif old is None or ("error" not in old and old["cell"] == cell):
            m["products"][pid] = {"name": name, "cell": cell}
        else:
            m["products"][pid] = {"name": name, "error": "id appears twice at different places"}
    return m


def _cell(v, m, what):
    if (not isinstance(v, (list, tuple)) or len(v) != 2
            or any(isinstance(x, bool) or not isinstance(x, int) for x in v)):
        raise RouteError(f"map '{what}' must be [row, col]")
    r, c = v
    if not (0 <= r < m["h"] and 0 <= c < m["w"]):
        raise RouteError(f"map '{what}' {v} is outside the grid")
    return r * m["w"] + c


def load_list(path):
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as e:
        raise RouteError(f"cannot read list {path}: {e.strerror or e}")
    except UnicodeDecodeError:
        raise RouteError(f"list {path} is not text")
    ids = []
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if line:
            ids.append(line.split(":", 1)[0].strip())
    if not ids or "" in ids:
        raise RouteError("shopping list is empty or has a line without an id")
    return ids


def neighbours(m, i):
    w = m["w"]
    r, c = divmod(i, w)
    if r > 0:
        yield i - w
    if r < m["h"] - 1:
        yield i + w
    if c > 0:
        yield i - 1
    if c < w - 1:
        yield i + 1


def bfs(m, src, targets=None):
    """Steps from src to every walkable cell; stops early once all targets are seen."""
    dist = {src: 0}
    parent = {src: -1}
    left = set(targets or ())
    left.discard(src)
    q = deque([src])
    walk = m["walk"]
    while q and (targets is None or left):
        i = q.popleft()
        for j in neighbours(m, i):
            if walk[j] and j not in dist:
                dist[j] = dist[i] + 1
                parent[j] = i
                left.discard(j)
                q.append(j)
    return dist, parent


def access_cell(m, cell, reach):
    """Where the picker stands for a product: its own cell if walkable, else a reachable neighbour."""
    if m["walk"][cell]:
        return cell if cell in reach else None
    return next((j for j in neighbours(m, cell) if j in reach), None)


def plan(m, ids):
    """Return (stops, route): stops = access cells in visiting order; picks = ids per stop."""
    reach, _ = bfs(m, m["entrance"])
    if m["checkout"] not in reach:
        raise RouteError("checkout cannot be reached from the entrance")
    at = {}  # access cell -> list of ids
    for pid in ids:
        p = m["products"].get(pid)
        if p is None:
            raise RouteError(f"unknown product id: {pid}")
        if "error" in p:
            raise RouteError(f"product {pid} is broken in the map: {p['error']}")
        a = access_cell(m, p["cell"], reach)
        if a is None:
            raise RouteError(f"product {pid} cannot be reached from the entrance")
        at.setdefault(a, []).append(pid)
    nodes = [m["entrance"]] + list(at) + [m["checkout"]]
    D = {}
    for a in nodes[:-1]:
        d, _ = bfs(m, a, nodes)
        D[a] = d
    order = _best_order(list(at), m["entrance"], m["checkout"], D)
    return order, at


def _exact_order(mid, start, end, D):
    """Held-Karp: optimal order, for up to EXACT_MAX stops."""
    n = len(mid)
    best = {(1 << i, i): (D[start][mid[i]], None) for i in range(n)}
    for mask in range(1, 1 << n):
        for j in range(n):
            if (mask, j) not in best:
                continue
            for k in range(n):
                if not mask >> k & 1:
                    c = best[(mask, j)][0] + D[mid[j]][mid[k]]
                    key = (mask | 1 << k, k)
                    if key not in best or c < best[key][0]:
                        best[key] = (c, j)
    full = (1 << n) - 1
    j = min(range(n), key=lambda j: best[(full, j)][0] + D[mid[j]][end])
    out, mask = [], full
    while j is not None:
        out.append(mid[j])
        mask, j = mask ^ (1 << j), best[(mask, j)][1]
    return out[::-1]


def _best_order(mid, start, end, D):
    if not mid:
        return []
    if len(mid) <= EXACT_MAX:
        return _exact_order(mid, start, end, D)
    # nearest neighbour, then 2-opt and or-opt until nothing improves
    left, cur, path = set(mid), start, []
    while left:
        cur = min(left, key=lambda x: D[cur][x])
        path.append(cur)
        left.remove(cur)

    def cost(p):
        seq = [start] + p + [end]
        return sum(D[a][b] for a, b in zip(seq, seq[1:]))

    best, improved = cost(path), True
    while improved:
        improved = False
        n = len(path)
        cands = []
        for i in range(n):
            for j in range(i + 1, n):
                cands.append(path[:i] + path[i:j + 1][::-1] + path[j + 1:])      # 2-opt
        for i in range(n):
            for seg in (1, 2, 3):
                if i + seg > n:
                    break
                rest = path[:i] + path[i + seg:]
                for k in range(len(rest) + 1):
                    cands.append(rest[:k] + path[i:i + seg] + rest[k:])           # or-opt
        for c in cands:
            cc = cost(c)
            if cc < best:
                path, best, improved = c, cc, True
                break
    return path


def walk_path(m, a, b):
    _, parent = bfs(m, a, [b])
    p, i = [], b
    while i != a:
        p.append(i)
        i = parent[i]
    return p[::-1]


def simulate(m, visits):
    """Yield one event per step (move or pick); visits = [(cell, [ids])] in order."""
    cur, dist_m, t, picked = m["entrance"], 0.0, 0.0, []
    yield {"kind": "start", "cell": cur, "distance_m": 0.0, "time_s": 0.0, "picked": []}
    for target, pids in visits + [(m["checkout"], [])]:
        for c in walk_path(m, cur, target):
            dist_m += m["cell_m"]
            t += m["cell_m"] / WALK_MPS
            yield {"kind": "move", "cell": c, "distance_m": dist_m, "time_s": t, "picked": list(picked)}
        cur = target
        for pid in pids:
            t += PICK_S
            picked.append(pid)
            yield {"kind": "pick", "cell": cur, "id": pid, "distance_m": dist_m, "time_s": t,
                   "picked": list(picked)}
    yield {"kind": "done", "cell": cur, "distance_m": dist_m, "time_s": t, "picked": list(picked)}


def final(events):
    last = None
    for last in events:
        pass
    return last


def visits_for(m, ids):
    """(optimized visits, list-order visits)."""
    stops, at = plan(m, ids)
    reach, _ = bfs(m, m["entrance"])
    naive = [(access_cell(m, m["products"][i]["cell"], reach), [i]) for i in ids]
    return [(c, at[c]) for c in stops], naive


def compare(m, ids):
    """Final KPIs of the optimized and the list-order route, and the saving."""
    opt_v, naive_v = visits_for(m, ids)
    opt, naive = final(simulate(m, opt_v)), final(simulate(m, naive_v))
    return {"optimized": opt, "list_order": naive,
            "time_saving_pct": 100 * (1 - opt["time_s"] / naive["time_s"]),
            "distance_saving_pct": (100 * (1 - opt["distance_m"] / naive["distance_m"])
                                    if naive["distance_m"] else 0.0)}


# ---- store generator: several layout families, for demos and tests ----

def gen_store(kind, seed, h, w, n_products):
    rnd = random.Random(seed)
    g = [["." for _ in range(w)] for _ in range(h)]
    if kind == "aisles":
        for r in range(2, h - 2):
            if r % 3 != 0:
                for c in range(2, w - 2):
                    g[r][c] = "#"
        for c in range(8, w - 2, 15):           # cross aisles
            for r in range(h):
                g[r][c] = "."
    elif kind == "islands":
        for _ in range(h * w // 40):
            r, c = rnd.randrange(2, h - 3), rnd.randrange(2, w - 8)
            for rr in range(r, min(r + rnd.randint(1, 3), h - 2)):
                for cc in range(c, c + rnd.randint(2, 6)):
                    g[rr][cc] = "#"
    elif kind == "open":
        for _ in range(h * w // 8):
            g[rnd.randrange(1, h - 1)][rnd.randrange(1, w - 1)] = "#"
    elif kind == "maze":
        h, w = h | 1, w | 1
        g = [["#"] * w for _ in range(h)]
        stack, g[1][1] = [(1, 1)], "."
        while stack:
            r, c = stack[-1]
            nxt = [(r + dr, c + dc, dr, dc) for dr, dc in ((2, 0), (-2, 0), (0, 2), (0, -2))
                   if 0 < r + dr < h - 1 and 0 < c + dc < w - 1 and g[r + dr][c + dc] == "#"]
            if not nxt:
                stack.pop()
                continue
            nr, nc, dr, dc = rnd.choice(nxt)
            g[r + dr // 2][c + dc // 2] = g[nr][nc] = "."
            stack.append((nr, nc))
    else:
        raise RouteError(f"unknown store kind: {kind}")
    if kind == "maze":
        ent, chk = [h - 2, 1], [h - 2, w - 2]
    else:
        ent, chk = [h - 1, 1], [h - 1, w - 2]
    spots = [(r, c) for r in range(h) for c in range(w)
             if (kind == "maze" and g[r][c] == ".") or
             (kind != "maze" and g[r][c] == "#" and any(
                 0 <= r + dr < h and 0 <= c + dc < w and g[r + dr][c + dc] == "."
                 for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))))]
    spots = rnd.sample(spots, min(n_products, len(spots)))
    return {"grid": ["".join(r) for r in g], "entrance": ent, "checkout": chk, "cell_m": 1.0,
            "products": [{"id": f"P{i}", "name": f"item{i}", "row": r, "col": c}
                         for i, (r, c) in enumerate(spots)]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="optimize and simulate")
    r.add_argument("map")
    r.add_argument("list")
    r.add_argument("--steps", action="store_true", help="print every move, not just picks")
    r.add_argument("--json", action="store_true", help="print the comparison as JSON only")
    g = sub.add_parser("gen", help="write a demo map and shopping list")
    g.add_argument("kind", choices=["aisles", "islands", "open", "maze"])
    g.add_argument("--seed", type=int, default=1)
    g.add_argument("--size", type=int, nargs=2, default=[40, 60], metavar=("H", "W"))
    g.add_argument("--products", type=int, default=200)
    g.add_argument("--items", type=int, default=15)
    g.add_argument("--out", default="store")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "gen":
            s = gen_store(a.kind, a.seed, *a.size, a.products)
            ids = random.Random(a.seed).sample([p["id"] for p in s["products"]], a.items)
            with open(a.out + ".json", "w") as f:
                json.dump(s, f)
            with open(a.out + ".txt", "w") as f:
                f.write("".join(f"{i}:{next(p['name'] for p in s['products'] if p['id'] == i)}\n"
                                for i in ids))
            print(f"wrote {a.out}.json and {a.out}.txt")
            return 0
        m, ids = load_map(a.map), load_list(a.list)
        res = compare(m, ids)
        if a.json:
            print(json.dumps({k: (v if not isinstance(v, dict) else
                                  {x: v[x] for x in ("distance_m", "time_s")})
                              for k, v in res.items()}))
            return 0
        for e in simulate(m, visits_for(m, ids)[0]):
            if e["kind"] == "move" and not a.steps:
                continue
            r_, c_ = divmod(e["cell"], m["w"])
            what = f"pick {e['id']}" if e["kind"] == "pick" else e["kind"]
            print(f"t={e['time_s']:8.1f}s  dist={e['distance_m']:8.1f}m  at=({r_},{c_})  "
                  f"{what}  items={len(e['picked'])}/{len(ids)}")
        o, n = res["optimized"], res["list_order"]
        print(f"optimized : time-to-prepare-basket {o['time_s']:.1f}s  distance-covered {o['distance_m']:.1f}m")
        print(f"list order: time-to-prepare-basket {n['time_s']:.1f}s  distance-covered {n['distance_m']:.1f}m")
        print(f"saving    : time {res['time_saving_pct']:.1f}%  distance {res['distance_saving_pct']:.1f}%")
        return 0
    except RouteError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"error: {e.strerror or e}: {e.filename}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
