"""Shared fixtures and helpers for the supermarket_route tests."""
import os
import re
import subprocess
import sys
from collections import deque

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# One aisle: entrance E at (1, 1), aisle cells (1, 2)..(1, 5).
# A1 sits on the shelf cell above (1, 2), C3 above (1, 4), B2 below (1, 5).
HANDMADE = {
    "grid": ["#######", "#E....#", "#######"],
    "products": [
        {"id": "A1", "short_name": "apples", "row": 0, "col": 2},
        {"id": "C3", "short_name": "cheese", "row": 0, "col": 4},
        {"id": "B2", "short_name": "bread", "row": 2, "col": 5},
    ],
}
HANDMADE_LIST = "A1:apples\nB2:bread\nC3:cheese\n"


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "supermarket_route", *args],
        cwd=ROOT, capture_output=True, text=True,
    )


def kpis_from_output(text, label):
    """Parse (time-to-prepare-basket, distance-covered) from a summary line."""
    line = next(ln for ln in text.splitlines() if ln.startswith(label))
    time_m = re.search(r"time-to-prepare-basket=([0-9.]+) s", line)
    dist_m = re.search(r"distance-covered=(\d+) steps", line)
    return float(time_m.group(1)), int(dist_m.group(1))


def steps_between(grid, src, dst):
    """Independent BFS on the raw grid: number of steps from src to dst, or None."""
    walk = {(r, c) for r, row in enumerate(grid) for c, ch in enumerate(row) if ch in ".E"}
    seen = {src: 0}
    queue = deque([src])
    while queue:
        cell = queue.popleft()
        if cell == dst:
            return seen[cell]
        r, c = cell
        for nxt in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if nxt in walk and nxt not in seen:
                seen[nxt] = seen[cell] + 1
                queue.append(nxt)
    return None
