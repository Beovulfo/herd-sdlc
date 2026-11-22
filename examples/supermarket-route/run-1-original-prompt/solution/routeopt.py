"""Supermarket picker route optimizer: grid map, shopping list, step simulation, KPI comparison."""
import argparse
import json
import random
import sys
import time
from collections import deque, namedtuple

# ponytail: fixed time model (1 cell = 1 s of walking, 5 s per pick); make flags if real data shows otherwise
STEP_S = 1.0
PICK_S = 5.0
EXACT_MAX = 12  # ponytail: Held-Karp is O(2^n n^2); above this fall back to nearest neighbour + 2-opt

Step = namedtuple("Step", "t dist pos event")


class Store:
    def __init__(self, grid, start, products):
        self.grid, self.start, self.products = grid, start, products  # products: id -> (name, pos)

    @classmethod
    def from_dict(cls, d):
        prods = {p["id"]: (p["name"], tuple(p["pos"])) for p in d["products"]}
        return cls(list(d["grid"]), tuple(d["start"]), prods)

    def walkable(self, r, c):
        return 0 <= r < len(self.grid) and 0 <= c < len(self.grid[r]) and self.grid[r][c] == "."

    def neighbors(self, cell):
        r, c = cell
        return [(r + dr, c + dc) for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)) if self.walkable(r + dr, c + dc)]


def load_map(path):
    with open(path) as f:
        return Store.from_dict(json.load(f))


def parse_list(text, store):
    """Lines 'id:short name' -> ordered unique ids. Raises ValueError on bad input."""
    ids = []
    for line in text.splitlines():
        if not line.strip():
            continue
        pid, sep, name = line.partition(":")
        if not sep:
            raise ValueError(f"bad list line {line!r}, expected id:short name")
        pid, name = pid.strip(), name.strip()
        if pid not in store.products:
            raise ValueError(f"unknown product id {pid!r}")
        if store.products[pid][0] != name:
            raise ValueError(f"name {name!r} does not match map name {store.products[pid][0]!r} for {pid}")
        if pid not in ids:
            ids.append(pid)
    return ids


def bfs_path(store, a, b):
    """Shortest walkable path as a list of cells from a to b inclusive. Raises ValueError if unreachable."""
    prev = {a: None}
    q = deque([a])
    while q:
        cur = q.popleft()
        if cur == b:
            break
        for n in store.neighbors(cur):
            if n not in prev:
                prev[n] = cur
                q.append(n)
    if b not in prev:
        raise ValueError(f"unreachable: {b} from {a}")
    path = []
    while b is not None:
        path.append(b)
        b = prev[b]
    return path[::-1]


def _held_karp(d, n):
    """Exact shortest open path from node 0 through nodes 1..n-1. Returns visiting order without node 0."""
    m = n - 1
    best = {(1 << j, j): (d[0][j + 1], None) for j in range(m)}
    for mask in range(1, 1 << m):
        for j in range(m):
            if (mask, j) not in best:
                continue
            c = best[(mask, j)][0]
            for k in range(m):
                if not mask >> k & 1:
                    key = (mask | 1 << k, k)
                    if key not in best or c + d[j + 1][k + 1] < best[key][0]:
                        best[key] = (c + d[j + 1][k + 1], j)
    full = (1 << m) - 1
    j = min(range(m), key=lambda j: best[(full, j)][0])
    order, mask = [], full
    while j is not None:
        order.append(j + 1)
        mask, j = mask ^ 1 << j, best[(mask, j)][1]
    return order[::-1]


def plan_optimized(store, ids):
    """Exact (Held-Karp) for up to EXACT_MAX items, else nearest neighbour + 2-opt on shortest-path distances."""
    if not ids:
        return []
    pts = [store.start] + [store.products[i][1] for i in ids]
    n = len(pts)
    d = [[len(bfs_path(store, pts[i], pts[j])) - 1 if i != j else 0 for j in range(n)] for i in range(n)]
    if n - 1 <= EXACT_MAX:
        return [ids[k - 1] for k in _held_karp(d, n)]
    order, left = [0], set(range(1, n))
    while left:
        nxt = min(left, key=lambda j: d[order[-1]][j])
        order.append(nxt)
        left.remove(nxt)

    def cost(o):
        return sum(d[a][b] for a, b in zip(o, o[1:]))

    improved = True
    while improved:  # ponytail: O(n^3) per pass, fine for baskets under ~50 items
        improved = False
        for i in range(1, n):
            for j in range(i + 1, n):
                cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                if cost(cand) < cost(order):
                    order, improved = cand, True
    return [ids[k - 1] for k in order[1:]]


