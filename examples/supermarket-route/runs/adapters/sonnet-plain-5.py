import sys


def _grid(g, r, c):
    return [row if i != r else row[:c] + "S" + row[c + 1:] for i, row in enumerate(g)]


def worker(project, canon):
    sys.path.insert(0, str(project)); import route
    sr, sc = canon["station"]
    m = {"grid": _grid(canon["grid"], sr, sc),
         "products": [{"id": p, "name": v["name"], "x": v["shelf"][1], "y": v["shelf"][0]} for p, v in canon["products"].items()]}
    store = route.Store(m)
    order, naive, rt = route.solve(store, list(canon["ids"]))
    res = {"round_trip": True}
    for label, o in (("list", naive), ("opt", order)):
        t, d = route.simulate(store, list(canon["ids"]), o, rt, label)
        _, cells = rt(o)  # the project's own cell-by-cell path that simulate walks
        if cells[-1] != store.exit:
            res["round_trip"] = False
        res[label] = {"dist": d, "time": t, "speed": route.SPEED, "pick": route.PICK,
                      "trace": [[c // store.w, c % store.w] for c in cells[1:]]}
    return res


def probe(sc, d, rp):
    m = {"grid": _grid(rp.GRID, rp.START[1], rp.START[0]),
         "products": [{"id": p, "name": rp.NAMES[p], "x": rp.SHELF[p][1], "y": rp.SHELF[p][0]} for p in rp.SHELF]}
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + "\n")
    return ["route.py", "run", str(d / "m.json"), str(d / "l.txt")]
