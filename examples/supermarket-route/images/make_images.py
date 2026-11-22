#!/usr/bin/env python3
"""Render the example's images as SVG with the standard library only.

  simulation.svg   animated: list-order route vs optimized route on the same store, time bars running
  layouts.svg      the optimized route on eight different store layouts
  benchmark.svg    robustness, test depth and wall time per model, with and without Herd

Routes come from the Sonnet Herd solution (sonnet-herd-run/solution/routeopt.py) on stores generated
by verifier/verify_general.py. Run from this folder: python3 images/make_images.py
"""
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "verifier"))
sys.path.insert(0, str(HERE / "sonnet-herd-run" / "solution"))
import routeopt  # noqa: E402
import verify_general as vg  # noqa: E402

OUT = HERE / "images"
SHELF, FLOOR, LIST_C, OPT_C, ITEM_C, STATION_C = "#3b4252", "#f7f7f2", "#d08770", "#2e7d32", "#e5a50a", "#1565c0"


def solve(canon, ids):
    raw = {"grid": canon["grid"], "start": [canon["station"][1], canon["station"][0]],
           "products": [{"id": p, "name": v["name"], "x": v["shelf"][1], "y": v["shelf"][0]}
                        for p, v in canon["products"].items()]}
    store = routeopt.load_map(raw)
    items = [(p, canon["products"][p]["name"]) for p in ids]
    res = {}
    for label, opt in (("list", False), ("opt", True)):
        route = routeopt.plan(store, items, optimize=opt)
        res[label] = (route, routeopt.kpis(store, route))
    return store, res


def shelf_rects(rows, px, ox, oy):
    out = []
    for r, row in enumerate(rows):
        c = 0
        while c < len(row):
            if row[c] == "#":
                s = c
                while c < len(row) and row[c] == "#":
                    c += 1
                out.append(f'<rect x="{ox + s * px}" y="{oy + r * px}" width="{(c - s) * px}" height="{px}"/>')
            else:
                c += 1
    return "".join(out)


