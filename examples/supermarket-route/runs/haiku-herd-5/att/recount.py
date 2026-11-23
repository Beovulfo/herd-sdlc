# Separate recount: rebuild totals from the CLI trace text only (no route_optimizer import).
import re, subprocess, sys
def run(*a):
    return subprocess.run([sys.executable, "route_optimizer.py", *a], capture_output=True, text=True).stdout
for store, basket in (("demo/store.json", "demo/basket.txt"), ("att/map.json", "att/dupe_basket.txt")):
    trace = run("run", store, basket).splitlines()
    walk_cells = sum(1 for l in trace if l.startswith("walk"))
    picks = sum(1 for l in trace if l.startswith("pick"))
    dist = walk_cells * 1.0
    secs = walk_cells / 1.2 + picks * 8.0
    last = trace[-1]
    m = re.search(r"time-to-prepare-basket: ([\d.]+) s; distance-covered: ([\d.]+) m", last)
    rep_t, rep_d = float(m.group(1)), float(m.group(2))
    cmp_out = run("compare", store, basket)
    ok = abs(rep_t - secs) < 0.1 and abs(rep_d - dist) < 0.1
    print(store, "recount time", round(secs, 1), "reported", rep_t, "| distance", dist, "reported", rep_d, "OK" if ok else "MISMATCH")
    print(cmp_out.strip().splitlines()[1])
