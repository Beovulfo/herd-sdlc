import sys


def _mark(grid, r, c):
    g = list(grid)
    g[r] = g[r][:c] + "S" + g[r][c + 1:]
    return g


def worker(project, canon):
    sys.path.insert(0, str(project)); import route
    sr, sc = canon["station"]
    m = {"grid": _mark(canon["grid"], sr, sc),
         "products": [{"id": p, "name": v["name"], "x": v["shelf"][1], "y": v["shelf"][0]} for p, v in canon["products"].items()]}
    st = route.Store(m)
    ids = canon["ids"]
    pl = route.Planner(st, ids)
    k = len(ids)
    res = {}
    for label, order in (("list", list(range(k + 2))), ("opt", pl.optimize())):
        steps = route.build_route(st, ids, order, pl)
        dist, t = route.simulate(steps, st, label)
        res[label] = {"dist": dist, "time": t, "speed": route.WALK, "pick": route.PICK,
                      "trace": [[c[1], c[0]] for c, _ in steps[1:]]}
        res["round_trip"] = res.get("round_trip", True) and steps[-1][0] == (sc, sr)
    return res


def probe(sc, d, rp):
    g = _mark(rp.GRID, rp.START[1], rp.START[0])
    m = {"grid": g, "products": [{"id": p, "name": rp.NAMES[p], "x": rp.SHELF[p][1], "y": rp.SHELF[p][0]} for p in rp.SHELF]}
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + "\n")
    return ["route.py", "run", str(d / "m.json"), str(d / "l.txt")]
