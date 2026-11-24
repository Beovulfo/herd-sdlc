#!/usr/bin/env python3
"""Hidden general acceptance check for the bus-transfer task ("any network, even very big ones").

It never reads the agent's code for correctness. It generates bus networks from six families
(hand cases, random, grid, radial, clusters, overnight) at four sizes, asks the solution through a
small adapter for the earliest-arrival journey of several queries per network, validates every
journey against the timetable itself, and compares the arrival with its own oracle. A case is valid
when it finishes in time and every query is right: a real journey that leaves at or after the
departure time, respects the change time, arrives when the oracle says, and "not possible" only when
the oracle finds nothing.

Usage:
  bus_verify.py ADAPTER PROJECT_DIR [--tiers S,M] [--seeds 2] [--families a,b] [--limit-scale 1.0] [--json FILE]
ADAPTER is reference, static or nochange (bus_reference.py, to test this verifier), or file:PATH to an
adapter module with worker(project, canon) -> {"answers": [...]}. See ADAPTER_SPEC.md. Standard library only.
"""
import argparse
import json
import random
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bus_reference  # noqa: E402

TIERS = {  # name: (stops, queries per network, seconds allowed per network)
    "S": (14, 6, 20),
    "M": (120, 6, 60),
    "L": (1500, 4, 120),
    "XL": (6000, 3, 240),
}
FAMILIES = ["hand", "random", "grid", "radial", "clusters", "overnight"]
MIN_CHANGE = 4
DAY_START, DAY_END, LAST_TIME = 300, 1440, 1800  # service window; no time is later than 30:00


# ---- the oracle: a connection scan, written apart from the reference solver ---------------------

def validate_canon(canon):
    """Raise ValueError when the network is not one this verifier can judge."""
    ids = [s[0] for s in canon["stops"]]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate stop id")
    trip_ids = [t["id"] for t in canon["trips"]]
    if len(set(trip_ids)) != len(trip_ids):
        raise ValueError("duplicate trip id")
    for t in canon["trips"]:
        stops = [x[0] for x in t["times"]]
        if len(set(stops)) != len(stops) or not set(stops) <= set(ids):
            raise ValueError(f"trip {t['id']}: repeated or unknown stop")
        for x, y in zip(t["times"], t["times"][1:]):
            if not (x[1] <= x[2] < y[1] <= y[2] <= LAST_TIME):
                raise ValueError(f"trip {t['id']}: times do not move forward")


def oracle_arrival(canon, query, min_change=None):
    """Earliest arrival in minutes, or None when no journey exists. Connection scan, arrival only."""
    m = canon["min_change"] if min_change is None else min_change
    a, b, depart = query["from"], query["to"], query["depart"]
    if a == b:
        return depart
    conns = []
    for t in canon["trips"]:
        x = t["times"]
        conns += [(p[2], q[1], p[0], q[0], t["id"]) for p, q in zip(x, x[1:])]
    conns.sort()
    ready, best, boarded = {a: depart}, {}, set()
    for dep, arr, frm, to, trip in conns:
        if dep >= best.get(b, LAST_TIME + 1):
            break
        if trip in boarded or ready.get(frm, LAST_TIME + 1) <= dep:
            boarded.add(trip)
            best[to] = min(best.get(to, LAST_TIME + 1), arr)
            ready[to] = min(ready.get(to, LAST_TIME + 1), arr + m)
    return best.get(b)


def static_reachable(canon, a, b):
    """True when a bus path from a to b exists at all, ignoring every time."""
    nxt = {}
    for t in canon["trips"]:
        s = [x[0] for x in t["times"]]
        for i, x in enumerate(s):
            nxt.setdefault(x, set()).update(s[i + 1:])
    seen, todo = {a}, [a]
    while todo:
        for y in nxt.get(todo.pop(), ()):
            if y not in seen:
                seen.add(y)
                todo.append(y)
    return b in seen


# ---- generators -------------------------------------------------------------------------------

def _stop_ids(n):
    return [f"S{i:04d}" for i in range(n)]


