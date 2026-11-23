import sys


def _layout(grid):
    # project: "." walkable, anything else blocked; canon: "#" blocked, anything else walkable
    return ["".join("#" if ch == "#" else "." for ch in row) for row in grid]


def worker(project, canon):
    sys.path.insert(0, str(project)); import route_optimizer as ro
    sr, sc = canon["station"]
    data = {"layout": _layout(canon["grid"]), "start": [sc, sr], "checkout": [sc, sr],
            "products": {p: {"name": v["name"], "at": [v["shelf"][1], v["shelf"][0]]} for p, v in canon["products"].items()}}
    store = ro.Store(data)
    traces = {"list-order": [], "optimized": []}

    def on_event(name, kind, kpi, where):
        if kind == "move":
            traces[name].append([where[1], where[0]])

    results, _ = ro.compare(store, list(canon["ids"]), on_event)
    res = {"round_trip": True}
    for label, name in (("list", "list-order"), ("opt", "optimized")):
        tr = traces[name]
        if (tr[-1] if tr else [sr, sc]) != [sr, sc]:
            res["round_trip"] = False
        res[label] = {"dist": results[name]["distance_m"], "time": results[name]["time_s"],
                      "speed": ro.WALK_MPS / ro.CELL_M, "pick": ro.PICK_S, "trace": tr}
    return res


def probe(sc, d, rp):
    m = {"layout": _layout(rp.GRID), "start": list(rp.START), "checkout": list(rp.START),
         "products": {p: {"name": rp.NAMES[p], "at": [rp.SHELF[p][1], rp.SHELF[p][0]]} for p in rp.SHELF}}
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + "\n")
    return ["route_optimizer.py", "run", str(d / "m.json"), str(d / "l.txt")]
