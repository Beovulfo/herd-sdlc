import inspect
import sys


def _grid(rows, station):
    # '#' stays blocked, everything else walkable; entrance 'E' at the station (start = end).
    g = [["#" if c == "#" else "." for c in r] for r in rows]
    g[station[0]][station[1]] = "E"
    return ["".join(r) for r in g]


def _map(rows, station, prods):
    return {"grid": _grid(rows, station),
            "products": [{"id": p, "name": n, "x": rc[1], "y": rc[0]} for p, n, rc in prods]}


def worker(project, canon):
    sys.path.insert(0, str(project)); import routeopt as route
    m = route.parse_map(_map(canon["grid"], canon["station"],
                             [(p, v["name"], v["shelf"]) for p, v in canon["products"].items()]))
    items = [(i, canon["products"][i]["name"]) for i in canon["ids"]]
    naive, best = route.plan(m, items)
    d = inspect.signature(route.simulate).parameters
    res = {"round_trip": True}
    for label, stops in (("list", naive), ("opt", best)):
        ev = list(route.simulate(m, stops))
        last = ev[-1]
        res["round_trip"] = res["round_trip"] and list(last["pos"]) == [canon["station"][1], canon["station"][0]]
        res[label] = {"dist": last["distance_m"], "time": last["time_s"],
                      "speed": d["speed"].default, "pick": d["pick_s"].default,
                      "trace": [[e["pos"][1], e["pos"][0]] for e in ev if e["event"] == "move"]}
    return res


def probe(sc, d, rp):
    m = _map(rp.GRID, (rp.START[1], rp.START[0]), [(p, rp.NAMES[p], rp.SHELF[p]) for p in rp.SHELF])
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + "\n")
    return ["routeopt.py",str(d / "m.json"), str(d / "l.txt")]