def _add_route(trips, name, seq, rnd, first, last, headway, speed=(2, 9)):
    """Trips of one route from first to last at about the headway; a trip may run slower (overtaking)."""
    hop = [rnd.randint(*speed) for _ in seq[1:]]
    t0 = first + rnd.randrange(headway)
    k = 0
    while t0 <= last:
        slow = rnd.random() < 0.2
        t, times = t0, []
        for j, stop in enumerate(seq):
            if j:
                t += hop[j - 1] + (rnd.randint(1, 6) if slow else 0)
            times.append([stop, t, t])  # one time per stop: a timetable with a single time column loses nothing
        if t <= LAST_TIME:
            trips.append({"id": f"{name}.{k}", "route": name, "times": times})
        k += 1
        t0 += max(1, headway + rnd.randint(-2, 2))


def _routes_random(ids, rnd, n_routes):
    return [rnd.sample(ids, rnd.randint(3, min(12, len(ids)))) for _ in range(n_routes)]


def _routes_grid(ids, rnd, n_routes):
    side = max(2, int(len(ids) ** 0.5))
    cell = lambda r, c: ids[r * side + c]  # noqa: E731
    rows = [[cell(r, c) for c in range(side)] for r in range(side)]
    cols = [[cell(r, c) for r in range(side)] for c in range(side)]
    lines = rows + cols
    return lines + [x[::-1] for x in lines]


