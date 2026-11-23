import json
import re
import sys
import tempfile
from pathlib import Path


def _pick_cell(grid, shelf):
    r, c = shelf
    ok = lambda r, c: 0 <= r < len(grid) and 0 <= c < len(grid[0]) and grid[r][c] != "#"
    if ok(r, c):
        return r, c
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        if ok(r + dr, c + dc):
            return r + dr, c + dc
    return r, c


def _mapdict(grid, station, shelves):
    g = [list(row) for row in grid]
    g[station[0]][station[1]] = "E"
    prods = []
    for pid, (name, shelf) in shelves.items():
        r, c = _pick_cell(grid, shelf)
        prods.append({"id": pid, "name": name, "x": c, "y": r})
    return {"grid": ["".join(row) for row in g], "products": prods}


def worker(project, canon):
    sys.path.insert(0, str(project))
    import supermarket_route as sr
    shelves = {p: (v["name"], v["shelf"]) for p, v in canon["products"].items()}
    m = _mapdict(canon["grid"], canon["station"], shelves)
    with tempfile.TemporaryDirectory() as d:
        mp, lp = Path(d, "m.json"), Path(d, "l.txt")
        mp.write_text(json.dumps(m))
        lp.write_text("\n".join(f"{i}:{canon['products'][i]['name']}" for i in canon["ids"]) + "\n")
        grid, entrance, products = sr.load_map(str(mp))
        picks = sr.load_list(str(lp), products)
    stops = [entrance] + [products[p][1] for p in picks]
    labels = ["ENTRANCE"] + [f"{p} {products[p][0]}" for p in picks]
    d = sr.distance_matrix(grid, stops, labels)
    res = {"round_trip": True}
    for key, cycle in (("list", list(range(len(stops)))), ("opt", sr.plan(d))):
        lines = []
        r = sr.simulate(grid, stops, labels, cycle, sr.WALK_SPEED_M_S, sr.PICK_SECONDS, emit=lines.append, trace=True)
        trace = [[int(y), int(x)] for x, y in (re.search(r"step to \((\d+), (\d+)\)", l).groups() for l in lines if "step to" in l)]
        res[key] = {"dist": r["distance_m"], "time": r["time_s"], "speed": sr.WALK_SPEED_M_S,
                    "pick": sr.PICK_SECONDS, "trace": trace}
        if trace and trace[-1] != list(canon["station"]):
            res["round_trip"] = False
    return res


def probe(sc, d, rp):
    shelves = {p: (rp.NAMES[p], rp.SHELF[p]) for p in rp.SHELF}
    m = _mapdict(rp.GRID, (rp.START[1], rp.START[0]), shelves)
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + "\n")
    return ["supermarket_route.py", "--map", str(d / "m.json"), "--list", str(d / "l.txt")]
