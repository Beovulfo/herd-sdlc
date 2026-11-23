import sys


def _map(grid, start_rc, products):
    r, c = start_rc
    return {"grid": grid, "start": [c, r], "checkout": [c, r],
            "products": [{"id": p, "name": n, "x": x, "y": y} for p, n, y, x in products]}


def worker(project, canon):
    sys.path.insert(0, str(project)); import router
    m = _map(canon["grid"], canon["station"],
             [(p, v["name"], v["shelf"][0], v["shelf"][1]) for p, v in canon["products"].items()])
    res = router.run_both(router.parse_map(m), [(i, canon["products"][i]["name"]) for i in canon["ids"]])
    out = {"round_trip": True}
    for label, key in (("list", "list"), ("opt", "optimized")):
        st = res[key]
        out[label] = {"dist": st[-1]["dist"], "time": st[-1]["t"], "speed": router.SPEED, "pick": router.PICK_S,
                      "trace": [[s["y"], s["x"]] for s in st if s["event"] == "move"]}
    return out


def probe(sc, d, rp):
    m = _map(rp.GRID, (rp.START[1], rp.START[0]), [(p, rp.NAMES[p], *rp.SHELF[p]) for p in rp.SHELF])
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + "\n")
    return ["router.py", "run", str(d / "m.json"), str(d / "l.txt")]
