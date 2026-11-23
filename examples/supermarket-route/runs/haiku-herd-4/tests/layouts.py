"""Generated store layouts for the tests. Each returns a store dict for Store.from_dict."""
import random


def _products(grid, n, rng):
    open_cells = [(x, y) for y, row in enumerate(grid) for x, ch in enumerate(row) if ch == "."]
    picked = rng.sample(open_cells, n)
    return [{"id": f"P{i:03d}", "name": f"item{i}", "x": x, "y": y} for i, (x, y) in enumerate(picked)]


def _store(grid, n, rng):
    start = next((x, y) for y, row in enumerate(grid) for x, ch in enumerate(row) if ch == ".")
    return {"grid": ["".join(r) for r in grid], "start": list(start), "products": _products(grid, n, rng)}


def open_hall(w, h, n, rng):
    grid = [["."] * w for _ in range(h)]
    return _store(grid, n, rng)


def aisles(w, h, every, n, rng):
    """Shelf columns with cross aisles at the top and bottom rows."""
    grid = [["."] * w for _ in range(h)]
    for x in range(w):
        if x % every == 1:
            for y in range(1, h - 1):
                grid[y][x] = "#"
    return _store(grid, n, rng)


def maze(w, h, n, rng):
    """Carved perfect maze on odd coordinates: every open cell is reachable."""
    grid = [["#"] * w for _ in range(h)]
    grid[1][1] = "."
    stack = [(1, 1)]
    while stack:
        x, y = stack[-1]
        steps = [(x + dx, y + dy) for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2))]
        steps = [(nx, ny) for nx, ny in steps if 1 <= nx < w - 1 and 1 <= ny < h - 1 and grid[ny][nx] == "#"]
        if not steps:
            stack.pop()
            continue
        nx, ny = rng.choice(steps)
        grid[(y + ny) // 2][(x + nx) // 2] = "."
        grid[ny][nx] = "."
        stack.append((nx, ny))
    return _store(grid, n, rng)


def rooms(w, h, n, rng):
    """Outer walls, a wall line every 8 columns with one door each, and a middle wall with doors."""
    grid = [["."] * w for _ in range(h)]
    for x in range(w):
        grid[h // 2][x] = "#" if x % 6 != 3 else "."
    for x in range(8, w, 8):
        for y in range(h):
            grid[y][x] = "#"
        grid[rng.choice([y for y in range(1, h - 1) if y != h // 2])][x] = "."
    return _store(grid, n, rng)


def random_basket(store, k, rng):
    return rng.sample(sorted(store.products), k)
