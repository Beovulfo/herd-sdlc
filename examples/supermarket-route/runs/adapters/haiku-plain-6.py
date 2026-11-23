import sys


def _map(grid, st, prods):
    return {"cell_size_m": 1.0, "layout": grid, "entrance": [st[1], st[0]], "checkout": [st[1], st[0]],
            "products": [{"id": p, "name": n, "x": rc[1], "y": rc[0]} for p, n, rc in prods]}


def worker(project, canon):
    sys.path.insert(0, str(project)); import route_optimizer as ro
    m = _map(canon["grid"], canon["station"], [(p, v["name"], v["shelf"]) for p, v in canon["products"].items()])
    store = ro.Store(m)
    base, opt = ro.plan(store, list(canon["ids"]))
    res = {"round_trip": True}
    for label, route in (("list", base), ("opt", opt)):
        snaps = list(ro.walk(store, route))
        res[label] = {"dist": snaps[-1]["distance_m"], "time": snaps[-1]["t_s"],
                      "speed": ro.WALK_SPEED_MPS, "pick": ro.PICK_TIME_S,
                      "trace": [[s["cell"][1], s["cell"][0]] for s in snaps if s["event"] == "step"]}
        res["round_trip"] = res["round_trip"] and snaps[-1]["cell"] == store.checkout
    return res


def probe(sc, d, rp):
    m = _map(rp.GRID, (rp.START[1], rp.START[0]), [(p, rp.NAMES[p], rp.SHELF[p]) for p in rp.SHELF])
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + "\n")
    return ["route_optimizer.py", "run", str(d / "m.json"), str(d / "l.txt")]
