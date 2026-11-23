import sys


def _map(grid, start_rc, products):
    return {"grid": grid, "start": list(start_rc),
            "products": [{"id": p, "name": n, "pos": list(rc)} for p, n, rc in products]}


def worker(project, canon):
    sys.path.insert(0, str(project)); import routeopt as route
    st = tuple(canon["station"])
    m = _map(canon["grid"], st, [(p, v["name"], v["shelf"]) for p, v in canon["products"].items()])
    items = [(i, canon["products"][i]["name"]) for i in canon["ids"]]
    traces = {"list-order": [], "optimized": []}
    last = {}

    def tr(name, kind, cell, label, dm, t):
        last[name] = (dm, t)
        if kind == "move":
            traces[name].append([cell[0], cell[1]])

    res = route.run(m, items, tr)
    out = {"round_trip": True}
    for label, name in (("list", "list-order"), ("opt", "optimized")):
        out[label] = {"dist": res[name]["distance_m"], "time": res[name]["time_s"],
                      "speed": route.SPEED, "pick": route.PICK_S, "trace": traces[name]}
        if not traces[name] or tuple(traces[name][-1]) != st:
            out["round_trip"] = False
    return out


def probe(sc, d, rp):
    m = _map(rp.GRID, (rp.START[1], rp.START[0]), [(p, rp.NAMES[p], rp.SHELF[p]) for p in rp.SHELF])
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + "\n" if rp.lines(sc) else "")
    return ["routeopt.py", "run", str(d / "m.json"), str(d / "l.txt")]
