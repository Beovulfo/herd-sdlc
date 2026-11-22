#!/usr/bin/env python3
"""Black-box verifier for the supermarket route-optimizer example.

It does not read the agent's code. It generates its own supermarkets and baskets from
seeds the agent has not seen, runs `supermarket.py simulate` for each algorithm, validates
the step stream, and checks the headline claim: optimized saves more than 20 percent of
time-to-prepare against the random walk. Standard library only.

Usage: verify_independent.py PROJECT_DIR [--baskets N] [--seed-base S] [--threshold 0.20]
"""
import argparse
import json
import random
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

W, H = 41, 21
AISLE_ROWS = [2, 5, 6, 9, 10, 13, 14, 17, 18]
SHELF_ROWS = [3, 4, 7, 8, 11, 12, 15, 16]
CROSS_COLS = {20}


def make_store(seed, n_products=120):
    rnd = random.Random(seed)
    grid = [["#"] * W for _ in range(H)]
    for y in range(1, H - 1):
        for x in range(1, W - 1):
            grid[y][x] = "." if (y not in SHELF_ROWS or x in CROSS_COLS or x < 3 or x > W - 4) else "#"
    free = [(x, y) for y in AISLE_ROWS for x in range(1, W - 1) if grid[y][x] == "."]
    cells = rnd.sample(free, n_products)
    names = ["milk", "bread", "eggs", "rice", "tea", "soap", "jam", "oil", "salt", "pasta"]
    products = {f"P{i + 1:03d}": {"name": f"{names[i % len(names)]}{i}", "cell": list(c)}
                for i, c in enumerate(cells)}
    return {"grid": ["".join(r) for r in grid], "products": products, "start": [1, H - 2]}


def make_list(store, seed, k):
    rnd = random.Random(seed)
    ids = rnd.sample(sorted(store["products"]), k)
    return {"items": [{"id": i, "name": store["products"][i]["name"]} for i in ids]}


def run(project, map_path, list_path, algo, seed, timeout=180):
    cmd = [sys.executable, "supermarket.py", "simulate", "--map", str(map_path), "--list", str(list_path),
           "--algo", algo, "--seed", str(seed)]
    p = subprocess.run(cmd, cwd=project, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise AssertionError(f"{algo}: exit {p.returncode}: {p.stderr[-300:]}")
    return [json.loads(line) for line in p.stdout.splitlines() if line.strip().startswith("{")]


def validate(store, items, lines, algo):
    """Check the step stream is a legal walk that picks every item. Returns the final record."""
    grid, prods = store["grid"], store["products"]
    want = {i["id"] for i in items}
    steps = [l for l in lines if l.get("type") == "step"]
    finals = [l for l in lines if l.get("type") == "final"]
    assert len(finals) == 1 and lines[-1] is finals[0], f"{algo}: need exactly one final line, last"
    final = finals[0]
    pos, dist, last_t, picked = tuple(store["start"]), 0, -1e-9, set()
    for s in steps:
        nxt = tuple(s["pos"])
        if nxt != pos:
            assert abs(nxt[0] - pos[0]) + abs(nxt[1] - pos[1]) == 1, f"{algo}: step {s['n']} is not adjacent"
            assert grid[nxt[1]][nxt[0]] == ".", f"{algo}: step {s['n']} walks into a wall"
            dist += 1
        assert s["distance"] == dist, f"{algo}: distance wrong at step {s['n']}"
        assert s["time"] >= last_t, f"{algo}: time went backwards at step {s['n']}"
        last_t, pos = s["time"], nxt
        for pid in s.get("picked", []):
            assert list(pos) == prods[pid]["cell"], f"{algo}: {pid} picked away from its cell"
            picked.add(pid)
    assert picked == want, f"{algo}: picked {sorted(picked)} wanted {sorted(want)}"
    assert final["distance"] == dist, f"{algo}: final distance differs from steps"
    assert abs(final["time_to_prepare"] - last_t) < 1e-6, f"{algo}: final time differs from last step"
    return final


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--baskets", type=int, default=20)
    ap.add_argument("--seed-base", type=int, default=9001)
    ap.add_argument("--threshold", type=float, default=0.20)
    a = ap.parse_args()
    project = Path(a.project)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for b in range(a.baskets):
            seed = a.seed_base + b
            store, k = make_store(seed), 6 + b % 10
            lst = make_list(store, seed, k)
            mp, lp = Path(tmp) / f"m{b}.json", Path(tmp) / f"l{b}.json"
            mp.write_text(json.dumps(store))
            lp.write_text(json.dumps(lst))
            res = {}
            for algo in ("optimized", "random", "list-order"):
                res[algo] = validate(store, lst["items"], run(project, mp, lp, algo, seed), algo)
            rows.append((seed, k, res))
    def mean(algo, key):
        return statistics.mean(r[2][algo][key] for r in rows)
    t_opt, t_rnd, t_lst = (mean(x, "time_to_prepare") for x in ("optimized", "random", "list-order"))
    d_opt, d_rnd, d_lst = (mean(x, "distance") for x in ("optimized", "random", "list-order"))
    save_rnd, save_lst = 1 - t_opt / t_rnd, 1 - t_opt / t_lst
    worse = sum(r[2]["optimized"]["time_to_prepare"] > r[2]["list-order"]["time_to_prepare"] for r in rows)
    print(f"baskets: {len(rows)} (seeds {a.seed_base}..{a.seed_base + len(rows) - 1}), all step streams valid")
    print("| algorithm | mean time | mean distance |\n| --- | --- | --- |")
    for name, t, d in (("optimized", t_opt, d_opt), ("random walk", t_rnd, d_rnd), ("list order", t_lst, d_lst)):
        print(f"| {name} | {t:.1f} | {d:.1f} |")
    print(f"time saved vs random walk: {save_rnd:.1%} (threshold {a.threshold:.0%})")
    print(f"time saved vs list order (stronger baseline, informational): {save_lst:.1%}; "
          f"optimized slower than list order on {worse} of {len(rows)} baskets")
    ok = save_rnd > a.threshold
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(f"RESULT: INVALID, {e}")
        sys.exit(2)
