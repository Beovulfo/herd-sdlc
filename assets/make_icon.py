#!/usr/bin/env python3
"""Render assets/icon.png (512x512) with the standard library only: a green rounded square with the Herd mark."""
import math
import struct
import zlib
from pathlib import Path

N, SS = 512, 3
GREEN, WHITE, MINT = (46, 125, 50), (255, 255, 255), (185, 246, 202)
S = N / 64.0  # the mark is drawn on a 64 x 64 canvas


def sd_round_rect(x, y, cx, cy, hw, hh, r):
    dx, dy = abs(x - cx) - (hw - r), abs(y - cy) - (hh - r)
    return math.hypot(max(dx, 0), max(dy, 0)) + min(max(dx, dy), 0) - r


def sd_segment(x, y, ax, ay, bx, by):
    px, py, vx, vy = x - ax, y - ay, bx - ax, by - ay
    t = max(0.0, min(1.0, (px * vx + py * vy) / (vx * vx + vy * vy)))
    return math.hypot(px - t * vx, py - t * vy)


def shade(x, y):
    """Colour at a point in 0..N pixel space, or None for transparent."""
    if sd_round_rect(x, y, N / 2, N / 2, N / 2, N / 2, N * 0.22) > 0:
        return None
    u, v = x / S, y / S  # mark coordinates; scale the mark down a little for breathing room
    u, v = (u - 32) / 0.72 + 32, (v - 32) / 0.72 + 32
    w = 4.0  # half of the 8-unit stroke
    for ax in (13, 51):
        if sd_segment(u, v, ax, 10, ax, 54) <= w:
            return WHITE
    d = min(sd_segment(u, v, 23.5, 35, 30, 41.5), sd_segment(u, v, 30, 41.5, 40.5, 26))
    return MINT if d <= w else GREEN


def main():
    rows = []
    for py in range(N):
        row = bytearray([0])
        for px in range(N):
            acc, cover = [0, 0, 0], 0
            for sy in range(SS):
                for sx in range(SS):
                    c = shade(px + (sx + .5) / SS, py + (sy + .5) / SS)
                    if c:
                        cover += 1
                        for i in range(3):
                            acc[i] += c[i]
            if cover:
                row += bytes([acc[0] // cover, acc[1] // cover, acc[2] // cover, 255 * cover // (SS * SS)])
            else:
                row += bytes([0, 0, 0, 0])
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", N, N, 8, 6, 0, 0, 0)) \
        + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    (Path(__file__).parent / "icon.png").write_bytes(png)


if __name__ == "__main__":
    main()
