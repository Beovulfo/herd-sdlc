import sys


def _grid(grid, row, col):
    # project walkable = '.' and 'E'; anything else blocks. canon: '#' blocked, else walkable.
    g = [["#" if ch == "#" else "." for ch in r] for r in grid]
    g[row][col] = "E"
    return ["".join(r) for r in g]


def _map(grid, row, col, prods):
    return {"grid": _grid(grid, row, col),
            "products": [{"id": p, "short_name": n, "row": r, "col": c} for p, n, r, c in prods]}


def worker(project, canon):
    sys.path.insert(0, str(project))
    from supermarket_route.layout import parse_list, parse_map
    from supermarket_route.planner import build_model, route
    from supermarket_route.simulate import kpis, simulate
    sr, sc = canon["station"]
    store = parse_map(_map(canon["grid"], sr, sc,
                           [(p, v["name"], v["shelf"][0], v["shelf"][1]) for p, v in canon["products"].items()]))
    model = build_model(store, parse_list("\n".join(f"{i}:{canon['products'][i]['name']}" for i in canon["ids"]), store))
    walk, pick = 1.0, 3.0  # the CLI defaults (--walk-seconds, --pick-seconds)
    res = {}
    for label, mode in (("list", "list"), ("opt", "optimized")):
        steps = list(simulate(model, route(model, mode), walk, pick))
        k = kpis(steps)
        res[label] = {"dist": k["distance_covered"], "time": k["time_to_prepare_basket"],
                      "speed": 1.0 / walk, "pick": pick,
                      "trace": [[s["row"], s["col"]] for s in steps if s["event"] == "move"]}
    # the project's route ends at the last pick, it does not return to the entrance
    res["round_trip"] = all(res[x]["trace"] and res[x]["trace"][-1] == [sr, sc] for x in ("list", "opt"))
    return res


def probe(sc, d, rp):
    m = _map(rp.GRID, rp.START[1], rp.START[0], [(p, rp.NAMES[p], rp.SHELF[p][0], rp.SHELF[p][1]) for p in rp.SHELF])
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + ("\n" if rp.lines(sc) else ""))
    return ["-m", "supermarket_route", "--map", str(d / "m.json"), "--list", str(d / "l.txt")]
