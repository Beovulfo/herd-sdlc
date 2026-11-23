import sys


def worker(project, canon):
    sys.path.insert(0, str(project)); import route
    sr, sc = canon["station"]
    m = {"grid": canon["grid"], "start": [sc, sr], "end": [sc, sr],
         "products": [{"id": p, "name": v["name"], "x": v["shelf"][1], "y": v["shelf"][0]} for p, v in canon["products"].items()]}
    byid = {p["id"]: p for p in m["products"]}
    items = [byid[i] for i in canon["ids"]]
    nodes, D = route.build(m, items)
    orders = {"list": list(range(len(nodes))), "opt": route.optimize(D)}
    res = {"round_trip": True}
    for label, order in orders.items():
        ev = list(route.simulate(m, items, order, nodes))
        res[label] = {"dist": ev[-1][2], "time": ev[-1][3], "speed": route.WALK_SPEED, "pick": route.PICK_TIME,
                      "trace": [[e[1][1], e[1][0]] for e in ev if e[0] > 0 and e[4] is None]}
    return res


def probe(sc, d, rp):
    m = {"grid": rp.GRID, "start": list(rp.START), "end": list(rp.START),
         "products": [{"id": p, "name": rp.NAMES[p], "x": rp.SHELF[p][1], "y": rp.SHELF[p][0]} for p in rp.SHELF]}
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + "\n")
    return ["route.py", "run", str(d / "m.json"), "--list", str(d / "l.txt")]
