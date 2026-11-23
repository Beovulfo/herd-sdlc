"""Shared helpers for the route optimizer tests (stdlib only)."""
import os
import subprocess
import sys

from route_optimizer import parse_store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "route_optimizer.py")

COMB = [
    "##########",
    "#.#.#.#..#",
    "#.#.#.#..#",
    "#........#",
    "##########",
]

MAZE = [
    "#########",
    "#.......#",
    "#.#####.#",
    "#.#...#.#",
    "#.#.#.#.#",
    "#...#...#",
    "#########",
]


def store_from(rows, entrance, products):
    """products: list of (id, short name, x, y)."""
    return parse_store({
        "grid": rows,
        "entrance": {"x": entrance[0], "y": entrance[1]},
        "products": [{"id": i, "name": n, "x": x, "y": y} for i, n, x, y in products],
    })


def run_cli(*args):
    import subprocess as sp
    return sp.run([sys.executable, CLI, *args], capture_output=True, text=True, cwd=ROOT)
