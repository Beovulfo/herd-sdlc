import re
import sys


def worker(project, canon):
    sys.path.insert(0, str(project)); import router
    sr, sc = canon["station"]
    m = {"grid": canon["grid"], "start": [sc, sr], "end": [sc, sr],
         "products": {p: {"name": v["name"], "x": v["shelf"][1], "y": v["shelf"][0]} for p, v in canon["products"].items()}}
    lines = []
    # every=1 makes the project's own simulator print one "at (x, y)" line per step
    r = router.compare(router.Store(m), list(canon["ids"]), every=1, out=lines.append)
    res = {"round_trip": True}
    for label, tag in (("list", "[list-order]"), ("opt", "[optimized ]")):
        trace = []
        for ln in lines:
            mt = re.match(re.escape(tag) + r".* at \((\d+), (\d+)\)$", ln)
            if mt and "PICK" not in ln:
                trace.append([int(mt.group(2)), int(mt.group(1))])
        res[label] = {"dist": r[label + "_dist"], "time": r[label + "_time"],
                      "speed": router.SPEED, "pick": router.PICK, "trace": trace}
    return res


def probe(sc, d, rp):
    m = {"grid": rp.GRID, "start": list(rp.START), "end": list(rp.START),
         "products": {p: {"name": rp.NAMES[p], "x": rp.SHELF[p][1], "y": rp.SHELF[p][0]} for p in rp.SHELF}}
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + "\n")
    return ["router.py", "run", str(d / "m.json"), str(d / "l.txt")]
