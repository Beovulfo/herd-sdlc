import sys


def worker(project, canon):
    sys.path.insert(0, str(project)); import route_optimizer as ro
    sr, sc = canon["station"]
    data = {"grid": canon["grid"], "entrance": [sc, sr], "checkout": [sc, sr],
            "products": [{"id": p, "name": v["name"], "x": v["shelf"][1], "y": v["shelf"][0]} for p, v in canon["products"].items()]}
    store = ro.Store(data)
    basket = [(i, *store.products[i]) for i in canon["ids"]]
    cells = [store.entrance] + [c for _, _, c in basket] + [store.checkout]
    labels = [None] + [f"{i} {n}" for i, n, _ in basket] + [None]
    trees = {c: ro.bfs(store, c) for c in set(cells)}
    res = {"round_trip": True}
    for key, tour in (("list", list(range(len(cells)))), ("opt", ro.order_stops(cells, trees))):
        ev = list(ro.simulate(store, trees, cells, labels, tour))
        res[key] = {"dist": ev[-1]["distance_m"], "time": ev[-1]["elapsed_s"], "speed": ro.WALK_MPS, "pick": ro.PICK_S,
                    "trace": [[e["y"], e["x"]] for e in ev if e["event"] is None and e["step"] > 0]}
        if (ev[-1]["y"], ev[-1]["x"]) != (sr, sc):
            res["round_trip"] = False
    return res


def probe(sc, d, rp):
    m = {"grid": rp.GRID, "entrance": list(rp.START), "checkout": list(rp.START),
         "products": [{"id": p, "name": rp.NAMES[p], "x": rp.SHELF[p][1], "y": rp.SHELF[p][0]} for p in rp.SHELF]}
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + "\n")
    return ["route_optimizer.py", "run", str(d / "m.json"), str(d / "l.txt")]
