import sys


def _cell(grid, rc):
    # project wants the pick cell itself: shelf if walkable, else first in-grid walkable neighbour (up, down, left, right), no reachability check
    r, c = rc
    for dr, dc in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
        rr, cc = r + dr, c + dc
        if 0 <= rr < len(grid) and 0 <= cc < len(grid[0]) and grid[rr][cc] != "#":
            return rr, cc
    return r, c


def worker(project, canon):
    sys.path.insert(0, str(project)); import supermarket_route as sr
    g = canon["grid"]; st = canon["station"]
    prods = []
    for p, v in canon["products"].items():
        r, c = _cell(g, v["shelf"])
        prods.append({"id": p, "name": v["name"], "x": c, "y": r})
    store = sr.Store({"grid": g, "start": [st[1], st[0]], "products": prods})
    planned = sr.plan(store, canon["ids"])
    res = {"round_trip": True}
    for label, order in (("list", planned["list"]), ("opt", planned["optimized"])):
        evs = []
        last = sr.run_route(store, planned, order, evs.append)
        trace = [[e["xy"][1], e["xy"][0]] for e in evs if e["event"] == "step"]
        if (trace[-1] if trace else list(st)) != list(st):
            res["round_trip"] = False
        res[label] = {"dist": last["distance"], "time": last["time_s"], "speed": 1.0 / sr.STEP_SECONDS,
                      "pick": sr.PICK_SECONDS, "trace": trace}
    return res


def probe(sc, d, rp):
    m = {"grid": rp.GRID, "start": list(rp.START),
         "products": [{"id": p, "name": rp.NAMES[p], "x": _cell(rp.GRID, rp.SHELF[p])[1], "y": _cell(rp.GRID, rp.SHELF[p])[0]} for p in rp.SHELF]}
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + "\n")
    return ["supermarket_route.py", "--map", str(d / "m.json"), "--request", str(d / "l.txt")]
