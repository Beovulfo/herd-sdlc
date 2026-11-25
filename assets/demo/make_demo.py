#!/usr/bin/env python3
"""Build assets/demo.gif: a recorded /herd:run session under a panel that lights the current Herd step.

Inputs: the vhs recording (demo.mp4, made with demo.tape) and phases.json, written by hand from
the session transcript: `phases` is a list of [video_seconds, step, caption] whose last entry marks
the end, and `masks` hides terminal lines that must not be published (such as the local user name). Needs rsvg-convert and ffmpeg.

  python3 assets/demo/make_demo.py demo.mp4 assets/demo/phases.json assets/demo.gif
"""
import json
import subprocess
import sys
import tempfile
from html import escape
from pathlib import Path

STEPS = [("intake", "Intake"), ("criteria", "Criteria"), ("second", "Second look"), ("red", "Red first"),
         ("build", "Build"), ("break", "Break it"), ("verify", "Verify"), ("evidence", "Evidence")]
W, H = 1200, 170
SPEED, MIN_SHOW, FPS, SRC_FPS, HOLD = 6, 2.5, 8, 10, 5  # each caption stays at least MIN_SHOW s; HOLD s on the last frame
BG, IDLE, DONE, NOW, TEXT, DIM = "#171717", "#3a3a3a", "#2e7d32", "#4caf50", "#e5e7eb", "#9ca3af"
FONT = 'font-family="Helvetica, Arial, sans-serif"'


def panel(step, caption, t):
    """SVG for one moment: the current step lit, earlier steps done, the caption and the real clock."""
    cur = [k for k, _ in STEPS].index(step)
    bw, gap, x0, y = 128, 14, 34, 22
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}"><rect width="{W}" height="{H}" fill="{BG}"/>']
    for i, (_, label) in enumerate(STEPS):
        x = x0 + i * (bw + gap)
        fill, stroke, color = (("#1d3a1f", DONE, TEXT) if i < cur else (NOW, "#a5d6a7", "#0b1f0c") if i == cur
                               else (BG, IDLE, DIM))
        parts.append(f'<rect x="{x}" y="{y}" width="{bw}" height="50" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
                     f'<text x="{x + bw / 2}" y="{y + 31}" text-anchor="middle" {FONT} font-size="18" font-weight="700" '
                     f'fill="{color}">{escape(label)}</text>')
        if i < len(STEPS) - 1:
            ax = x + bw + 2
            parts.append(f'<path d="M{ax} {y + 25}h{gap - 5}" stroke="{DIM}" stroke-width="2"/>'
                         f'<path d="M{ax + gap - 6} {y + 21}l5 4l-5 4z" fill="{DIM}"/>')
    m, s = divmod(int(t), 60)
    parts.append(f'<text x="{x0}" y="{y + 92}" {FONT} font-size="22" fill="{TEXT}">{escape(caption)}</text>'
                 f'<text x="{x0}" y="{y + 130}" {FONT} font-size="16" fill="{DIM}">Real /herd:run session, Herd 0.14.0, Claude Sonnet 5.5 with a Haiku 5.5 builder, '
                 f'sped up. Elapsed {m}m {s:02d}s</text></svg>')
    return "".join(parts)


def main(video, phases_path, out):
    doc = json.loads(Path(phases_path).read_text())
    phases, end = doc["phases"], doc["phases"][-1][0]
    masks = ",".join(f"drawbox=x=82:y={y0}:w=1060:h={y1 - y0}:color={BG}:t=fill:enable='between(t,{a},{b})'"
                     for a, b, y0, y1 in doc.get("masks", []))
    tmp = Path(tempfile.mkdtemp())
    subprocess.run(["ffmpeg", "-loglevel", "error", "-i", video, "-t", str(end), "-vf", ",".join(filter(None, [masks, f"fps={SRC_FPS}"])),
                    str(tmp / "s%05d.png")], check=True)
    nsrc = len(list(tmp.glob("s*.png")))
    term, pan = [], []
    for (t0, step, caption), (t1, *_) in zip(phases, phases[1:]):
        n = max(1, round(max((t1 - t0) / SPEED, MIN_SHOW) * FPS))  # output frames for this caption
        for j in range(n):
            t = t0 + (t1 - t0) * j / n
            png = tmp / f"p_{step}_{int(t0 * 10)}_{int(t)}.png"
            if not png.exists():
                (tmp / "p.svg").write_text(panel(step, caption, t))
                subprocess.run(["rsvg-convert", str(tmp / "p.svg"), "-o", str(png)], check=True)
            term.append(tmp / f"s{min(nsrc, int(t * SRC_FPS) + 1):05d}.png")
            pan.append(png)
    for name, frames in (("term.txt", term), ("pan.txt", pan)):
        lines = [f"file '{f}'\nduration {1 / FPS}" for f in frames + frames[-1:] * (HOLD * FPS)]  # real frames: concat doubles a long last duration
        (tmp / name).write_text("\n".join(lines) + "\n")
    graph = (f"[1:v][0:v]vstack,fps={FPS},scale=860:-1:flags=lanczos,split[a][b];"
             "[a]palettegen=max_colors=48:stats_mode=diff[pal];[b][pal]paletteuse=dither=none")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(tmp / "term.txt"),
                    "-f", "concat", "-safe", "0", "-i", str(tmp / "pan.txt"), "-filter_complex", graph, out], check=True)


if __name__ == "__main__":
    main(*sys.argv[1:4])
