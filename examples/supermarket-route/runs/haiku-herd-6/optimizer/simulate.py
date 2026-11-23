"""Step-by-step simulation of the picker walking the aisles.

Each grid step costs STEP_SECONDS; each pick costs PICK_SECONDS. Every event carries the
running KPIs, so they can be shown live.
"""
from dataclasses import dataclass
from typing import Optional

from optimizer.plan import list_order_route, optimized_route

STEP_SECONDS = 1.0
PICK_SECONDS = 2.0


@dataclass(frozen=True)
class Event:
    kind: str  # "move", "pick" or "ready" (back at the start, basket complete)
    cell: tuple
    distance: int  # steps walked so far
    time_s: float  # time to prepare the basket so far
    picked_count: int
    picked_id: Optional[str] = None


def run(store, items, order):
    """Yield one Event per grid step, pick and the final hand-over at the start."""
    cell, distance, picked, time_s = store.start, 0, 0, 0.0
    for k in list(order) + [None]:
        target = store.start if k is None else items[k].cell
        path = store.path(cell, target)
        for step in path[1:]:
            distance += 1
            time_s += STEP_SECONDS
            cell = step
            yield Event("move", cell, distance, time_s, picked)
        if k is None:
            yield Event("ready", cell, distance, time_s, picked)
        else:
            picked += 1
            time_s += PICK_SECONDS
            yield Event("pick", cell, distance, time_s, picked, items[k].id)


def kpis(events):
    if not events:
        return {"time_to_prepare_basket_s": 0.0, "distance_steps": 0, "items_picked": 0}
    last = events[-1]
    return {
        "time_to_prepare_basket_s": last.time_s,
        "distance_steps": last.distance,
        "items_picked": last.picked_count,
    }


def compare(store, items):
    result = {}
    for name, order in (("list", list_order_route(items)), ("optimized", optimized_route(store, items))):
        result[name] = kpis(list(run(store, items, order)))
    base = result["list"]["time_to_prepare_basket_s"]
    opt = result["optimized"]["time_to_prepare_basket_s"]
    result["saving_pct"] = 100.0 * (1 - opt / base) if base else 0.0
    return result
