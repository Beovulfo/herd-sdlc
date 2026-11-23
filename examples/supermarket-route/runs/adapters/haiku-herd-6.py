import sys


def _pick(grid, cell):
    r, c = cell
    if grid[r][c] != "#":
        return cell
    for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
        if 0 <= nr < len(grid) and 0 <= nc < len(grid[0]) and grid[nr][nc] != "#":
            return (nr, nc)
    return cell  # no walkable neighbour: pass the shelf cell as is, let the project reject it


def _layout(grid, station):
    sr, sc = station
    return ["".join("#" if ch == "#" else "S" if (r, c) == (sr, sc) else "." for c, ch in enumerate(row))
            for r, row in enumerate(grid)]


def _map(grid, station, shelves, names):
    prods = []
    for p, cell in shelves.items():
        r, c = _pick(grid, tuple(cell))
        prods.append({"id": p, "name": names[p], "row": r, "col": c})
    return {"layout": _layout(grid, station), "products": prods}


def worker(project, canon):
    sys.path.insert(0, str(project))
    from optimizer import simulate
    from optimizer.plan import list_order_route, optimized_route
    from optimizer.store import parse_list, parse_store
    m = _map(canon["grid"], canon["station"], {p: v["shelf"] for p, v in canon["products"].items()},
             {p: v["name"] for p, v in canon["products"].items()})
    store = parse_store(m)
    items = parse_list("\n".join(f"{i}:{canon['products'][i]['name']}" for i in canon["ids"]), store)
    res = {"round_trip": True}
    for label, order in (("list", list_order_route(items)), ("opt", optimized_route(store, items))):
        ev = list(simulate.run(store, items, order))
        res[label] = {"dist": ev[-1].distance, "time": ev[-1].time_s, "speed": 1 / simulate.STEP_SECONDS,
                      "pick": simulate.PICK_SECONDS, "trace": [list(e.cell) for e in ev if e.kind == "move"]}
        if ev[-1].cell != store.start:
            res["round_trip"] = False
    return res


def probe(sc, d, rp):
    m = _map(rp.GRID, (rp.START[1], rp.START[0]), rp.SHELF, rp.NAMES)
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else rp.j(m))
    (d / "l.txt").write_text("\n".join(rp.lines(sc)) + "\n")
    # no runner script exists in the project; run as a module
    return ["-m", "optimizer", "run", str(d / "m.json"), str(d / "l.txt")]
