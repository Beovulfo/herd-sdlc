#!/usr/bin/env python3
"""Hidden general acceptance check for the route-optimizer task ("any supermarket, even very big").

It never reads the agent's code for correctness. It generates stores from eight layout families at
several scales (seeds the agent has not seen), asks the solution (through a small adapter) for its
optimized and list-order routes as cell-by-cell traces, validates every trace itself, and reports:
validity, completion within a time limit, time saved against the solution's own list-order route,
the gap to the exact optimum (small stores) and to a 1-tree lower bound (mid-size stores).

Usage:
  verify_general.py ADAPTER PROJECT_DIR [--tiers S,M,L] [--seeds 2] [--families a,b] [--limit-scale 1.0]
Adapters: with_herd, without_herd, reference. Add one function `worker_<name>(project, canon, out_path)` per solution.
Standard library only.
"""
import argparse
import itertools
import json
import math
import random
import statistics
import subprocess
import sys
import tempfile
import time
from collections import deque
from pathlib import Path

TIERS = {  # name: (width, height, items, seconds allowed per route, seeds per family)
    "S": (60, 40, 7, 30),
    "M": (160, 100, 40, 90),
    "L": (400, 300, 100, 180),
    "XL": (600, 400, 200, 300),
}
SPEED_DEFAULT = 1.2
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


# ---- store generators (grid of '#' blocked and '.' free) -------------------------------------

def blank(w, h):
    g = [["#"] * w for _ in range(h)]
    for r in range(1, h - 1):
        for c in range(1, w - 1):
            g[r][c] = "."
    return g


def fam_parallel(w, h, rnd):  # classic horizontal shelf rows with cross aisles
    g = blank(w, h)
    for r in range(3, h - 3):
        if r % 5 in (0, 1):
            for c in range(3, w - 3):
                if c % 30 != 0:
                    g[r][c] = "#"
    return g


def fam_vertical(w, h, rnd):  # vertical shelf columns, perimeter ring free
    g = blank(w, h)
    for c in range(3, w - 3):
        if c % 4 in (1, 2):
            for r in range(3, h - 3):
                if r % 25 not in (0, 1):
                    g[r][c] = "#"
    return g


