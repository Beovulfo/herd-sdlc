"""Generate synthetic stores of different layout families. Deterministic per seed."""
import random


def _grid(R, C, fill="#"):
    return [[fill] * C for _ in range(R)]


def aisles(R, C, rng):
    g = _grid(R, C, ".")
    for r in range(2, R - 2):  # horizontal shelf rows with a cross aisle every 7 rows
        if r % 3 != 2 and r % 8 != 0:
            for c in range(1, C - 1):
                g[r][c] = "#"
    return g


def open_floor(R, C, rng):
    g = _grid(R, C, ".")
    for _ in range(R * C // 25):  # random shelf blobs
        r, c = rng.randrange(1, R - 1), rng.randrange(1, C - 1)
        for dr in range(rng.randint(1, 3)):
            for dc in range(rng.randint(1, 6)):
                if r + dr < R - 1 and c + dc < C - 1:
                    g[r + dr][c + dc] = "#"
    return g


def maze(R, C, rng):
    g = _grid(R, C, "#")
    stack = [(1, 1)]
    g[1][1] = "."
    while stack:
        r, c = stack[-1]
        opts = [(r + dr, c + dc, dr, dc) for dr, dc in ((2, 0), (-2, 0), (0, 2), (0, -2))
                if 0 < r + dr < R - 1 and 0 < c + dc < C - 1 and g[r + dr][c + dc] == "#"]
        if not opts:
            stack.pop()
            continue
        nr, nc, dr, dc = rng.choice(opts)
        g[r + dr // 2][c + dc // 2] = g[nr][nc] = "."
        stack.append((nr, nc))
    return g


def ring(R, C, rng):  # one-way-ish perimeter corridor plus a few spokes
    g = _grid(R, C, "#")
    for r in range(1, R - 1):
        g[r][1] = g[r][C - 2] = "."
    for c in range(1, C - 1):
        g[1][c] = g[R - 2][c] = "."
    for c in range(4, C - 3, 6):
        for r in range(1, R - 1):
            g[r][c] = "."
    return g


FAMILIES = dict(aisles=aisles, open=open_floor, maze=maze, ring=ring)


def make(family, R, C, n_products, seed, isolate=0):
    """Return (map dict, list of ids in random customer order). `isolate` walls off that many products."""
    rng = random.Random(seed)
    g = FAMILIES[family](R, C, rng)
    walk = [(r, c) for r in range(R) for c in range(C) if g[r][c] != "#"]
    start = (1, 1) if g[1][1] != "#" else walk[0]
    g[start[0]][start[1]] = "."
    cells = [c for c in walk if c != start]
    prods = [dict(id="P%d" % i, name="item%d" % i, pos=list(p)) for i, p in enumerate(rng.sample(cells, min(n_products, len(cells))))]
    for p in prods[:isolate]:  # fence a product in so it is unreachable
        r, c = p["pos"]
        for n in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
            if 0 <= n[0] < R and 0 <= n[1] < C and n != start:
                g[n[0]][n[1]] = "#"
    ids = [p["id"] for p in prods]
    rng.shuffle(ids)
    return dict(grid=["".join(r) for r in g], start=list(start), products=prods), ids
