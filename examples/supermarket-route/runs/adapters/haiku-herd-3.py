import sys


def _tr(grid, station, shelves):
    """Project map: '#' wall, '.' free, 'E' entrance; product cell must be free, so a blocked shelf
    moves to its first in-grid walkable neighbour (up, down, left, right), no reachability check."""
    rows = [list("#" if ch == "#" else "." for ch in r) for r in grid]
    rows[station[0]][station[1]] = "E"
    rows = ["".join(r) for r in rows]
    cells = {}
    for p, (r, c) in shelves.items():
        cell = [r, c]
        if rows[r][c] == "#":
            for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if 0 <= nr < len(rows) and 0 <= nc < len(rows[0]) and rows[nr][nc] != "#":
                    cell = [nr, nc]
                    break
        cells[p] = cell
    return rows, cells


def worker(project, canon):
    sys.path.insert(0, str(project)); import routeopt as route
    st = tuple(canon["station"])
    rows, cells = _tr(canon["grid"], st, {p: v["shelf"] for p, v in canon["products"].items()})
    m = {"rows": rows, "products": [{"id": p, "name": v["name"], "cell": cells[p]} for p, v in canon["products"].items()]}
    store = route.parse_map(m)
    list_stops, best = route.solve(store, canon["ids"])
    res = {}
    for label, stops in (("list", list_stops), ("opt", best)):
        ev = list(route.simulate(store, stops))
        trace = [list(e["cell"]) for e in ev if e["event"] == "step"]
        res[label] = {"dist": ev[-1]["distance"], "time": ev[-1]["time_s"], "speed": 1 / route.STEP_S,
                      "pick": route.PICK_S, "trace": trace}
    res["round_trip"] = all((r["trace"][-1] if r["trace"] else list(st)) == list(st) for r in (res["list"], res["opt"]))
    return res


def probe(sc, d, rp):
    rows, cells = _tr(rp.GRID, (rp.START[1], rp.START[0]), rp.SHELF)
    m = {"rows": rows, "products": [{"id": p, "name": rp.NAMES[p], "cell": cells[p]} for p in rp.SHELF]}
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + "\n")
    return ["routeopt.py", "compare", str(d / "m.json"), str(d / "l.txt")]
