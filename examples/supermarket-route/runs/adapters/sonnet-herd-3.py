import inspect
import sys


def _store(canon):
    sr, sc = canon["station"]
    g = ["".join("#" if ch == "#" else "." for ch in row) for row in canon["grid"]]
    g[sr] = g[sr][:sc] + "S" + g[sr][sc + 1:]
    prods = [{"id": p, "name": v["name"], "row": v["shelf"][0], "col": v["shelf"][1]} for p, v in canon["products"].items()]
    return {"grid": g, "products": prods}


def worker(project, canon):
    sys.path.insert(0, str(project)); import route
    store = route.parse_store(_store(canon))
    items = [(i, canon["products"][i]["name"]) for i in canon["ids"]]
    stops = route.resolve(store, items)
    sig = inspect.signature(route.simulate).parameters
    speed, pick = sig["speed"].default, sig["pick_s"].default
    res = {"round_trip": True}
    for label, order in (("list", list(range(len(stops)))), ("opt", route.optimize(store, stops))):
        ev = list(route.simulate(store, stops, order, speed, pick))
        res[label] = {"dist": ev[-1]["distance"], "time": ev[-1]["t"], "speed": speed, "pick": pick,
                      "trace": [list(e["pos"]) for e in ev if e["event"] == "move"]}
        if ev[-1]["pos"] != store["start"]:
            res["round_trip"] = False
    return res


def probe(sc, d, rp):
    g = [row.replace("S", ".") for row in rp.GRID]
    r, c = rp.START[1], rp.START[0]
    g[r] = g[r][:c] + "S" + g[r][c + 1:]
    m = {"grid": g, "products": [{"id": p, "name": rp.NAMES[p], "row": rp.SHELF[p][0], "col": rp.SHELF[p][1]} for p in rp.SHELF]}
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + "\n")
    return ["route.py", "run", str(d / "m.json"), str(d / "l.txt")]
