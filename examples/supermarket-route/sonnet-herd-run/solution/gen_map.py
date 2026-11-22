"""Synthetic supermarket maps and shopping lists for demos and tests (stdlib only).

    python3 gen_map.py aisles --width 81 --height 51 --products 800 --items 25 --seed 1 --out store1
writes store1/map.json and store1/list.txt (list is in random order: the "not optimized" order).
"""
import argparse
import json
import os
import random

WORDS = ("milk", "bread", "eggs", "rice", "pasta", "apple", "tea", "soap", "salt", "jam", "oil", "beans")


def _grid(kind, rng, w, h):
    g = [["."] * w for _ in range(h)]
    if kind == "aisles":  # double-thick shelf rows with an aisle between each, cross aisles every 10 columns
        for y in range(h):
            if y % 4 in (1, 2):
                for x in range(w):
                    if x % 10 != 0:
                        g[y][x] = "#"
    elif kind == "open":  # open floor with scattered shelf islands
        for y0 in range(2, h - 3, 5):
            for x0 in range(2, w - 5, 7):
                x1, y1 = x0 + rng.randint(0, 2), y0 + rng.randint(0, 1)
                for y in range(y1, y1 + 2):
                    for x in range(x1, min(x1 + 4, w - 1)):
                        g[y][x] = "#"
    elif kind == "random":  # random clutter, then wall off whatever the entrance cannot reach
        for y in range(h):
            for x in range(w):
                if rng.random() < 0.28:
                    g[y][x] = "#"
    elif kind == "winding":  # one long serpentine corridor, shelves are the walls between its runs
        for y in range(1, h, 2):
            gap = w - 1 if (y // 2) % 2 == 0 else 0
            for x in range(w):
                g[y][x] = "." if x == gap else "#"
        return g, (0, 0), (w - 1, h - 1 if h % 2 else h - 2)
    else:
        raise ValueError(f"unknown kind {kind!r}")
    for y in range(h):  # perimeter walkway and entrance/checkout cells always open
        g[y][0] = g[y][w - 1] = "."
    for x in range(w):
        g[0][x] = g[h - 1][x] = "."
    return g, (1, h - 1), (w - 2, h - 1)


def _reachable(g, start):
    h, w = len(g), len(g[0])
    seen, q = {start}, [start]
    for x, y in q:
        for c in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= c[0] < w and 0 <= c[1] < h and g[c[1]][c[0]] != "#" and c not in seen:
                seen.add(c)
                q.append(c)
    return seen


def make_store(kind, seed, w, h, n_products):
    rng = random.Random(seed)
    g, start, end = _grid(kind, rng, w, h)
    seen = _reachable(g, start)
    for y in range(h):
        for x in range(w):
            if g[y][x] != "#" and (x, y) not in seen:
                g[y][x] = "#"
    shelves = [(x, y) for y in range(h) for x in range(w) if g[y][x] == "#"
               and any((x + dx, y + dy) in seen for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
    rng.shuffle(shelves)
    products = [{"id": f"P{i:05d}", "name": f"{WORDS[i % len(WORDS)]}-{i}", "x": x, "y": y}
                for i, (x, y) in enumerate(shelves[:n_products])]
    return {"grid": ["".join(r) for r in g], "start": list(start), "end": list(end), "products": products}


def make_list(raw, n, seed):
    rng = random.Random(seed + 1000)
    picked = rng.sample(raw["products"], min(n, len(raw["products"])))
    return [f"{p['id']}:{p['name']}" for p in picked]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("kind", choices=("aisles", "open", "random", "winding"))
    ap.add_argument("--width", type=int, default=81)
    ap.add_argument("--height", type=int, default=51)
    ap.add_argument("--products", type=int, default=800)
    ap.add_argument("--items", type=int, default=25)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", required=True, help="output directory")
    a = ap.parse_args(argv)
    raw = make_store(a.kind, a.seed, a.width, a.height, a.products)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "map.json"), "w") as f:
        json.dump(raw, f)
    with open(os.path.join(a.out, "list.txt"), "w") as f:
        f.write("\n".join(make_list(raw, a.items, a.seed)) + "\n")
    print(f"wrote {a.out}/map.json ({len(raw['products'])} products) and {a.out}/list.txt ({a.items} items)")


if __name__ == "__main__":
    main()
