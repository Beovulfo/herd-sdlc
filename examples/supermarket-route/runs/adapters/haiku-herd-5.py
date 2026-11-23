import sys


def _map(grid, start_rc, shelves, names):
    # project: '.'/'#' only, products on walkable cells, x=col y=row
    g = ["".join("#" if ch == "#" else "." for ch in r) for r in grid]
    prods = []
    for p, (r, c) in shelves.items():
        cell = (r, c)
        if g[r][c] == "#":  # naive: first in-grid walkable neighbour, up/down/left/right
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                rr, cc = r + dr, c + dc
                if 0 <= rr < len(g) and 0 <= cc < len(g[0]) and g[rr][cc] == ".":
                    cell = (rr, cc)
                    break
        prods.append({"id": p, "name": names[p], "x": cell[1], "y": cell[0]})
    return {"grid": g, "entrance": {"x": start_rc[1], "y": start_rc[0]}, "products": prods}


def worker(project, canon):
    sys.path.insert(0, str(project))
    import route_optimizer as ro
    m = _map(canon["grid"], canon["station"], {p: tuple(v["shelf"]) for p, v in canon["products"].items()},
             {p: v["name"] for p, v in canon["products"].items()})
    store = ro.parse_store(m)
    res = {"round_trip": True}
    for label, order in (("list", "list"), ("opt", "optimized")):
        steps = list(ro.simulate(ro.plan_route(store, canon["ids"], order)))
        res[label] = {"dist": steps[-1].distance_m, "time": steps[-1].seconds, "speed": ro.WALK_M_PER_S,
                      "pick": ro.PICK_S, "trace": [[s.cell[1], s.cell[0]] for s in steps if s.kind == "walk"]}
        tr = res[label]["trace"]
        if (tr[-1] if tr else list(canon["station"])) != list(canon["station"]):
            res["round_trip"] = False  # the project ends at the last pick, by its own design
    return res


def probe(sc, d, rp):
    m = _map(rp.GRID, (rp.START[1], rp.START[0]), rp.SHELF, rp.NAMES)
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + ("\n" if rp.lines(sc) else ""))
    return ["route_optimizer.py", "run", str(d / "m.json"), str(d / "l.txt")]
