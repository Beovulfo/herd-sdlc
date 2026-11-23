import json, sys, tempfile
from pathlib import Path


def worker(project, canon):
    sys.path.insert(0, str(project)); import router
    sr, sc = canon["station"]
    m = {"grid": canon["grid"], "start": [sc, sr], "end": [sc, sr],
         "products": [{"id": p, "name": v["name"], "x": v["shelf"][1], "y": v["shelf"][0]} for p, v in canon["products"].items()]}
    with tempfile.TemporaryDirectory() as td:
        mp, lp = Path(td) / "m.json", Path(td) / "l.txt"
        mp.write_text(json.dumps(m))
        lp.write_text("".join(f"{i}:{canon['products'][i]['name']}\n" for i in canon["ids"]))
        grid, start, end, items = router.load(str(mp), str(lp))
    pts = [start] + [c for _, _, c in items] + [end]
    opt = [i - 1 for i in router.optimize(router.dist_matrix(grid, pts))[1:-1]]
    res = {"round_trip": True}
    for label, order in (("list", list(range(len(items)))), ("opt", opt)):
        ev = list(router.simulate(grid, router.route_stops(start, end, items, order)))
        k, cell, _, dist, t = ev[-1]
        res["round_trip"] = res["round_trip"] and cell == end
        res[label] = {"dist": dist * router.CELL_M, "time": t, "speed": router.WALK_MPS / router.CELL_M, "pick": router.PICK_S,
                      "trace": [[e[1][1], e[1][0]] for e in ev if e[2] is None]}
    return res


def probe(sc, d, rp):
    m = {"grid": rp.GRID, "start": list(rp.START), "end": list(rp.START),
         "products": [{"id": p, "name": rp.NAMES[p], "x": rp.SHELF[p][1], "y": rp.SHELF[p][0]} for p in rp.SHELF]}
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + "\n")
    return ["router.py", "run", str(d / "m.json"), str(d / "l.txt")]
