import contextlib, io, re, sys


def worker(project, canon):
    sys.path.insert(0, str(project)); import routeopt as r
    sr, sc = canon["station"]
    d = {"grid": canon["grid"], "start": [sc, sr], "end": [sc, sr],
         "products": [{"id": p, "name": v["name"], "x": v["shelf"][1], "y": v["shelf"][0]} for p, v in canon["products"].items()]}
    s, ids = r.Store(d), canon["ids"]
    nodes, _, listed, opt = r.plan(s, ids)
    res = {"round_trip": True}
    for label, order in (("list", listed), ("opt", opt)):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            dist, t = r.simulate(s, nodes, order, ids, verbose=1)  # verbose=1 prints every step
        trace = [[int(b), int(a)] for a, b in re.findall(r"step\s+\d+ at \((\d+), (\d+)\)", buf.getvalue())]
        if trace and trace[-1] != [sr, sc]:
            res["round_trip"] = False
        res[label] = {"dist": dist, "time": t, "speed": r.WALK_SPEED, "pick": r.PICK_TIME, "trace": trace}
    return res


def probe(sc, d, rp):
    m = {"grid": rp.GRID, "start": list(rp.START), "end": list(rp.START),
         "products": [{"id": p, "name": rp.NAMES[p], "x": rp.SHELF[p][1], "y": rp.SHELF[p][0]} for p in rp.SHELF]}
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + ("\n" if rp.lines(sc) else ""))
    return ["routeopt.py", "--map", str(d / "m.json"), "--list", str(d / "l.txt")]
