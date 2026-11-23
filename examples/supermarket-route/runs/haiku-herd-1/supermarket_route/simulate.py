"""Step-by-step simulation of a route, with the two KPIs: time-to-prepare-basket and distance-covered."""
from supermarket_route.planner import path_to, route, search


def simulate(model, order, walk_seconds=1.0, pick_seconds=3.0):
    """Yield one dict per step: start, each cell moved into, and each pick. Simulated clock in seconds."""
    store = model.store
    cell = store.entrance
    t, distance, step = 0.0, 0, 0
    yield {"step": step, "event": "start", "row": cell[0], "col": cell[1], "t": t, "distance_covered": distance}
    for index in order:
        target = model.picks[index - 1]
        _, parent = search(store, cell)
        for nxt in path_to(parent, cell, target):
            t += walk_seconds
            distance += 1
            step += 1
            yield {"step": step, "event": "move", "row": nxt[0], "col": nxt[1],
                   "t": t, "distance_covered": distance}
        t += pick_seconds
        step += 1
        yield {"step": step, "event": "pick", "row": target[0], "col": target[1], "t": t,
               "distance_covered": distance, "product_id": model.items[index - 1].id}
        cell = target


def kpis(steps):
    """Recount the KPIs from the trace: last pick time, and the number of moves."""
    moves, last_pick = 0, 0.0
    for s in steps:
        if s["event"] == "move":
            moves += 1
        elif s["event"] == "pick":
            last_pick = s["t"]
    return {"time_to_prepare_basket": last_pick, "distance_covered": moves}


def compare(model, walk_seconds=1.0, pick_seconds=3.0, on_step=None):
    """Simulate the list-order and the optimized route for the same basket and compare their KPIs."""
    results = {}
    for label, mode in (("list_order", "list"), ("optimized", "optimized")):
        steps = []
        for step in simulate(model, route(model, mode), walk_seconds, pick_seconds):
            steps.append(step)
            if on_step:
                on_step(label, step)
        results[label] = kpis(steps)
    list_time = results["list_order"]["time_to_prepare_basket"]
    opt_time = results["optimized"]["time_to_prepare_basket"]
    saving = 100.0 * (list_time - opt_time) / list_time if list_time else 0.0
    return {"list_order": results["list_order"], "optimized": results["optimized"], "saving_pct": saving}