def simulate(store, ids, algo, seed=0, max_steps=5_000_000):
    """Yield Step(t, dist, pos, event) for every move and pick. algo: 'optimized' or 'random'."""
    t, dist, pos = 0.0, 0, store.start
    want = {i: store.products[i][1] for i in ids}
    yield Step(t, dist, pos, "start")

    def pick_here():
        nonlocal t
        for i in [i for i, p in want.items() if p == pos]:
            del want[i]
            t += PICK_S
            yield Step(t, dist, pos, f"pick {i}")

    if algo == "optimized":
        for i in plan_optimized(store, ids):
            for cell in bfs_path(store, pos, store.products[i][1])[1:]:
                pos, t, dist = cell, t + STEP_S, dist + 1
                yield Step(t, dist, pos, "move")
            if i in want:
                yield from pick_here()
        return
    if algo != "random":
        raise ValueError(f"unknown algo {algo!r}")
    for i in ids:  # fail fast on unreachable items instead of walking forever
        bfs_path(store, store.start, store.products[i][1])
    rng = random.Random(seed)
    yield from pick_here()
    steps = 0
    while want:
        steps += 1
        if steps > max_steps:
            raise ValueError("random walk exceeded max_steps")
        pos = rng.choice(store.neighbors(pos))
        t, dist = t + STEP_S, dist + 1
        yield Step(t, dist, pos, "move")
        yield from pick_here()


def kpis(store, ids, algo, seed=0):
    last = None
    for last in simulate(store, ids, algo, seed):
        pass
    return {"time": last.t, "dist": last.dist}


def compare(store, ids, runs=20, seed=0):
    opt = kpis(store, ids, "optimized")
    rnd = [kpis(store, ids, "random", seed + k) for k in range(runs)]
    mean = {k: sum(r[k] for r in rnd) / runs for k in ("time", "dist")}
    return {"optimized": opt, "random": mean, "runs": runs,
            "savings_pct": 100 * (1 - opt["time"] / mean["time"]) if mean["time"] else 0.0}


HTML = """<!doctype html><meta charset=utf-8><title>Supermarket picker simulation</title>
<style>
body{font:14px system-ui,sans-serif;margin:16px;background:#fafafa;color:#222}
.row{display:flex;flex-wrap:wrap;gap:24px}.card{background:#fff;border:1px solid #ddd;border-radius:6px;padding:10px}
h3{margin:0 0 6px}.kpi{font:600 15px ui-monospace,monospace;margin:6px 0}.bar{margin:10px 0}
.done{color:#0a7d33}.list{font-size:12px;color:#555;max-width:620px}.list s{color:#0a7d33}
</style>
<div class=bar><button id=pp>Pause</button> <button id=rs>Restart</button>
speed <input id=sp type=range min=1 max=200 value=25> <span id=spv></span>x
&nbsp; clock <b id=clk>0</b>s &nbsp; <span id=sav></span></div>
<div class=row id=cards></div>
<script>
const D = __DATA__, CELL = 20;
const cards = D.runs.map(run => {
  const el = document.createElement("div"); el.className = "card";
  el.innerHTML = "<h3>" + run.label + "</h3><canvas width=" + D.grid[0].length*CELL + " height=" + D.grid.length*CELL +
    "></canvas><div class=kpi></div><div class=list></div>";
  document.getElementById("cards").append(el);
  return {run, cv: el.querySelector("canvas"), kpi: el.querySelector(".kpi"), list: el.querySelector(".list"), i: 0};
});
const want = new Set(D.want), name = Object.fromEntries(D.products.map(p => [p.id, p.name]));
function draw(c, T) {
  const s = c.run.steps; c.i = 0;
  while (c.i + 1 < s.length && s[c.i + 1][0] <= T) c.i++;
  const g = c.cv.getContext("2d"), cur = s[c.i], picked = new Set();
  for (let k = 0; k <= c.i; k++) if (s[k][4].startsWith("pick ")) picked.add(s[k][4].slice(5));
  g.clearRect(0, 0, c.cv.width, c.cv.height);
  D.grid.forEach((row, r) => [...row].forEach((ch, col) => {
    g.fillStyle = ch === "#" ? "#556" : "#f4f1ea"; g.fillRect(col*CELL, r*CELL, CELL, CELL);
  }));
  g.strokeStyle = "rgba(30,110,230,.55)"; g.lineWidth = 2; g.beginPath();
  for (let k = 0; k <= c.i; k++) { const x = s[k][3]*CELL + CELL/2, y = s[k][2]*CELL + CELL/2; k ? g.lineTo(x, y) : g.moveTo(x, y); }
  g.stroke();
  g.font = "9px sans-serif";
  D.products.forEach(p => {
    const x = p.pos[1]*CELL, y = p.pos[0]*CELL, w = want.has(p.id);
    g.fillStyle = picked.has(p.id) ? "#2a9d4b" : w ? "#f08a00" : "#bbb";
    g.fillRect(x + 5, y + 5, 10, 10);
    if (w) { g.fillStyle = "#000"; g.fillText(p.id, x, y - 1); }
  });
  g.fillStyle = "#d33"; g.beginPath(); g.arc(cur[3]*CELL + CELL/2, cur[2]*CELL + CELL/2, 7, 0, 7); g.fill();
  const fin = picked.size === want.size;
  c.kpi.className = "kpi" + (fin ? " done" : "");
  c.kpi.textContent = "time-to-prepare-basket: " + cur[0].toFixed(0) + " s | distance-covered: " + cur[1] +
    " | picked " + picked.size + "/" + want.size + (fin ? " DONE" : "");
  c.list.innerHTML = D.want.map(id => picked.has(id) ? "<s>" + id + ":" + name[id] + "</s>" : id + ":" + name[id]).join(" &middot; ");
  return fin;
}
let T = 0, playing = true, last = null;
const end = Math.max(...D.runs.map(r => r.steps[r.steps.length - 1][0]));
const sp = document.getElementById("sp"), spv = document.getElementById("spv");
sp.oninput = () => spv.textContent = sp.value; sp.oninput();
document.getElementById("pp").onclick = e => { playing = !playing; e.target.textContent = playing ? "Pause" : "Play"; };
document.getElementById("rs").onclick = () => { T = 0; };
function frame(now) {
  if (last !== null && playing && T < end) T = Math.min(end, T + (now - last) / 1000 * sp.value);
  last = now;
  cards.forEach(c => draw(c, T));
  document.getElementById("clk").textContent = T.toFixed(0);
  const [a, b] = D.runs.map(r => r.steps[r.steps.length - 1][0]);
  document.getElementById("sav").textContent = T >= end ? "optimized saves " + (100*(1 - a/b)).toFixed(1) + "% time vs this random walk" : "";
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
</script>
"""


