"""Supermarket pick-route optimizer. Stdlib only.

Map JSON: {"grid": ["#..#", ...], "start": [row, col], "products": [{"id": "P1", "name": "milk", "pos": [row, col]}]}
Grid: '#' = shelf/wall (blocked), anything else walkable. Product pos must be a walkable cell (its pick face).
List file: lines "id:short name" (name optional). 1 cell = 1 m.
"""
import json, sys
from collections import deque

SPEED = 1.4  # m/s walking
PICK_S = 8.0  # seconds per item picked
# ponytail: constants are assumptions, same for optimized and baseline; pass --speed/--pick to tune.


def load_map(path):
    m = json.load(open(path))
    m["grid"] = [list(r) for r in m["grid"]]
    return m


def parse_list(text):
    out = []
    for ln in text.splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            out.append(ln.split(":", 1)[0].strip())
    return out


def bfs(grid, src):
    """Distances and parents from src over 4-neighbour walkable cells."""
    R, C = len(grid), len(grid[0])
    dist = {src: 0}
    par = {src: None}
    q = deque([src])
    while q:
        r, c = q.popleft()
        for n in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
            if 0 <= n[0] < R and 0 <= n[1] < C and grid[n[0]][n[1]] != "#" and n not in dist:
                dist[n] = dist[(r, c)] + 1
                par[n] = (r, c)
                q.append(n)
    return dist, par


def path_cells(par, dst):
    p = []
    while dst is not None:
        p.append(dst)
        dst = par[dst]
    return p[::-1]


class Store:
    def __init__(self, m):
        self.grid = m["grid"]
        if not self.grid or not self.grid[0] or len({len(r) for r in self.grid}) != 1:
            raise ValueError("grid must be non-empty and rectangular")
        self.start = tuple(m["start"])
        if not (0 <= self.start[0] < len(self.grid) and 0 <= self.start[1] < len(self.grid[0])):
            raise ValueError("start is outside the grid")
        self.pos = {p["id"]: tuple(p["pos"]) for p in m["products"]}
        self.name = {p["id"]: p.get("name", "") for p in m["products"]}
        if self.grid[self.start[0]][self.start[1]] == "#":
            raise ValueError("start is blocked")
        self._bfs = {}

    def bfs(self, cell):
        if cell not in self._bfs:
            self._bfs[cell] = bfs(self.grid, cell)
        return self._bfs[cell]

    def split(self, ids):
        """(routable ids, unknown ids, unreachable ids); duplicates dropped, order kept."""
        d, _ = self.bfs(self.start)
        ok, unk, unr, seen = [], [], [], set()
        for i in ids:
            if i in seen:
                continue
            seen.add(i)
            if i not in self.pos:
                unk.append(i)
            elif self.pos[i] not in d:
                unr.append(i)
            else:
                ok.append(i)
        return ok, unk, unr


def tour_len(order, D):
    return sum(D[order[i]][order[(i + 1) % len(order)]] for i in range(len(order)))


def optimize(store, ids):
    """Closed tour from start through all ids: nearest neighbour then 2-opt + or-opt on a distance matrix.
    Node 0 is the start. Returns ordered ids."""
    nodes = [store.start] + [store.pos[i] for i in ids]
    n = len(nodes)
    if n <= 2:
        return list(ids)
    D = [[store.bfs(a)[0][b] for b in nodes] for a in nodes]
    # nearest neighbour
    order, left = [0], set(range(1, n))
    while left:
        nxt = min(left, key=lambda j: D[order[-1]][j])
        order.append(nxt)
        left.remove(nxt)
    # 2-opt + or-opt until no gain. ponytail: O(n^2)/pass heuristic, no optimality proof; swap for Or-tools/LKH if n>>1000.
    improved = True
    while improved:
        improved = False
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                a, b = order[i - 1], order[i]
                c, d = order[j], order[(j + 1) % n]
                if D[a][c] + D[b][d] < D[a][b] + D[c][d]:
                    order[i:j + 1] = order[i:j + 1][::-1]
                    improved = True
        for seg in (1, 2, 3):
            i = 1
            while i + seg <= n:
                s = order[i:i + seg]
                rest = order[:i] + order[i + seg:]
                p, q = order[i - 1], order[(i + seg) % n]
                gain = D[p][s[0]] + D[s[-1]][q] - D[p][q]
                best, bk = 0, None
                for k in range(len(rest)):
                    x, y = rest[k], rest[(k + 1) % len(rest)]
                    for sg in (s, s[::-1]):
                        add = D[x][sg[0]] + D[sg[-1]][y] - D[x][y]
                        if gain - add > best:
                            best, bk = gain - add, (k, sg)
                if bk:
                    k, sg = bk
                    order = rest[:k + 1] + sg + rest[k + 1:]
                    improved = True
                i += 1
    return [ids[k - 1] for k in order[1:]]