def _routes_radial(ids, rnd, n_routes):
    hub, rest = ids[0], ids[1:]
    k = max(3, len(rest) // 10)  # short spokes, so a trip ends within the day at every size
    spokes = [rest[i::k] for i in range(k)]
    routes = [s[::-1] + [hub] + spokes[(i + 1) % k] for i, s in enumerate(spokes)]
    ring = [s[-1] for s in spokes]
    ring.append(ring[0])
    arcs = [list(dict.fromkeys(ring[i:i + 12])) for i in range(0, len(ring) - 1, 11)]
    return routes + arcs + [a[::-1] for a in arcs]


def _routes_clusters(ids, rnd, n_routes):
    k = max(2, min(6, len(ids) // 5))
    groups = [ids[i::k] for i in range(k)]
    routes = []
    for g in groups:
        routes += [rnd.sample(g, rnd.randint(2, min(8, len(g)))) for _ in range(max(1, n_routes // k))]
    links = k - 1 if rnd.random() < 0.5 else k - 2  # sometimes the last cluster stays cut off
    routes += [[groups[i][0], groups[i + 1][0]] for i in range(max(0, links))]
    return routes


ROUTE_MAKERS = {"random": _routes_random, "grid": _routes_grid, "radial": _routes_radial,
                "clusters": _routes_clusters, "overnight": _routes_random}


def _queries(canon, n, rnd, late):
    """Up to n queries inside the service window, about a third of them with no bus path at all.
    Never a query that fails only by time of day: whether a timetable repeats the next day is open."""
    ids = [s[0] for s in canon["stops"]]
    out, none_left = [], max(1, n // 3)
    for _ in range(60 * n):
        if len(out) == n:
            break
        a, b = rnd.choice(ids), rnd.choice(ids)
        depart = rnd.randint(1260, 1439) if late else rnd.randint(DAY_START, DAY_END - 120)
        q = {"from": a, "to": b, "depart": depart}
        if oracle_arrival(canon, q) is not None:
            out.append(q)
        elif none_left and not static_reachable(canon, a, b):
            out.append(q)
            none_left -= 1
    return out


def make_case(family, tier, seed):
    """One network and its queries; the same arguments always give the same case."""
    n_stops, n_queries, _ = TIERS[tier]
    rnd = random.Random(f"{family}/{tier}/{seed}")
    ids = _stop_ids(n_stops)
    late = family == "overnight"
    first, last = (1200, 1500) if late else (DAY_START, DAY_END - 30)
    routes = ROUTE_MAKERS[family](ids, rnd, max(3, n_stops // 5))
    headway = rnd.choice((10, 15, 20, 30)) if not late else rnd.choice((15, 25, 40))
    trips = []
    for i, seq in enumerate(routes):
        _add_route(trips, f"R{i}", seq, rnd, first, last, headway)
    canon = {"family": family, "tier": tier, "seed": seed, "min_change": MIN_CHANGE,
             "stops": [[s, f"Stop {s[1:]}"] for s in ids], "trips": trips}
    canon["queries"] = _queries(canon, n_queries, rnd, late)
    return canon


def _hand(name, trips, queries, stops="ABCDE"):
    return {"family": "hand", "tier": "S", "seed": name, "min_change": MIN_CHANGE,
            "stops": [[s, f"Stop {s}"] for s in stops], "queries": queries,
            "trips": [{"id": i, "route": i.split(".")[0],
                       "times": [[s, a, d] for s, a, d in t]} for i, t in trips.items()]}


def hand_cases():
    """Small cases built by hand, each aimed at one mistake. Times are minutes since midnight."""
    q = lambda a, b, d: {"from": a, "to": b, "depart": d}  # noqa: E731
    return [
        # a static graph picks A-C-B (20 minutes of riding), but the bus C-B has left: the direct bus is the way
        _hand("static-trap", {"X.0": [("A", 540, 540), ("C", 550, 550)], "Y.0": [("C", 551, 551), ("B", 560, 560)],
                              "Z.0": [("A", 560, 560), ("B", 620, 620)]}, [q("A", "B", 540)]),
        # the first change is 2 minutes, the minimum is 4: the 9:12 bus cannot be taken, the 9:30 one can
        _hand("tight-change", {"X.0": [("A", 540, 540), ("B", 550, 550)], "Y.0": [("B", 552, 552), ("C", 560, 560)],
                               "Y.1": [("B", 570, 570), ("C", 580, 580)]}, [q("A", "C", 540)]),
        # staying on one bus through a stop needs no change time, even with no dwell
        _hand("stay-on-bus", {"X.0": [("A", 540, 540), ("B", 550, 550), ("C", 560, 560)]}, [q("A", "C", 540)]),
        # past midnight: the last bus runs 24:30 to 25:10
        _hand("overnight", {"X.0": [("A", 1470, 1470), ("B", 1480, 1480)], "Y.0": [("B", 1490, 1490), ("C", 1510, 1510)]},
              [q("A", "C", 1430)]),
        # the first bus is hours away: wait at the start
        _hand("wait", {"X.0": [("A", 540, 540), ("B", 560, 560)]}, [q("A", "B", 420)]),
        # two parts of the city with no bus between them, and a trip from a stop to itself
        _hand("disconnected", {"X.0": [("A", 540, 540), ("B", 550, 550)], "Y.0": [("D", 540, 540), ("E", 550, 550)]},
              [q("A", "E", 500), q("B", "B", 600), q("E", "D", 500)]),
        # a slow bus leaves first, a fast bus leaves later and arrives first
        _hand("overtaking", {"X.0": [("A", 540, 540), ("B", 640, 640)], "Y.0": [("A", 550, 550), ("B", 580, 580)]},
              [q("A", "B", 540)]),
        # the best way changes twice, at B then C, with exactly 4 minutes at each change
        _hand("two-changes", {"X.0": [("A", 540, 540), ("B", 550, 550)], "Y.0": [("B", 554, 554), ("C", 565, 565)],
                              "Z.0": [("C", 569, 569), ("D", 580, 580)]}, [q("A", "D", 540)]),
    ]


def make_cases(tiers, families, seeds):
    """(label, canon) for every requested tier, family and seed. Hand cases belong to tier S only."""
    out = []
    for tier in tiers:
        for fam in families:
            if fam == "hand":
                out += [(f"{tier} hand {c['seed']}", c) for c in hand_cases()] if tier == "S" else []
                continue
            for seed in range(seeds if tier in ("S", "M") else 1):
                out.append((f"{tier} {fam} seed {seed}", make_case(fam, tier, 7000 + seed)))
    return out


# ---- validating one answer ------------------------------------------------------------------

def merge_legs(legs):
    """Merge neighbouring legs on one trip, so one leg per ride and per stop-to-stop hop are read alike."""
    out = []
    for leg in legs:
        if out and out[-1]["trip"] == leg["trip"] and out[-1]["to"] == leg["from"] and out[-1]["arr"] <= leg["dep"]:
            out[-1] = {**out[-1], "to": leg["to"], "arr": leg["arr"]}
        else:
            out.append(dict(leg))
    return out


def _check_leg(trips, leg):
    t = trips.get(leg.get("trip"))
    assert t is not None, f"leg uses unknown trip {leg.get('trip')!r}"
    stops = [x[0] for x in t["times"]]
    assert leg["from"] in stops and leg["to"] in stops, f"trip {t['id']} does not serve {leg['from']} and {leg['to']}"
    i, j = stops.index(leg["from"]), stops.index(leg["to"])
    assert i < j, f"trip {t['id']} does not run from {leg['from']} to {leg['to']}"
    assert t["times"][i][2] == leg["dep"], f"trip {t['id']} leaves {leg['from']} at {t['times'][i][2]}, not {leg['dep']}"
    assert t["times"][j][1] == leg["arr"], f"trip {t['id']} reaches {leg['to']} at {t['times'][j][1]}, not {leg['arr']}"


def _check_chain(canon, query, legs):
    assert legs[0]["from"] == query["from"], "journey does not start at the start stop"
    assert legs[0]["dep"] >= query["depart"], "journey leaves before the departure time"
    assert legs[-1]["to"] == query["to"], "journey does not end at the destination"
    for a, b in zip(legs, legs[1:]):
        assert a["to"] == b["from"], f"change at {a['to']} but next leg starts at {b['from']}"
        gap = b["dep"] - a["arr"]
        assert gap >= canon["min_change"], f"change at {a['to']} takes {gap} minutes, minimum is {canon['min_change']}"


def validate_answer(canon, query, answer, expected):
    """Raise AssertionError with a reason unless the answer is right. expected is the oracle's arrival or None."""
    assert isinstance(answer, dict) and isinstance(answer.get("found"), bool), "answer has no found flag"
    if not answer["found"]:
        assert expected is None, f"said not possible, but a journey arrives at {expected}"
        return
    assert expected is not None, "gave a journey where none is possible"
    trips = {t["id"]: t for t in canon["trips"]}
    given = answer.get("legs") or []
    for leg in given:  # each leg as reported, before merging could hide a made-up intermediate stop or time
        _check_leg(trips, leg)
    legs = merge_legs(given)
    if not legs:
        assert query["from"] == query["to"], "journey has no legs"
        arrival = query["depart"]
    else:
        _check_chain(canon, query, legs)
        arrival = legs[-1]["arr"]
    assert answer.get("arrival") == arrival, f"reported arrival {answer.get('arrival')} but the legs arrive at {arrival}"
    assert arrival == expected, f"arrives at {arrival}, the earliest is {expected}"


def check_case(canon, result):
    """None when every query of the case is right, else the first reason."""
    answers = result.get("answers") if isinstance(result, dict) else None
    if not isinstance(answers, list) or len(answers) != len(canon["queries"]):
        return "wrong number of answers"
    for i, (q, ans) in enumerate(zip(canon["queries"], answers)):
        try:
            validate_answer(canon, q, ans, oracle_arrival(canon, q))
        except Exception as e:  # the answer is untrusted program output: whatever it breaks is a wrong answer
            return f"query {i} ({q['from']} to {q['to']} at {q['depart']}): {type(e).__name__ if not str(e) else e}"
    return None


# ---- running an adapter ---------------------------------------------------------------------

def run_worker(adapter, project, canon, limit):
    """(result or None, wall seconds, status) with the adapter in its own process under a time limit."""
    with tempfile.TemporaryDirectory() as t:
        cp, op = Path(t) / "canon.json", Path(t) / "out.json"
        cp.write_text(json.dumps(canon))
        t0 = time.time()
        try:
            p = subprocess.run([sys.executable, __file__, "--worker", adapter, str(project), str(cp), str(op)],
                               capture_output=True, text=True, timeout=limit)
        except subprocess.TimeoutExpired:
            return None, time.time() - t0, "timeout"
        wall = time.time() - t0
        if p.returncode != 0 or not op.exists():
            return None, wall, "crash: " + (p.stderr.strip().splitlines() or ["?"])[-1][:100]
        return json.loads(op.read_text()), wall, "ok"


def run_adapter_module(path, project, canon_path, out_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("bench_adapter", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    Path(out_path).write_text(json.dumps(mod.worker(Path(project), json.loads(Path(canon_path).read_text()))))


def score(adapter, project, label, canon, limit_scale):
    """One result row for one case."""
    limit = TIERS[canon["tier"]][2] * limit_scale
    result, wall, status = run_worker(adapter, project, canon, limit)
    why = check_case(canon, result) if status == "ok" else None
    return {"case": label, "tier": canon["tier"], "family": canon["family"], "queries": len(canon["queries"]),
            "wall": round(wall, 2), "status": status, "invalid": why, "valid": status == "ok" and why is None}


def report(rows, tiers, families):
    """Print the tables and return the number of valid cases."""
    print("| tier | cases | finished in time | valid | median wall (s) |\n| --- | --- | --- | --- | --- |")
    for tier in tiers:
        rs = [r for r in rows if r["tier"] == tier]
        done = [r for r in rs if r["status"] == "ok"]
        med = f"{statistics.median(r['wall'] for r in done):.1f}" if done else "n/a"
        print(f"| {tier} | {len(rs)} | {len(done)} of {len(rs)} | {sum(r['valid'] for r in rs)} of {len(rs)} | {med} |")
    print("\nBy family (valid cases):")
    for fam in families:
        rs = [r for r in rows if r["family"] == fam]
        print(f"- {fam}: {sum(r['valid'] for r in rs)} of {len(rs)}")
    for r in rows:
        if not r["valid"]:
            print(f"! {r['case']}: {r['invalid'] or r['status']} ({r['wall']:.0f}s)")
    valid = sum(r["valid"] for r in rows)
    print(f"CASES valid {valid} of {len(rows)}")
    print("RESULT:", "PASS" if valid == len(rows) else "FAIL", "(every case finished in time with right answers)")
    return valid


def parse(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("adapter")
    ap.add_argument("project")
    ap.add_argument("--tiers", default="S,M")
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--families", default=",".join(FAMILIES))
    ap.add_argument("--limit-scale", type=float, default=1.0)
    ap.add_argument("--json")
    return ap.parse_args(argv)


def refusal(a):
    """A one-line reason the arguments cannot be used, or None."""
    tiers, fams = a.tiers.split(","), a.families.split(",")
    if not set(tiers) <= set(TIERS) or not set(fams) <= set(FAMILIES):
        return f"unknown tier or family; tiers {','.join(TIERS)}, families {','.join(FAMILIES)}"
    if a.seeds < 1 or a.limit_scale <= 0:
        return "--seeds must be at least 1 and --limit-scale above 0"
    if not Path(a.project).is_dir():
        return f"project folder {a.project} does not exist"
    if a.adapter.startswith("file:") and not Path(a.adapter[5:]).is_file():
        return f"adapter file {a.adapter[5:]} does not exist"
    if not a.adapter.startswith("file:") and a.adapter not in bus_reference.SOLVERS:
        return f"unknown adapter {a.adapter!r}; use {', '.join(bus_reference.SOLVERS)} or file:PATH"
    return None


def main(argv=None):
    a = parse(argv)
    why = refusal(a)
    if why:
        print(f"bus_verify: {why}", file=sys.stderr)
        return 2
    tiers, fams = a.tiers.split(","), a.families.split(",")
    rows = [score(a.adapter, a.project, label, canon, a.limit_scale) for label, canon in make_cases(tiers, fams, a.seeds)]
    valid = report(rows, tiers, fams)
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=1))
    return 0 if valid == len(rows) else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        _, _, name, project, cp, op = sys.argv
        if name.startswith("file:"):
            run_adapter_module(name[5:], project, cp, op)
        else:
            bus_reference.worker(name, json.loads(Path(cp).read_text()), op)
        sys.exit(0)
    sys.exit(main())
