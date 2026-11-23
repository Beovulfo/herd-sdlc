import sys


def worker(project, canon):
    sys.path.insert(0, str(project)); import router
    sr, sc = canon["station"]
    rows = ["".join("#" if c == "#" else "." for c in r) for r in canon["grid"]]
    rows[sr] = rows[sr][:sc] + "S" + rows[sr][sc + 1:]
    m = {"rows": rows,
         "products": [{"id": p, "name": v["name"], "x": v["shelf"][1], "y": v["shelf"][0]} for p, v in canon["products"].items()]}
    store = router.Store(m)
    res = {"round_trip": True}
    for label, opt in (("list", False), ("opt", True)):
        evs = list(router.simulate(store, list(canon["ids"]), opt))
        last = evs[-1]
        if store.xy(store.end) != (last["x"], last["y"]) or (last["x"], last["y"]) != (sc, sr):
            res["round_trip"] = False
        res[label] = {"dist": last["distance_m"], "time": last["time_s"], "speed": router.SPEED, "pick": router.PICK_S,
                      "trace": [[e["y"], e["x"]] for e in evs if e["kind"] == "step"]}
    return res


def probe(sc, d, rp):
    sr, scol = rp.START[1], rp.START[0]
    rows = ["".join("#" if c == "#" else "." for c in r) for r in rp.GRID]
    rows[sr] = rows[sr][:scol] + "S" + rows[sr][scol + 1:]
    m = {"rows": rows, "products": [{"id": p, "name": rp.NAMES[p], "x": rp.SHELF[p][1], "y": rp.SHELF[p][0]} for p in rp.SHELF]}
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + "\n" if rp.lines(sc) else "")
    return ["router.py", "simulate", str(d / "m.json"), str(d / "l.txt")]
