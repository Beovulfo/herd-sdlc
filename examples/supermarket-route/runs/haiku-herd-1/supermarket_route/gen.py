"""Seeded synthetic supermarkets and baskets, for the tests and the benchmark."""
import random

from supermarket_route.layout import parse_map
from supermarket_route.planner import search

SHAPES = ("aisles", "open", "maze")


def generate_store(shape, width, height, seed, products=40):
    """A width x height map of one of SHAPES, with the entrance bottom-left and products on shelf cells."""
    if shape not in SHAPES:
        raise ValueError(f"unknown shape {shape!r}")
    rng = random.Random(seed)
    grid = [["#"] * width for _ in range(height)]
    if shape == "aisles":
        # Shelf rows every third row, aisles between them, open corridors at both sides.
        for r in range(1, height - 1):
            for c in range(1, width - 1):
                grid[r][c] = "#" if r % 3 == 1 and 2 <= c <= width - 3 else "."
    elif shape == "open":
        for r in range(1, height - 1):
            for c in range(1, width - 1):
                grid[r][c] = "."
        for r in range(1, height - 2):
            for c in range(1, width - 2):
                if rng.random() < 0.08:
                    grid[r][c] = grid[r + 1][c] = grid[r][c + 1] = grid[r + 1][c + 1] = "#"
    else:  # maze: random blocked cells, so some areas are cut off
        for r in range(1, height - 1):
            for c in range(1, width - 1):
                grid[r][c] = "#" if rng.random() < 0.3 else "."
    entrance = (height - 2, 1)
    grid[entrance[0]][entrance[1]] = "E"
    rows = ["".join(row) for row in grid]

    reachable, _ = search(parse_map({"grid": rows, "products": []}), entrance)
    candidates = [
        (r, c) for r in range(1, height - 1) for c in range(1, width - 1)
        if rows[r][c] == "#" and any((r + dr, c + dc) in reachable
                                     for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)))
    ]
    chosen = rng.sample(candidates, min(products, len(candidates)))
    items = [{"id": f"P{i:04d}", "short_name": f"item {i}", "row": r, "col": c}
             for i, (r, c) in enumerate(chosen)]
    return parse_map({"grid": rows, "products": items})


def random_basket(store, n, seed):
    """A random shopping list as 'id:short name' text, in random order, with duplicates only if n > products."""
    rng = random.Random(seed)
    ids = sorted(store.products)
    picked = rng.sample(ids, n) if n <= len(ids) else [rng.choice(ids) for _ in range(n)]
    return "".join(f"{pid}:{store.products[pid].short_name}\n" for pid in picked)
