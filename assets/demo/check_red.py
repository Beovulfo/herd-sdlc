#!/usr/bin/env python3
"""Check assets/demo.gif for red error output: Claude Code prints a failed tool result in red.

Counts the red pixels in the terminal part of each frame (below the step panel). The spinner uses
the same red for a few dozen pixels, so a frame counts only above LIMIT. Needs ffmpeg.

  python3 assets/demo/check_red.py assets/demo.gif [--allow FIRST-LAST]

--allow takes a frame range that may be red (an expected failure, labelled in the caption).
Exit 0 when no other frame is red, 1 otherwise.
"""
import subprocess
import sys

PANEL, LIMIT = 0.15, 300  # top share of the frame that is the panel; red pixels that make a frame red


# a pixel is red when r > 90, r - g > 45 and r - b > 40; ffmpeg writes it as 0, anything else as 255
RED = "if(gt(r(X,Y),90)*gt(r(X,Y)-g(X,Y),45)*gt(r(X,Y)-b(X,Y),40),0,255)"


def frames(gif):
    """Red pixel count per frame, below the panel."""
    w, h = (int(v) for v in subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "csv=p=0", gif], capture_output=True, text=True, check=True).stdout.strip().split(","))
    top = int(h * PANEL)
    mask = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", gif, "-fps_mode", "passthrough", "-vf",
                           f"format=gbrp,crop={w}:{h - top}:0:{top},geq=r='{RED}':g='{RED}':b='{RED}',format=gray",
                           "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    size = w * (h - top)
    for start in range(0, len(mask) - size + 1, size):
        yield mask.count(0, start, start + size)


def main(argv):
    gif, allow = argv[0], range(0)
    if "--allow" in argv:
        a, b = argv[argv.index("--allow") + 1].split("-")
        allow = range(int(a), int(b) + 1)
    counts = list(frames(gif))
    bad = [(i + 1, n) for i, n in enumerate(counts) if n > LIMIT]
    print(f"{len(counts)} frames, {len(bad)} with red error output (over {LIMIT} red pixels)")
    runs = []
    for i, n in bad:
        if runs and i == runs[-1][1] + 1:
            runs[-1][1], runs[-1][2] = i, max(runs[-1][2], n)
        else:
            runs.append([i, i, n])
    for a, b, n in runs:
        print(f"  frames {a}-{b}: up to {n} red pixels" + (" (allowed)" if a in allow and b in allow else ""))
    return 1 if any(not (a in allow and b in allow) for a, b, _ in runs) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
