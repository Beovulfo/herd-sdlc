#!/usr/bin/env python3
"""Robustness probe for the bus-transfer task: six bad inputs through a solution's own CLI.

  python3 bus_probe.py <name>=<project folder>:<adapter.py> ...

An adapter's probe(scenario, temp_dir, probe_module) writes the scenario in the project's own file formats
and returns the CLI argv (script path relative to the project, or "-m", "<package>", ...). See ADAPTER_SPEC.md.
Outcome per scenario: ok / clean error (non-zero, no traceback) / CRASH (traceback) / HANG (timeout) /
silent (exit 0 on an invalid input) / FAILS (the normal scenario gave no journey).
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCENARIOS = ["normal", "missing_file", "malformed_timetable", "unknown_stop", "empty_network", "bad_departure",
             "duplicate_stop_ids"]
BAD = SCENARIOS[1:]  # the six bad inputs
MALFORMED = "{bad"
STOPS = [["A", "Alder Road"], ["B", "Bridge Street"], ["C", "Church Lane"]]
TRIPS = [{"id": "X.0", "route": "X", "times": [["A", 540, 540], ["B", 550, 550]]},
         {"id": "Y.0", "route": "Y", "times": [["B", 560, 560], ["C", 575, 575]]}]
MIN_CHANGE = 4


def canon(sc):
    """The network for a scenario, in the verifier's canon format (stops may repeat an id for duplicate_stop_ids)."""
    stops = [list(s) for s in STOPS]
    if sc == "empty_network":
        return {"stops": [], "trips": [], "min_change": MIN_CHANGE}
    if sc == "duplicate_stop_ids":
        stops.append(["B", "Bridge Street again"])
    return {"stops": stops, "trips": [dict(t) for t in TRIPS], "min_change": MIN_CHANGE}


def query(sc):
    """(start, destination, departure text) for a scenario. The text is a clock time, 08:30 unless it is bad."""
    return "A", ("Z9" if sc == "unknown_stop" else "C"), ("half past eight" if sc == "bad_departure" else "08:30")


def j(obj):
    return json.dumps(obj)


def classify(sc, argv, cwd, timeout=20):
    try:
        p = subprocess.run([sys.executable, *argv], cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "HANG"
    out = p.stdout + p.stderr
    if "Traceback" in out:
        return "CRASH"
    if sc == "normal":
        return "ok" if p.returncode == 0 and p.stdout.strip() else "FAILS"
    return "silent" if p.returncode == 0 else "clean error"


GOOD = {"normal": {"ok"}, **{sc: {"clean error"} for sc in BAD}}


def run_probe(project, mod, timeout=20):
    """Outcome of each scenario for one project and its adapter module."""
    res = []
    for sc in SCENARIOS:
        with tempfile.TemporaryDirectory() as t:
            argv = mod.probe(sc, Path(t), sys.modules[__name__])
            if argv[0] != "-m":
                argv[0] = str(Path(project) / argv[0])
            res.append(classify(sc, argv, project, timeout))
    return res


def handled(res):
    """How many of the six bad inputs ended in a clean error; 0 when the normal scenario is not ok."""
    if res[0] != "ok":
        return 0
    return sum(r in GOOD[sc] for r, sc in zip(res, SCENARIOS) if sc != "normal")


def load_adapter(name, path):
    spec = importlib.util.spec_from_file_location("a_" + name.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(argv):
    print("| run | " + " | ".join(SCENARIOS) + " | handled |")
    print("|" + " --- |" * (2 + len(SCENARIOS)))
    for arg in argv:
        name, _, rest = arg.partition("=")
        project, _, adapter = rest.rpartition(":")
        if not (name and project and adapter and Path(project).is_dir() and Path(adapter).is_file()):
            print(f"bus_probe: expected NAME=PROJECT_DIR:ADAPTER.py with both paths existing, got {arg!r}", file=sys.stderr)
            return 2
        res = run_probe(str(Path(project).resolve()), load_adapter(name, adapter))
        print(f"| {name} | " + " | ".join(res) + f" | {handled(res)} of {len(BAD)} |")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