def build_html(store, ids, seed=0):
    """Self-contained HTML replaying optimized vs one seeded random walk side by side."""
    runs = [{"label": label, "steps": [[st.t, st.dist, st.pos[0], st.pos[1], st.event]
                                       for st in simulate(store, ids, algo, seed)]}
            for label, algo in (("Optimized route", "optimized"), (f"Random walk (seed {seed})", "random"))]
    data = {"grid": store.grid, "want": ids, "runs": runs,
            "products": [{"id": i, "name": n, "pos": list(p)} for i, (n, p) in store.products.items()]}
    return HTML.replace("__DATA__", json.dumps(data))


def _pos_int(v):
    n = int(v)
    if n < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return n


def _load(args):
    store = load_map(args.map)
    with open(args.list) as f:
        return store, parse_list(f.read(), store)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="routeopt", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("simulate", "compare", "visualize"):
        p = sub.add_parser(name)
        p.add_argument("--map", required=True)
        p.add_argument("--list", required=True)
        p.add_argument("--seed", type=int, default=0)
    s = sub.choices["simulate"]
    s.add_argument("--algo", choices=("optimized", "random"), default="optimized")
    s.add_argument("--delay", type=float, default=0.0, help="seconds to sleep per printed step (real-time feel)")
    s.add_argument("--every", type=_pos_int, default=1, help="print every Nth move (picks always print)")
    c = sub.choices["compare"]
    c.add_argument("--runs", type=_pos_int, default=20)
    c.add_argument("--min-savings", type=float, default=None, help="exit 1 if time savings %% is not above this")
    sub.choices["visualize"].add_argument("--out", default="simulation.html")
    a = ap.parse_args(argv)
    try:
        store, ids = _load(a)
        if a.cmd == "visualize":
            with open(a.out, "w") as f:
                f.write(build_html(store, ids, a.seed))
            print(f"wrote {a.out}")
            return 0
        if a.cmd == "simulate":
            moves = 0
            for st in simulate(store, ids, a.algo, a.seed):
                if st.event == "move":
                    moves += 1
                    if moves % a.every:
                        continue
                print(f"t={st.t:.0f}s dist={st.dist} pos={st.pos[0]},{st.pos[1]} {st.event}", flush=True)
                if a.delay:
                    time.sleep(a.delay)
            return 0
        r = compare(store, ids, a.runs, a.seed)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as e:  # bad input or malformed map
        print(f"error: {e}", file=sys.stderr)
        return 2
    o, w = r["optimized"], r["random"]
    print(f"items={len(ids)} random-walk runs={r['runs']} (seed {a.seed})")
    print(f"{'':28}{'optimized':>12}{'random walk':>14}")
    print(f"{'time-to-prepare-basket (s)':28}{o['time']:>12.0f}{w['time']:>14.0f}")
    print(f"{'distance-covered (cells)':28}{o['dist']:>12.0f}{w['dist']:>14.0f}")
    print(f"time savings: {r['savings_pct']:.1f}%")
    if a.min_savings is not None and not r["savings_pct"] > a.min_savings:
        print(f"FAIL: savings not above {a.min_savings}%", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
