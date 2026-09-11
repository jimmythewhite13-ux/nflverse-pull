"""Real, reproducible icon generation, matching the current design system (#14171C charcoal,
#F2C14E signal-yellow), same simple mark as icon.svg (rounded-square background, football
ellipse, lace stitching), at real 192x192 and 512x512 sizes for real PWA installability
(pwa_infrastructure_and_sync_buildout.md Part A). Re-run this after any real icon.svg color
change to keep the PNGs in sync.

Usage:
    uv run python hosted_env/api/static/gen_icons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

BG = (0x14, 0x17, 0x1C, 255)
BALL = (0xF2, 0xC1, 0x4E, 255)
LACE = (0x14, 0x17, 0x1C, 255)  # dark laces on the yellow ball, readable contrast

OUT_DIR = Path(__file__).resolve().parent


def make_icon(size: int, path: Path) -> None:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = round(size * 0.2)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=BG)
    cx, cy = size / 2, size / 2
    rx, ry = size * 0.32, size * 0.20
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=BALL)
    lw = max(2, round(size * 0.025))
    d.line([(cx - rx * 0.7, cy), (cx + rx * 0.7, cy)], fill=LACE, width=lw)
    for dx in (-0.31, -0.10, 0.10, 0.31):
        x = cx + dx * rx * 2
        d.line([(x, cy - ry * 0.35), (x, cy + ry * 0.35)], fill=LACE, width=lw)
    img.save(path)
    print(f"wrote {path} ({size}x{size})")


if __name__ == "__main__":
    make_icon(192, OUT_DIR / "icon-192.png")
    make_icon(512, OUT_DIR / "icon-512.png")
