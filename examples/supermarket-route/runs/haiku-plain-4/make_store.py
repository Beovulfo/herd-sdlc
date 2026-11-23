#!/usr/bin/env python3
"""Generate a synthetic supermarket map (shelf bars, cross aisles, random products).

Usage: python3 make_store.py --rows 120 --cols 200 --products 800 \
           --out examples/store.json --order-out examples/order.txt
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def build(rows: int, cols: int, products: int, seed: int) -> dict:
    rng = random.Random(seed)
    grid = [["."] * cols for _ in range(rows)]
    for c in range(cols):
        grid[0][c] = grid[rows - 1][c] = "#"
    for r in range(rows):
        grid[r][0] = grid[r][cols - 1] = "#"
    # Shelf bars: rows with r % 4 in (1, 2) are shelves, the two rows between bars are aisles.
    access: list[tuple[int, int]] = []
    for r in range(1, rows - 1):
        if r % 4 not in (1, 2):
            continue
        aisle_row = r - 1 if r % 4 == 1 else r + 1
        if not 0 < aisle_row < rows - 1:
            continue
        for c in range(2, cols - 2):
            if c % 16 == 0:  # cross aisle every 16 columns
                continue
            grid[r][c] = "#"
            access.append((aisle_row, c))
    cells = rng.sample(access, min(products, len(access)))
    items = [
        {"id": f"P{k:05d}", "name": f"item-{k:04d}", "cell": list(cell)}
        for k, cell in enumerate(sorted(cells), start=1)
    ]
    return {
        "name": f"synthetic {rows}x{cols}",
        "cell_size_m": 1.0,
        "grid": ["".join(row) for row in grid],
        "entrance": [rows // 2, 1],
        "checkout": [rows // 2, cols - 2],
        "products": items,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rows", type=int, default=120)
    ap.add_argument("--cols", type=int, default=200)
    ap.add_argument("--products", type=int, default=800)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", required=True)
    ap.add_argument("--order-out", help="also write a random 12-item customer list here")
    args = ap.parse_args()

    store = build(args.rows, args.cols, args.products, args.seed)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(store) + "\n")
    print(f"wrote {args.out}: {len(store['products'])} products on a {args.rows}x{args.cols} map")
    if args.order_out:
        rng = random.Random(args.seed)
        picked = rng.sample(store["products"], 12)
        lines = [f"{p['id']}:{p['name']}" for p in picked]
        Path(args.order_out).write_text("\n".join(lines) + "\n")
        print(f"wrote {args.order_out}: {len(lines)} items")


if __name__ == "__main__":
    main()
