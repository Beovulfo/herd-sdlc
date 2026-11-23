import sys


def _grid(g):
    # project accepts only '#' and '.'; canon: anything not '#' is walkable
    return ["".join("#" if c == "#" else "." for c in row) for row in g]


def _cell(g, shelf):
    # project wants a floor cell: use shelf if walkable, else first in-grid walkable
    # neighbour in order up, down, left, right (no reachability check); else the shelf itself
    r, c = shelf
    if g[r][c] != "#":
        return r, c
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < len(g) and 0 <= nc < len(g[0]) and g[nr][nc] != "#":
            return nr, nc
    return r, c


def _map(grid, start_rc, shelves, names):
    g = _grid(grid)
    prods = []
    for p, s in shelves.items():
        r, c = _cell(grid, s)
        prods.append({"id": p, "name": names[p], "x": c, "y": r})
    return {"grid": g, "start": [start_rc[1], start_rc[0]], "products": prods}


def worker(project, canon):
    sys.path.insert(0, str(project)); import route_optimizer as ro
    st = canon["station"]
    m = _map(canon["grid"], st, {p: v["shelf"] for p, v in canon["products"].items()},
             {p: v["name"] for p, v in canon["products"].items()})
    store = ro.Store.from_dict(m)
    ids = list(canon["ids"])
    res = {}
    trace_ends = []
    for label, plan in (("list", ro.plan_list_order), ("opt", ro.plan_optimized)):
        route = plan(store, ids)
        fr = list(ro.simulate(store, route))
        trace = [[f.y, f.x] for f in fr if f.picked_id is None]
        trace_ends.append(trace[-1] if trace else list(st))
        res[label] = {"dist": fr[-1].distance if fr else route.distance,
                      "time": fr[-1].time_s if fr else route.time_s(),
                      "speed": ro.WALK_M_PER_S, "pick": ro.PICK_S, "trace": trace}
    res["round_trip"] = all(e == list(st) for e in trace_ends)
    return res


def probe(sc, d, rp):
    m = _map(rp.GRID, (rp.START[1], rp.START[0]), rp.SHELF, rp.NAMES)
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + "\n")
    return ["route_optimizer.py", str(d / "m.json"), str(d / "l.txt")]
