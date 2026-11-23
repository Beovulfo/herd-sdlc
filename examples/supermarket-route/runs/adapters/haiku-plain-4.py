import inspect
import sys


def _cell(grid, shelf):
    r, c = shelf
    if grid[r][c] != "#":
        return [r, c]
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        a, b = r + dr, c + dc
        if 0 <= a < len(grid) and 0 <= b < len(grid[0]) and grid[a][b] != "#":
            return [a, b]
    return [r, c]


def _store(grid, st, prods):
    return {"grid": list(grid), "cell_size_m": 1.0, "entrance": list(st), "checkout": list(st),
            "products": [{"id": p, "name": n, "cell": _cell(grid, s)} for p, n, s in prods]}


def worker(project, canon):
    sys.path.insert(0, str(project)); import route_optimizer as ro
    import json, tempfile, os
    m = _store(canon["grid"], canon["station"], [(p, v["name"], v["shelf"]) for p, v in canon["products"].items()])
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "s.json"); open(f, "w").write(json.dumps(m))
        store = ro.load_store(f)
    prm = inspect.signature(ro.simulate).parameters
    speed, pick = prm["walk_speed_mps"].default, prm["pick_seconds"].default
    res = {"round_trip": True}
    for label, order in (("list", canon["ids"]), ("opt", ro.optimized_order(store, canon["ids"]))):
        ev = list(ro.simulate(store, order, speed, pick))
        res[label] = {"dist": ev[-1].distance_m, "time": ev[-1].elapsed_s, "speed": speed, "pick": pick,
                      "trace": [list(e.cell) for e in ev if e.kind == "walk"]}
        if ev[-1].cell != store.checkout:
            res["round_trip"] = False
    return res


def probe(sc, d, rp):
    m = _store(rp.GRID, (rp.START[1], rp.START[0]), [(p, rp.NAMES[p], rp.SHELF[p]) for p in rp.SHELF])
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + "\n")
    return ["route_optimizer.py", "--store", str(d / "m.json"), "--order", str(d / "l.txt")]
