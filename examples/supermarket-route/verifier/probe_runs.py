#!/usr/bin/env python3
"""Robustness probe through an adapter module. Run from the repository root:

  python3 examples/supermarket-route/verifier/probe_runs.py <name>=<project folder>:<adapter.py> ...

Each adapter's probe(scenario, temp_dir, probe_module) writes the probe store in the project's own formats
and returns the CLI argv (script path relative to the project, or "-m", "<package>", ...).
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import robustness_probe as rp  # noqa: E402

print("| run | " + " | ".join(rp.SCENARIOS) + " | handled |")
print("|" + " --- |" * (2 + len(rp.SCENARIOS)))
for arg in sys.argv[1:]:
    name, rest = arg.split("=", 1)
    project, adapter = rest.rsplit(":", 1)
    project = str(Path(project).resolve())
    spec = importlib.util.spec_from_file_location("a_" + name.replace("-", "_"), adapter)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    res = []
    for sc in rp.SCENARIOS:
        with tempfile.TemporaryDirectory() as t:
            argv = mod.probe(sc, Path(t), rp)
            if argv[0] != "-m":
                argv[0] = str(Path(project) / argv[0])
            res.append(rp.classify(sc, argv, project))
    good = sum(r in rp.GOOD[sc] for r, sc in zip(res, rp.SCENARIOS))
    print(f"| {name} | " + " | ".join(res) + f" | {good} of {len(rp.SCENARIOS)} |")