def fam_islands(w, h, rnd):  # open hall with random rectangular fixtures
    g = blank(w, h)
    for _ in range(max(4, w * h // 300)):
        r, c, rh, cw = rnd.randrange(2, h - 3), rnd.randrange(2, w - 3), rnd.randint(1, 5), rnd.randint(2, 12)
        for rr in range(r, min(h - 1, r + rh)):
            for cc in range(c, min(w - 1, c + cw)):
                g[rr][cc] = "#"
    return g


def fam_random(w, h, rnd):  # scattered obstacles, about a quarter blocked
    g = blank(w, h)
    for r in range(1, h - 1):
        for c in range(1, w - 1):
            if rnd.random() < 0.25:
                g[r][c] = "#"
    return g


def fam_comb(w, h, rnd):  # a main corridor with long dead-end aisles
    g = [["#"] * w for _ in range(h)]
    for c in range(1, w - 1):
        g[h - 2][c] = "."
    for c in range(2, w - 2, 3):
        for r in range(2, h - 2):
            g[r][c] = "."
    return g


def fam_lshape(w, h, rnd):  # non-rectangular: parallel aisles with a quarter of the hall missing
    g = fam_parallel(w, h, rnd)
    for r in range(1, h // 2):
        for c in range(w // 2, w - 1):
            g[r][c] = "#"
    return g


def fam_maze(w, h, rnd):  # one-wide winding corridors (spanning tree on a coarse grid)
    g = [["#"] * w for _ in range(h)]
    cw, ch = (w - 1) // 2, (h - 1) // 2
    seen, stack = {(0, ch - 1)}, [(0, ch - 1)]
    g[2 * (ch - 1) + 1][1] = "."
    while stack:
        x, y = stack[-1]
        nbrs = [(x + dx, y + dy) for dx, dy in DIRS if 0 <= x + dx < cw and 0 <= y + dy < ch and (x + dx, y + dy) not in seen]
        if not nbrs:
            stack.pop()
            continue
        nx, ny = rnd.choice(nbrs)
        seen.add((nx, ny))
        g[2 * ny + 1][2 * nx + 1] = "."
        g[y + ny + 1][x + nx + 1] = "."
        stack.append((nx, ny))
    return g


def fam_clusters(w, h, rnd):  # departments: rooms joined by doors, shelves inside
    g = [["#"] * w for _ in range(h)]
    rooms = [(r, c) for r in range(1, h - 6, 14) for c in range(1, w - 6, 20)]
    for r0, c0 in rooms:
        for r in range(r0, min(h - 1, r0 + 12)):
            for c in range(c0, min(w - 1, c0 + 18)):
                g[r][c] = "." if (r - r0) % 4 not in (1, 2) or (c - c0) % 9 == 0 else "#"
    for r in range(1, h - 1):
        g[r][min(w - 2, 1)] = "."
    for c in range(1, w - 1):
        g[h - 2][c] = "."
    for r0, c0 in rooms:
        for r in range(r0, min(h - 2, r0 + 12)):
            g[r][c0 - 1 if c0 > 1 else 1] = "."
    return g


FAMILIES = {"parallel": fam_parallel, "vertical": fam_vertical, "islands": fam_islands, "random": fam_random,
            "comb": fam_comb, "lshape": fam_lshape, "maze": fam_maze, "clusters": fam_clusters}


def bfs_flat(rows, w, h, sources):
    d = [-1] * (w * h)
    q = deque(sources)
    for s in sources:
        d[s] = 0
    while q:
        i = q.popleft()
        r, c = divmod(i, w)
        for dr, dc in DIRS:
            rr, cc = r + dr, c + dc
            if 0 <= rr < h and 0 <= cc < w and rows[rr][cc] != "#" and d[rr * w + cc] < 0:
                d[rr * w + cc] = d[i] + 1
                q.append(rr * w + cc)
    return d


def make_instance(family, tier, seed):
    w, h, k, _ = TIERS[tier]
    rnd = random.Random(f"{family}-{tier}-{seed}")
    g = FAMILIES[family](w, h, rnd)
    sr, sc = h - 2, 1
    g[sr][sc] = "."
    rows = ["".join(r) for r in g]
    reach = bfs_flat(rows, w, h, [sr * w + sc])
    free = sum(r.count(".") for r in rows)
    if sum(d >= 0 for d in reach) < 0.5 * free:  # the station is boxed in: add an entrance corridor
        for c in range(1, w - 1):
            g[sr][c] = "."
        for r in range(1, h - 1):
            g[r][sc] = "."
        rows = ["".join(r) for r in g]
        reach = bfs_flat(rows, w, h, [sr * w + sc])
    shelves = []
    for r in range(1, h - 1):
        for c in range(1, w - 1):
            if rows[r][c] == "#":
                acc = [(r + dr, c + dc) for dr, dc in DIRS
                       if 0 <= r + dr < h and 0 <= c + dc < w and reach[(r + dr) * w + c + dc] >= 0]
                if acc:
                    shelves.append(((r, c), acc))
    if len(shelves) < k + 5:  # store too small or sealed: fall back to free cells as pick points
        shelves = [((r, c), [(r, c)]) for r in range(h) for c in range(w) if reach[r * w + c] > 0]
    chosen = rnd.sample(shelves, min(len(shelves), max(k * 5, k + 5)))
    products = {f"P{n:04d}": {"name": f"item{n}", "shelf": list(s), "access": [list(a) for a in acc]}
                for n, (s, acc) in enumerate(chosen)}
    ids = rnd.sample(sorted(products), k)
    return {"family": family, "tier": tier, "seed": seed, "grid": rows, "station": [sr, sc],
            "products": products, "ids": ids}


# ---- validation -----------------------------------------------------------------------------

def validate_trace(canon, label, res, round_trip):
    rows, (sr, sc) = canon["grid"], canon["station"]
    h, w = len(rows), len(rows[0])
    trace = [tuple(c) for c in res["trace"]]
    pos, seen = (sr, sc), {(sr, sc)}
    for cell in trace:
        assert abs(cell[0] - pos[0]) + abs(cell[1] - pos[1]) == 1, f"{label}: non-adjacent move {pos}->{cell}"
        assert 0 <= cell[0] < h and 0 <= cell[1] < w and rows[cell[0]][cell[1]] != "#", f"{label}: walked into a wall"
        pos = cell
        seen.add(cell)
    if round_trip:
        assert pos == (sr, sc), f"{label}: route must end at the station"
    for pid in canon["ids"]:
        shelf = tuple(canon["products"][pid]["shelf"])
        near = [shelf] + [(shelf[0] + dr, shelf[1] + dc) for dr, dc in DIRS]
        assert any(c in seen for c in near), f"{label}: never reached {pid}"
    assert res["dist"] == len(trace), f"{label}: reported distance differs from the trace"
    want_t = len(trace) / res["speed"] + res["pick"] * len(canon["ids"])
    assert abs(res["time"] - want_t) < 0.5 + 1e-6 * want_t, f"{label}: reported time {res['time']} differs from {want_t:.1f}"
    return len(trace)


def exact_optimum(canon, round_trip=True):
    """Brute force over visit orders and access cells (small baskets only)."""
    rows = canon["grid"]
    h, w = len(rows), len(rows[0])
    ids = canon["ids"]
    st = canon["station"][0] * w + canon["station"][1]
    acc = {p: [a[0] * w + a[1] for a in canon["products"][p]["access"]] for p in ids}
    dm = {}
    for cell in {st, *(c for p in ids for c in acc[p])}:
        dm[cell] = bfs_flat(rows, w, h, [cell])
    best = math.inf
    for perm in itertools.permutations(ids):
        layer = {st: 0}
        for p in perm:
            layer = {c: min(cost + dm[prev][c] for prev, cost in layer.items() if dm[prev][c] >= 0)
                     for c in acc[p] if any(dm[prev][c] >= 0 for prev in layer)}
            if not layer:
                break
        if layer:
            total = min(cost + (dm[c][st] if round_trip else 0) for c, cost in layer.items())
            best = min(best, total)
    return best


def nn_distance(canon):
    """Round-trip distance of a plain nearest-neighbour tour (first access cell per item): a calibration reference."""
    rows = canon["grid"]
    h, w = len(rows), len(rows[0])
    st = canon["station"][0] * w + canon["station"][1]
    cell = {p: canon["products"][p]["access"][0][0] * w + canon["products"][p]["access"][0][1] for p in canon["ids"]}
    maps = {}

    def dist(a, b):
        if a not in maps:
            maps[a] = bfs_flat(rows, w, h, [a])
        return maps[a][b]

    left, cur, total = set(canon["ids"]), st, 0
    while left:
        nxt = min(left, key=lambda p: dist(cur, cell[p]))
        total += dist(cur, cell[nxt])
        cur = cell[nxt]
        left.remove(nxt)
    return total + dist(cur, st)


def one_tree_bound(canon):
    """Valid lower bound for a round trip: 1-tree over item sets (distance between sets is a relaxation)."""
    rows = canon["grid"]
    h, w = len(rows), len(rows[0])
    ids = canon["ids"]
    st = canon["station"][0] * w + canon["station"][1]
    sets = [[st]] + [[a[0] * w + a[1] for a in canon["products"][p]["access"]] for p in ids]
    maps = [bfs_flat(rows, w, h, s) for s in sets]  # distance from the nearest cell of each set
    n = len(sets)
    D = [[0 if i == j else min(maps[i][c] for c in sets[j] if maps[i][c] >= 0) for j in range(n)] for i in range(n)]
    in_tree, key, total = {1}, {j: D[1][j] for j in range(2, n)}, 0
    while key:
        j = min(key, key=key.get)
        total += key.pop(j)
        in_tree.add(j)
        for m in key:
            key[m] = min(key[m], D[j][m])
    two = sorted(D[0][j] for j in range(1, n))[:2]
    return total + sum(two) if n > 2 else 2 * D[0][1]


# ---- adapters (one worker per solution, run in a subprocess so a time limit can be enforced) ----

def worker_without_herd(project, canon, out_path):
    sys.path.insert(0, str(project))
    import router
    grid = [list(r) for r in canon["grid"]]
    sr, sc = canon["station"]
    grid[sr][sc] = "S"
    data = {"grid": ["".join(r) for r in grid],
            "products": {pid: {"name": p["name"], "pos": p["shelf"]} for pid, p in canon["products"].items()}}
    store = router.Store(data)
    ids = canon["ids"]
    t0 = time.time()
    opt = router.optimize(store, ids)
    res = {"opt_seconds": time.time() - t0, "round_trip": True, "speed": SPEED_DEFAULT, "pick": 5.0}
    for label, order in (("list", ids), ("opt", opt)):
        d, t, trace = router.simulate(store, order, SPEED_DEFAULT, 5.0, 0, label, lambda *a, **k: None)
        res[label] = {"dist": d, "time": t, "speed": SPEED_DEFAULT, "pick": 5.0, "trace": [divmod(c, store.w) for c in trace]}
    json.dump(res, open(out_path, "w"))


def worker_with_herd(project, canon, out_path):
    sys.path.insert(0, str(project))
    import router
    m = {"grid": [list(r) for r in canon["grid"]], "start": canon["station"],
         "products": [{"id": p, "name": v["name"], "pos": v["access"][0]} for p, v in canon["products"].items()]}
    store = router.Store(m)
    ids = canon["ids"]
    t0 = time.time()
    opt = router.optimize(store, ids)
    res = {"opt_seconds": time.time() - t0, "round_trip": True, "speed": router.SPEED, "pick": router.PICK_S}
    for label, order in (("list", ids), ("opt", opt)):
        trace = [list(ev["cell"]) for ev in router.simulate(store, order) if ev["kind"] == "move"]
        k = router.kpis(store, order)
        res[label] = {"dist": k["distance_m"], "time": k["time_s"], "speed": router.SPEED, "pick": router.PICK_S,
                      "trace": trace}
    json.dump(res, open(out_path, "w"))


def _paths(rows, w, h, stops):
    """Shortest cell path through consecutive stop cells (list of (r, c))."""
    out = []
    for a, b in zip(stops, stops[1:]):
        prev, q = {a: None}, deque([a])
        while q:
            cur = q.popleft()
            if cur == b:
                break
            for dr, dc in DIRS:
                n = (cur[0] + dr, cur[1] + dc)
                if 0 <= n[0] < h and 0 <= n[1] < w and rows[n[0]][n[1]] != "#" and n not in prev:
                    prev[n] = cur
                    q.append(n)
        leg, cur = [], b
        while prev[cur] is not None:
            leg.append(cur)
            cur = prev[cur]
        out += leg[::-1]
    return out


def worker_reference(project, canon, out_path):
    """Nearest-neighbour reference used to test this verifier. Not a solution under test."""
    rows = canon["grid"]
    h, w = len(rows), len(rows[0])
    st = tuple(canon["station"])
    ids = canon["ids"]
    first = {p: tuple(canon["products"][p]["access"][0]) for p in ids}
    maps = {}

    def dist(a, b):
        if a not in maps:
            maps[a] = bfs_flat(rows, w, h, [a[0] * w + a[1]])
        return maps[a][b[0] * w + b[1]]

    left, cur, order = set(ids), st, []
    while left:
        nxt = min(left, key=lambda p: dist(cur, first[p]))
        order.append(nxt)
        left.remove(nxt)
        cur = first[nxt]
    res = {"opt_seconds": 0.0, "round_trip": True, "speed": 1.0, "pick": 5.0}
    for label, seq in (("list", ids), ("opt", order)):
        trace = _paths(rows, w, h, [st] + [first[p] for p in seq] + [st])
        res[label] = {"dist": len(trace), "time": len(trace) / 1.0 + 5.0 * len(ids), "speed": 1.0, "pick": 5.0,
                      "trace": trace}
    if canon.get("_break") == "teleport":
        res["opt"]["trace"] = [res["opt"]["trace"][len(res["opt"]["trace"]) // 2], list(st)]  # jumps across the store
        res["opt"]["dist"] = 2
    if canon.get("_break") == "skip_item":
        res["opt"]["trace"] = res["opt"]["trace"][:5] + [st]
    json.dump(res, open(out_path, "w"))


WORKERS = {"with_herd": worker_with_herd, "without_herd": worker_without_herd, "reference": worker_reference}


def run_worker(adapter, project, canon, limit):
    with tempfile.TemporaryDirectory() as t:
        cp, op = Path(t) / "canon.json", Path(t) / "out.json"
        cp.write_text(json.dumps(canon))
        t0 = time.time()
        try:
            p = subprocess.run([sys.executable, __file__, "--worker", adapter, str(project), str(cp), str(op)],
                               capture_output=True, text=True, timeout=limit)
        except subprocess.TimeoutExpired:
            return None, time.time() - t0, "timeout"
        wall = time.time() - t0
        if p.returncode != 0 or not op.exists():
            return None, wall, "crash: " + (p.stderr.strip().splitlines() or ["?"])[-1][:100]
        return json.loads(op.read_text()), wall, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("adapter")
    ap.add_argument("project")
    ap.add_argument("--tiers", default="S,M,L")
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--families", default=",".join(FAMILIES))
    ap.add_argument("--limit-scale", type=float, default=1.0)
    ap.add_argument("--break", dest="brk", default=None, help="self-test only")
    a = ap.parse_args()
    rows = []
    for tier in a.tiers.split(","):
        for fam in a.families.split(","):
            for seed in range(a.seeds if tier in ("S", "M") else 1):
                canon = make_instance(fam, tier, 7000 + seed)
                if a.brk:
                    canon["_break"] = a.brk
                limit = TIERS[tier][3] * a.limit_scale
                res, wall, status = run_worker(a.adapter, a.project, canon, limit)
                row = {"tier": tier, "family": fam, "seed": seed, "wall": wall, "status": status, "saving": None,
                       "gap": None, "invalid": None}
                if res:
                    try:
                        rt = res.get("round_trip", True)
                        validate_trace(canon, "list-order", res["list"], rt)
                        validate_trace(canon, "optimized", res["opt"], rt)
                        row["saving"] = 1 - res["opt"]["time"] / res["list"]["time"]
                        if tier == "S":
                            row["gap"] = res["opt"]["dist"] / exact_optimum(canon, rt) - 1
                        else:
                            row["gap"] = res["opt"]["dist"] / nn_distance(canon) - 1
                    except AssertionError as e:
                        row["invalid"] = str(e)[:110]
                rows.append(row)
    print("| tier | store layouts | finished in time | valid | mean time saved | worst | share at or above 30% | "
          "median wall (s) | distance vs exact optimum (S) or vs plain nearest-neighbour (M, L): mean, worst |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    ok_all = True
    for tier in a.tiers.split(","):
        rs = [r for r in rows if r["tier"] == tier]
        done = [r for r in rs if r["status"] == "ok"]
        valid = [r for r in done if r["invalid"] is None]
        sv = [r["saving"] for r in valid]
        gaps = [r["gap"] for r in valid if r["gap"] is not None]
        gap_txt = f"{statistics.mean(gaps):+.1%}, {max(gaps):+.1%}" if gaps else "n/a"
        print(f"| {tier} | {len(rs)} | {len(done)} of {len(rs)} | {len(valid)} of {len(done)} | "
              f"{statistics.mean(sv):.1%} | {min(sv):.1%} | {sum(s >= 0.30 for s in sv)} of {len(sv)} | "
              f"{statistics.median(r['wall'] for r in done):.1f} | {gap_txt} |"
              if sv else f"| {tier} | {len(rs)} | {len(done)} of {len(rs)} | {len(valid)} of {len(done)} | n/a | n/a | n/a | n/a | {gap_txt} |")
        ok_all &= len(valid) == len(rs)
    print("\nBy layout family (mean time saved, instances finished and valid):")
    for fam in a.families.split(","):
        rs = [r for r in rows if r["family"] == fam]
        valid = [r for r in rs if r["status"] == "ok" and r["invalid"] is None]
        sv = [r["saving"] for r in valid]
        print(f"- {fam}: {statistics.mean(sv):.1%} saved, {len(valid)} of {len(rs)}" if sv else f"- {fam}: none valid, 0 of {len(rs)}")
    for r in rows:
        if r["status"] != "ok" or r["invalid"]:
            print(f"! {r['tier']} {r['family']} seed {r['seed']}: {r['invalid'] or r['status']} ({r['wall']:.0f}s)")
    print("RESULT:", "PASS" if ok_all else "FAIL", "(every instance finished in time with a valid route)")
    return 0 if ok_all else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        _, _, name, project, cp, op = sys.argv
        WORKERS[name](Path(project), json.loads(Path(cp).read_text()), op)
        sys.exit(0)
    sys.exit(main())
