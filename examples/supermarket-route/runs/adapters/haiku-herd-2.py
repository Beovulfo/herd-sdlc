import sys


def _layout(grid):
    return ["".join("#" if ch == "#" else "." for ch in r) for r in grid]


def _map(grid, start, prods):
    # start is [x, y] = [col, row]; products carry x=col, y=row and may sit on blocked cells
    return {"layout": _layout(grid), "start": list(start), "products": prods}


def worker(project, canon):
    sys.path.insert(0, str(project)); import route_optimizer as ro
    sr, sc = canon["station"]
    prods = [{"id": p, "short": v["name"], "x": v["shelf"][1], "y": v["shelf"][0]} for p, v in canon["products"].items()]
    store = ro.load_store(_map(canon["grid"], [sc, sr], prods))
    items = [(i, canon["products"][i]["name"]) for i in canon["ids"]]
    res = {"round_trip": True}
    for label, opt in (("list", False), ("opt", True)):
        plan = ro.plan_route(store, items, optimize=opt)
        ev = list(ro.simulate(store, plan))
        res[label] = {"dist": ev[-1]["distance_m"], "time": ev[-1]["time_s"], "speed": ro.WALK_M_PER_S, "pick": ro.PICK_S,
                      "trace": [[e["y"], e["x"]] for e in ev if e["action"] == "move"]}
        if not ev or (ev[-1]["y"], ev[-1]["x"]) != (sr, sc):
            res["round_trip"] = False
    return res


def probe(sc, d, rp):
    prods = [{"id": p, "short": rp.NAMES[p], "x": rp.SHELF[p][1], "y": rp.SHELF[p][0]} for p in rp.SHELF]
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(_map(rp.GRID, rp.START, prods)))
    lines = rp.lines(sc)
    (d / "l.txt").write_text("\n".join(lines) + "\n" if lines else "")
    return ["route_optimizer.py", str(d / "m.json"), str(d / "l.txt")]