def polyline(cells, px, ox, oy):
    pts = [(ox + (x + .5) * px, oy + (y + .5) * px) for x, y in cells]
    d, prev, run = [f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"], pts[0], None
    for a, b in zip(pts, pts[1:]):
        dirn = (round(b[0] - a[0], 3), round(b[1] - a[1], 3))
        if dirn != run and run is not None:
            d.append(f"L{a[0]:.1f} {a[1]:.1f}")
        run = dirn
    d.append(f"L{pts[-1][0]:.1f} {pts[-1][1]:.1f}")
    return " ".join(d)


def dots(canon, ids, px, ox, oy, r):
    out = []
    for p in ids:
        sr, sc = canon["products"][p]["shelf"]
        out.append(f'<circle cx="{ox + (sc + .5) * px}" cy="{oy + (sr + .5) * px}" r="{r}" fill="{ITEM_C}" stroke="#fff" stroke-width="1"/>')
    return "".join(out)


def timeline(route, store, total_s, hold=1.0):
    """Breakpoints (time fraction, path fraction) with pauses at each pick."""
    n = max(1, len(route.cells) - 1)
    step_s, pick_s = store.cell_m / store.speed_mps, store.pick_s
    pts, picked = [(0.0, 0.0)], 0
    at = {}
    for idx in route.pick_at:
        at[idx] = at.get(idx, 0) + 1
    t = 0.0
    for idx in range(1, len(route.cells)):
        t += step_s
        if idx in at:
            pts.append((t, idx / n))
            t += pick_s * at[idx]
            pts.append((t, idx / n))
    if pts[-1][1] < 1.0:
        pts.append((t, 1.0))
    pts.append((total_s * hold, 1.0))
    return pts


def animated_panel(canon, ids, store, route, kp, px, ox, oy, color, label, total_s, dur):
    w, h = len(canon["grid"][0]), len(canon["grid"])
    d = polyline(route.cells, px, ox, oy)
    length = (len(route.cells) - 1) * px
    pts = timeline(route, store, total_s)
    scale = pts[-1][0]
    keytimes = ";".join(f"{t / scale:.5f}" for t, _ in pts)
    offsets = ";".join(f"{length * (1 - f):.1f}" for _, f in pts)
    keypoints = ";".join(f"{f:.5f}" for _, f in pts)
    widths = ";".join(f"{min(t, kp['time_s']) / total_s * (w * px):.1f}" for t, _ in pts)
    dist_w = ";".join(f"{f * kp['distance_m'] / DIST_MAX * (w * px):.1f}" for _, f in pts)
    bar_y = oy + h * px + 14
    return f'''
<rect x="{ox}" y="{oy}" width="{w * px}" height="{h * px}" fill="{FLOOR}" stroke="#999"/>
<g fill="{SHELF}" shape-rendering="crispEdges">{shelf_rects(canon["grid"], px, ox, oy)}</g>
<path d="{d}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" stroke-dasharray="{length:.1f}" stroke-dashoffset="{length:.1f}" opacity=".85">
  <animate attributeName="stroke-dashoffset" values="{offsets}" keyTimes="{keytimes}" dur="{dur}s" repeatCount="indefinite"/>
</path>
{dots(canon, ids, px, ox, oy, 3.2)}
<rect x="{ox + route.cells[0][0] * px}" y="{oy + route.cells[0][1] * px}" width="{px}" height="{px}" fill="{STATION_C}"/>
<circle r="5" fill="{color}" stroke="#fff" stroke-width="1.5">
  <animateMotion path="{d}" keyPoints="{keypoints}" keyTimes="{keytimes}" calcMode="linear" dur="{dur}s" repeatCount="indefinite"/>
</circle>
<text x="{ox}" y="{oy - 12}" font-size="15" font-weight="bold" fill="#222">{label}</text>
<text x="{ox + 4}" y="{bar_y}" font-size="11" fill="#555">time-to-prepare-basket</text>
<rect x="{ox}" y="{bar_y + 4}" width="{w * px}" height="9" fill="#e4e4e4"/>
<rect x="{ox}" y="{bar_y + 4}" height="9" fill="{color}" width="0"><animate attributeName="width" values="{widths}" keyTimes="{keytimes}" dur="{dur}s" repeatCount="indefinite"/></rect>
<text x="{ox + 4}" y="{bar_y + 30}" font-size="11" fill="#555">distance-covered</text>
<rect x="{ox}" y="{bar_y + 34}" width="{w * px}" height="9" fill="#e4e4e4"/>
<rect x="{ox}" y="{bar_y + 34}" height="9" fill="{color}" width="0"><animate attributeName="width" values="{dist_w}" keyTimes="{keytimes}" dur="{dur}s" repeatCount="indefinite"/></rect>
<text x="{ox}" y="{bar_y + 62}" font-size="13" fill="#222">{kp["time_s"]:.0f} s to prepare the basket, {kp["distance_m"]:.0f} m walked</text>
'''


DIST_MAX = 1.0


def simulation_svg():
    global DIST_MAX
    canon = vg.make_instance("parallel", "S", 7000)
    rnd = random.Random(11)
    ids = rnd.sample(sorted(canon["products"]), 14)
    store, res = solve(canon, ids)
    (lr, lk), (orr, ok) = res["list"], res["opt"]
    DIST_MAX = lk["distance_m"]
    px, gap, ox, oy = 8, 40, 20, 92
    w, h = len(canon["grid"][0]) * px, len(canon["grid"]) * px
    total = lk["time_s"]
    saved = 1 - ok["time_s"] / lk["time_s"]
    width, height = ox * 2 + 2 * w + gap, oy + h + 118
    body = (animated_panel(canon, ids, store, lr, lk, px, ox, oy, LIST_C, "Shopping-list order (not optimized)", total, 26)
            + animated_panel(canon, ids, store, orr, ok, px, ox + w + gap, oy, OPT_C, "Optimized route", total, 26))
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif">
<rect width="100%" height="100%" fill="#ffffff"/>
<text x="{ox}" y="26" font-size="18" font-weight="bold" fill="#111">One basket, two routes: {saved:.0%} less time to prepare it</text>
<text x="{ox}" y="46" font-size="12" fill="#555">14 items on a 60x40 store. Dark blocks are shelves, yellow dots are the items, the blue square is the packing station.</text>
<text x="{ox}" y="63" font-size="12" fill="#555">Both runs use the same walking speed (1.2 m/s) and 5 s per pick, and play at the same pace: the shorter route finishes first.</text>
{body}
</svg>
'''
    (OUT / "simulation.svg").write_text(svg)
    return saved


def layouts_svg():
    names = list(vg.FAMILIES)
    px, tw, th, pad = 4, 60 * 4, 40 * 4, 16
    cols = 4
    rows = (len(names) + cols - 1) // cols
    width, height = pad + cols * (tw + pad), 56 + rows * (th + 46)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif">',
             '<rect width="100%" height="100%" fill="#fff"/>',
             f'<text x="{pad}" y="26" font-size="18" font-weight="bold" fill="#111">The same optimizer on eight store layouts</text>',
             f'<text x="{pad}" y="44" font-size="12" fill="#555">Green line: optimized route for 12 items. Each layout was generated, not drawn by hand.</text>']
    for n, fam in enumerate(names):
        c = vg.make_instance(fam, "S", 7000)
        ids = random.Random(n).sample(sorted(c["products"]), 12)
        store, res = solve(c, ids)
        route, kp = res["opt"]
        base = res["list"][1]
        ox, oy = pad + (n % cols) * (tw + pad), 60 + (n // cols) * (th + 46)
        saved = 1 - kp["time_s"] / base["time_s"]
        parts.append(f'<rect x="{ox}" y="{oy}" width="{tw}" height="{th}" fill="{FLOOR}" stroke="#999"/>'
                     f'<g fill="{SHELF}" shape-rendering="crispEdges">{shelf_rects(c["grid"], px, ox, oy)}</g>'
                     f'<path d="{polyline(route.cells, px, ox, oy)}" fill="none" stroke="{OPT_C}" stroke-width="1.3" opacity=".9"/>'
                     f'{dots(c, ids, px, ox, oy, 2.4)}'
                     f'<rect x="{ox + route.cells[0][0] * px}" y="{oy + route.cells[0][1] * px}" width="{px * 1.6}" height="{px * 1.6}" fill="{STATION_C}"/>'
                     f'<text x="{ox}" y="{oy + th + 15}" font-size="13" font-weight="bold" fill="#222">{fam}</text>'
                     f'<text x="{ox}" y="{oy + th + 30}" font-size="11" fill="#555">{kp["distance_m"]:.0f} m, {saved:.0%} less time than list order</text>')
    parts.append("</svg>")
    (OUT / "layouts.svg").write_text("\n".join(parts))


# numbers from verifier/robustness_probe.py and the run logs (see BENCHMARK.md)
PAIRS = [("Opus", "run 1", 6, 4.3), ("Opus", "run 2", 6, 2.7), ("Opus", "no workflow", 3, 2.1),
         ("Haiku", "Herd", 6, 3.0), ("Haiku", "no workflow", 3, 1.5),
         ("Sonnet", "Herd", 6, 8.4), ("Sonnet", "no workflow", 4, 1.1)]


def benchmark_svg():
    width, height, left, bar_h, gap = 860, 56 + len(PAIRS) * 30 + 80, 190, 18, 12
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif">',
             '<rect width="100%" height="100%" fill="#fff"/>',
             '<text x="16" y="26" font-size="18" font-weight="bold" fill="#111">Same prompt, with and without Herd</text>',
             '<text x="16" y="44" font-size="12" fill="#555">Left: bad-input scenarios handled out of 6 (no crash). Right: wall-clock minutes to a finished result.</text>']
    for i, (model, arm, handled, mins) in enumerate(PAIRS):
        y = 66 + i * 30
        herd = arm != "no workflow"
        color = OPT_C if herd else LIST_C
        parts.append(f'<text x="16" y="{y + 13}" font-size="12" fill="#222">{model}, {arm}</text>')
        parts.append(f'<rect x="{left}" y="{y}" width="{handled * 40}" height="{bar_h}" fill="{color}"/>'
                     f'<text x="{left + handled * 40 + 6}" y="{y + 13}" font-size="12" fill="#222">{handled} of 6</text>')
        x2 = left + 6 * 40 + 70
        parts.append(f'<rect x="{x2}" y="{y}" width="{mins * 28:.0f}" height="{bar_h}" fill="{color}" opacity=".55"/>'
                     f'<text x="{x2 + mins * 28 + 6:.0f}" y="{y + 13}" font-size="12" fill="#222">{mins:.1f} min</text>')
    y = 66 + len(PAIRS) * 30 + 10
    parts.append(f'<rect x="16" y="{y}" width="12" height="12" fill="{OPT_C}"/><text x="34" y="{y + 11}" font-size="12" fill="#222">with Herd</text>'
                 f'<rect x="120" y="{y}" width="12" height="12" fill="{LIST_C}"/><text x="138" y="{y + 11}" font-size="12" fill="#222">no workflow</text>')
    parts.append(f'<text x="16" y="{y + 34}" font-size="11" fill="#666">One run per arm. Herd runs on Haiku were emulated by following the skills; the Sonnet Herd time includes any time the session waited.</text>')
    parts.append("</svg>")
    (OUT / "benchmark.svg").write_text("\n".join(parts))


if __name__ == "__main__":
    saved = simulation_svg()
    layouts_svg()
    benchmark_svg()
    print(f"wrote simulation.svg ({saved:.1%} saved on the animated basket), layouts.svg, benchmark.svg")
