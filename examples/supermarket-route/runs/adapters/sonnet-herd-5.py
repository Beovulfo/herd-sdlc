import sys


def worker(project, canon):
    sys.path.insert(0, str(project)); import route_optimizer as ro
    st = list(canon["station"])
    import json, os, tempfile
    raw = {"grid": canon["grid"], "entrance": st, "checkout": st, "cell_m": 1.0,
           "products": [{"id": p, "name": v["name"], "row": v["shelf"][0], "col": v["shelf"][1]}
                        for p, v in canon["products"].items()]}
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "m.json")
        with open(path, "w") as f:
            json.dump(raw, f)
        m = ro.load_map(path)
    opt_v, naive_v = ro.visits_for(m, canon["ids"])
    res = {"round_trip": True}
    for label, visits in (("list", naive_v), ("opt", opt_v)):
        ev = list(ro.simulate(m, visits))
        res[label] = {"dist": ev[-1]["distance_m"], "time": ev[-1]["time_s"], "speed": ro.WALK_MPS, "pick": ro.PICK_S,
                      "trace": [list(divmod(e["cell"], m["w"])) for e in ev if e["kind"] == "move"]}
    return res


def probe(sc, d, rp):
    m = {"grid": rp.GRID, "entrance": [rp.START[1], rp.START[0]], "checkout": [rp.START[1], rp.START[0]],
         "products": [{"id": p, "name": rp.NAMES[p], "row": rp.SHELF[p][0], "col": rp.SHELF[p][1]} for p in rp.SHELF]}
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + "\n")
    return ["route_optimizer.py", "run", str(d / "m.json"), str(d / "l.txt")]
