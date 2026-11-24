"""Reference solver for the bus-transfer verifier, plus two deliberately wrong solvers that test it.

Used only by bus_verify.py and its tests, never shown to a run. The network is the verifier's canon:
  {"stops": [[id, name], ...], "min_change": minutes,
   "trips": [{"id": str, "route": str, "times": [[stop, arrival, departure], ...]}, ...]}
Times are minutes since midnight and may pass 1440. A query is {"from": stop, "to": stop, "depart": minutes}.
An answer is {"found": bool, "arrival": minutes, "legs": [{"trip", "from", "dep", "to", "arr"}, ...]},
one leg per bus ride.

solve()        earliest arrival by a reachability search over "waiting at a stop" and "on a bus hop" nodes.
solve_static() wrong on purpose: plain Dijkstra on a static stop graph, then it follows that path.
solve_nochange() wrong on purpose: solve() with a minimum change time of 0.
"""
import bisect
import heapq
import json
import sys
from collections import deque
from pathlib import Path


def _connections(canon):
    """Hops (trip, from, dep, to, arr), grouped by trip in stop order, and the departures at each stop."""
    hops = []
    for trip in canon["trips"]:
        t = trip["times"]
        hops += [(trip["id"], a[0], a[2], b[0], b[1]) for a, b in zip(t, t[1:])]
    deps = {}
    for i, h in enumerate(hops):
        deps.setdefault(h[1], []).append((h[2], i))
    for lst in deps.values():
        lst.sort()
    return hops, deps


def _search(canon, query, m):
    """(hops, parent of every reached node, reached hop indexes) of the reachability search."""
    hops, deps = _connections(canon)
    keys = {s: [d for d, _ in lst] for s, lst in deps.items()}

    def wait_node(stop, ready):
        lst = keys.get(stop, [])
        j = bisect.bisect_left(lst, ready)
        return ("W", stop, j) if j < len(lst) else None

    parent, taken = {}, []
    start = wait_node(query["from"], query["depart"])
    todo = deque()
    if start:
        parent[start] = None
        todo.append(start)

    def visit(node, via):
        if node and node not in parent:
            parent[node] = via
            todo.append(node)

    while todo:
        node = todo.popleft()
        if node[0] == "W":
            _, stop, j = node
            visit(("T", deps[stop][j][1]), node)
            visit(wait_node_next(deps, stop, j), node)
            continue
        i = node[1]
        taken.append(i)
        if i + 1 < len(hops) and hops[i + 1][0] == hops[i][0]:
            visit(("T", i + 1), node)
        visit(wait_node(hops[i][3], hops[i][4] + m), node)
    return hops, parent, taken


def wait_node_next(deps, stop, j):
    return ("W", stop, j + 1) if j + 1 < len(deps[stop]) else None


def _legs(hops, parent, node):
    """Ride legs along the parent chain that ends at hop node, one per bus ride."""
    chain = []
    while node:
        if node[0] == "T":
            chain.append(hops[node[1]])
        node = parent[node]
    legs = []
    for trip, a, dep, b, arr in reversed(chain):
        if legs and legs[-1]["trip"] == trip and legs[-1]["to"] == a:
            legs[-1].update({"to": b, "arr": arr})
        else:
            legs.append({"trip": trip, "from": a, "dep": dep, "to": b, "arr": arr})
    return legs


def solve(canon, query, min_change=None):
    """Earliest-arrival answer, or {"found": False}. Staying on one bus needs no change time."""
    m = canon["min_change"] if min_change is None else min_change
    if query["from"] == query["to"]:
        return {"found": True, "arrival": query["depart"], "legs": []}
    hops, parent, taken = _search(canon, query, m)
    ends = [i for i in taken if hops[i][3] == query["to"]]
    if not ends:
        return {"found": False}
    best = min(ends, key=lambda i: hops[i][4])
    legs = _legs(hops, parent, ("T", best))
    return {"found": True, "arrival": legs[-1]["arr"], "legs": legs}


def solve_nochange(canon, query):
    return solve(canon, query, min_change=0)


def _static_path(canon, a, b):
    """Stops of the cheapest path on the static graph, edge cost = shortest ride between two neighbours."""
    cost = {}
    for trip in canon["trips"]:
        t = trip["times"]
        for x, y in zip(t, t[1:]):
            key = (x[0], y[0])
            cost[key] = min(cost.get(key, 10 ** 9), y[1] - x[2])
    out = {}
    for (x, y), c in cost.items():
        out.setdefault(x, []).append((y, c))
    dist, prev, heap = {a: 0}, {}, [(0, a)]
    while heap:
        d, x = heapq.heappop(heap)
        if d > dist.get(x, 10 ** 9):
            continue
        for y, c in out.get(x, []):
            if d + c < dist.get(y, 10 ** 9):
                dist[y], prev[y] = d + c, x
                heapq.heappush(heap, (d + c, y))
    if b not in dist:
        return None
    path = [b]
    while path[-1] != a:
        path.append(prev[path[-1]])
    return path[::-1]


def solve_static(canon, query):
    """Wrong on purpose: fixes the stop path ignoring the timetable, then takes the earliest bus on each hop."""
    a, b = query["from"], query["to"]
    if a == b:
        return {"found": True, "arrival": query["depart"], "legs": []}
    path = _static_path(canon, a, b)
    if path is None:
        return {"found": False}
    hops, deps = _connections(canon)
    ready, legs = query["depart"], []
    for x, y in zip(path, path[1:]):
        options = [hops[i] for d, i in deps.get(x, []) if d >= ready and hops[i][3] == y]
        if not options:
            return {"found": False}
        trip, _, dep, _, arr = min(options, key=lambda h: h[4])
        legs.append({"trip": trip, "from": x, "dep": dep, "to": y, "arr": arr})
        ready = arr + canon["min_change"]
    return {"found": True, "arrival": legs[-1]["arr"], "legs": legs}


SOLVERS = {"reference": solve, "static": solve_static, "nochange": solve_nochange}


def worker(name, canon, out_path):
    """Answer every query of the canon with the named solver and write {"answers": [...]} to out_path."""
    answers = [SOLVERS[name](canon, q) for q in canon["queries"]]
    Path(out_path).write_text(json.dumps({"answers": answers}))


if __name__ == "__main__":
    worker(sys.argv[1], json.loads(Path(sys.argv[2]).read_text()), sys.argv[3])