def simulate(store, order, speed=SPEED, pick_s=PICK_S):
    """Yield one event per step: dict(kind, cell, dist, time, item). Ends back at start (checkout).
    kind: 'move' (1 cell), 'pick' (pick_s seconds), 'end'."""
    cur, dist, t = store.start, 0, 0.0
    yield dict(kind="start", cell=cur, dist=0, time=0.0, item=None)
    for it in list(order) + [None]:
        dst = store.start if it is None else store.pos[it]
        _, par = store.bfs(dst)
        for cell in path_cells(par, cur)[::-1][1:]:  # par rooted at dst: walk cur -> dst
            dist += 1
            t += 1 / speed
            cur = cell
            yield dict(kind="move", cell=cell, dist=dist, time=t, item=None)
        if it is not None:
            t += pick_s
            yield dict(kind="pick", cell=cur, dist=dist, time=t, item=it)
    yield dict(kind="end", cell=cur, dist=dist, time=t, item=None)


def kpis(store, order, **kw):
    ev = None
    for ev in simulate(store, order, **kw):
        pass
    return dict(distance_m=ev["dist"], time_s=round(ev["time"], 2))


def compare(store, ids, **kw):
    ok, unk, unr = store.split(ids)
    opt = optimize(store, ok)
    b, o = kpis(store, ok, **kw), kpis(store, opt, **kw)
    sav = 1 - o["time_s"] / b["time_s"] if b["time_s"] else 0.0
    dsav = 1 - o["distance_m"] / b["distance_m"] if b["distance_m"] else 0.0
    return dict(order=opt, baseline=b, optimized=o, time_saving=sav, distance_saving=dsav,
                unknown=unk, unreachable=unr)


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Supermarket pick-route optimizer")
    ap.add_argument("map")
    ap.add_argument("list", help="file of 'id:short name' lines")
    ap.add_argument("--trace", action="store_true", help="print every step with live KPIs")
    ap.add_argument("--speed", type=float, default=SPEED)
    ap.add_argument("--pick", type=float, default=PICK_S)
    a = ap.parse_args(argv)
    try:
        st = Store(load_map(a.map))
    except (ValueError, KeyError, TypeError) as e:
        print("bad map: %s" % e, file=sys.stderr)
        return 1
    ids = parse_list(open(a.list).read())
    r = compare(st, ids, speed=a.speed, pick_s=a.pick)
    for label, order in (("list-order", st.split(ids)[0]), ("optimized", r["order"])):
        if a.trace:
            for e in simulate(st, order, a.speed, a.pick):
                note = " pick %s %s" % (e["item"], st.name[e["item"]]) if e["item"] else ""
                print("[%s] %-5s %s distance-covered=%dm time-to-prepare-basket=%.1fs%s"
                      % (label, e["kind"], e["cell"], e["dist"], e["time"], note))
    print(json.dumps({k: r[k] for k in ("baseline", "optimized", "unknown", "unreachable")}))
    print("time saving %.1f%%  distance saving %.1f%%" % (100 * r["time_saving"], 100 * r["distance_saving"]))
    if r["unknown"] or r["unreachable"]:
        print("WARNING: skipped unknown=%s unreachable=%s" % (r["unknown"], r["unreachable"]), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
