#!/usr/bin/env python3
"""Robustness and size probe for the two packaged solutions (run from the repo root).

Feeds each solution the same small store with six scenarios (a normal run, an unknown product, a
duplicate, an empty list, an unreachable product, a malformed map) through its own CLI, and counts
code, tests and docstrings. Outcome per scenario: ok / clean error (non-zero, no traceback) /
CRASH (traceback) / HANG (timeout) / silent (exit 0 on an invalid input).
"""
import ast
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
GRID = ["###########",
        "#.......#.#",   # (9,1) is a walkable pocket sealed off by walls
        "#...#...###",   # (4,2) and (8,2) are shelves
        "#.........#",
        "###########"]
START = (1, 1)
SCENARIOS = ["normal", "unknown_id", "duplicate_id", "empty_list", "unreachable", "malformed_map"]
ITEMS = {"normal": ["P1", "P2"], "unknown_id": ["P1", "P99"], "duplicate_id": ["P1", "P1"],
         "empty_list": [], "unreachable": ["P1", "P3"], "malformed_map": ["P1", "P2"]}
NAMES = {"P1": "milk", "P2": "eggs", "P3": "tea", "P99": "ghost"}
# walkable-cell positions (x, y) and shelf cells (row, col) per product
CELL = {"P1": (4, 1), "P2": (6, 3), "P3": (9, 1)}
SHELF = {"P1": (2, 4), "P2": (2, 8), "P3": (1, 10)}


def lines(sc):
    return [f"{p}:{NAMES[p]}" for p in ITEMS[sc]]


def j(o):
    return json.dumps(o)


def a_without_herd(sc, d):  # router.py run store.json list.txt: grid with S, products {id: {name, pos [r, c]}}
    g = list(GRID)
    g[1] = g[1][:1] + "S" + g[1][2:]
    m = {"grid": g, "products": {p: {"name": NAMES[p], "pos": [CELL[p][1], CELL[p][0]]} for p in CELL}}
    (d / "store.json").write_text("{bad" if sc == "malformed_map" else j(m))
    (d / "l.txt").write_text("\n".join(lines(sc)) + "\n")
    return ["router.py", "run", str(d / "store.json"), str(d / "l.txt")]


def a_with_herd(sc, d):  # router.py map.json list.txt: start [r, c], products [{id, name, pos [r, c]}]
    m = {"grid": GRID, "start": [START[1], START[0]],
         "products": [{"id": p, "name": NAMES[p], "pos": [CELL[p][1], CELL[p][0]]} for p in CELL]}
    (d / "m.json").write_text("{bad" if sc == "malformed_map" else j(m))
    (d / "l.txt").write_text("\n".join(lines(sc)) + "\n")
    return ["router.py", str(d / "m.json"), str(d / "l.txt")]


SOLUTIONS = {
    "With Herd": ("with-herd", "router.py", ".", a_with_herd),
    "Without Herd": ("without-herd", "router.py", ".", a_without_herd),
}


def classify(sc, argv, cwd):
    try:
        p = subprocess.run([sys.executable, *argv], cwd=cwd, capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return "HANG"
    out = p.stdout + p.stderr
    if "Traceback" in out:
        return "CRASH"
    if sc == "normal":  # exit 1 can be a correct "target not met" on this tiny store
        return "ok" if p.returncode in (0, 1) and p.stdout.strip() else "FAILS"
    if p.returncode == 0:
        return "ok" if sc in ("duplicate_id", "empty_list") else "silent"
    return "clean error"


GOOD = {"normal": {"ok"}, "unknown_id": {"clean error"}, "duplicate_id": {"ok", "clean error"},
        "empty_list": {"ok", "clean error"}, "unreachable": {"clean error"}, "malformed_map": {"clean error"}}


def size(folder, code_file, tests):
    root = HERE / folder
    src = (root / code_file).read_text()
    tree = ast.parse(src)
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    documented = sum(ast.get_docstring(f) is not None for f in funcs)
    test_files = list((root / tests).glob("test_*.py")) if tests != "." else list(root.glob("test_*.py"))
    tsrc = "".join(f.read_text() for f in test_files)
    code = sum(1 for l in src.splitlines() if l.strip() and not l.strip().startswith("#"))
    tcode = sum(1 for l in tsrc.splitlines() if l.strip() and not l.strip().startswith("#"))
    n_tests = len(re.findall(r"def test_\w+", tsrc)) or len(re.findall(r"^def test_|^def check_|\bassert\b", tsrc, re.M))
    return code, tcode, n_tests, len(funcs), documented


def main():
    print("| solution | code lines | test lines | tests | functions documented | " + " | ".join(SCENARIOS) + " | handled |")
    print("|" + " --- |" * (6 + len(SCENARIOS)))
    for name, (folder, script, tests, adapter) in SOLUTIONS.items():
        res = []
        for sc in SCENARIOS:
            with tempfile.TemporaryDirectory() as t:
                d = Path(t)
                argv = adapter(sc, d)
                argv[0] = str(HERE / folder / argv[0])
                res.append(classify(sc, argv, HERE / folder))
        code, tcode, n, nf, nd = size(folder, script, tests)
        good = sum(r in GOOD[sc] for r, sc in zip(res, SCENARIOS))
        print(f"| {name} | {code} | {tcode} | {n} | {nd} of {nf} | " + " | ".join(res) + f" | {good} of {len(SCENARIOS)} |")


if __name__ == "__main__":
    main()
