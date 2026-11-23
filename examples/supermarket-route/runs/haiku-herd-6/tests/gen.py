"""Generated supermarket maps for the tests. Not a test module."""
import random

from optimizer.store import parse_store

SHAPES = ("open", "shelves", "ring", "maze")


def _cell(shape, r, c, rows, cols):
    if shape == "open":  # a hall with a grid of pillars
        return "#" if r % 4 == 2 and c % 4 == 2 else "."
    if shape == "shelves":  # shelf rows with a gap every 8 columns
        return "#" if r % 3 == 1 and c % 8 != 0 else "."
    if shape == "ring":  # a 2-wide corridor around a walled island
        return "." if r < 2 or r >= rows - 2 or c < 2 or c >= cols - 2 else "#"
    if shape == "maze":  # serpentine corridor
        if r % 2 == 0:
            return "."
        gap = cols - 1 if (r // 2) % 2 == 0 else 0
        return "." if c == gap else "#"
    raise ValueError(shape)


def make_map(shape, rows, cols, n_products, rng):
    """A map dict in the JSON format of optimizer.store, start at (0, 0)."""
    grid = [[_cell(shape, r, c, rows, cols) for c in range(cols)] for r in range(rows)]
    grid[0][0] = "S"
    spots = [(r, c) for r in range(rows) for c in range(cols) if grid[r][c] == "."]
    chosen = rng.sample(spots, n_products)
    return {
        "layout": ["".join(row) for row in grid],
        "products": [
            {"id": f"P{i:03d}", "name": f"item{i}", "row": r, "col": c}
            for i, (r, c) in enumerate(chosen)
        ],
    }


def make_case(shape, rows, cols, n_products, n_items, seed):
    """Store plus a shopping list of n_items products in random (customer) order."""
    rng = random.Random(seed)
    store = parse_store(make_map(shape, rows, cols, n_products, rng))
    ids = sorted(store.products)
    items = [store.products[i] for i in rng.sample(ids, n_items)]
    return store, items
