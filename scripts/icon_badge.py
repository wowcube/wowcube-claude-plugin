#!/usr/bin/env python3
"""Make or check a launcher icon in the launcher's standard hexagon.

The launcher shows every game's icon as a 160x160 flat-top hexagon badge, and every icon the launcher ships uses
the same hexagon: x 8..151, y 15..144 of the canvas (144 x 130 px), its exact anti-aliased edge stored in
templates/app_ai_template/art/icon_mask.png. An icon whose hexagon is drawn by hand (by a model, by Codex, by a
drawing script) comes out bigger or smaller than the others and looks wrong next to them on the cube. So the
picture is never drawn as a hexagon: it is drawn as a square picture, and this tool cuts the badge out of it.

    python icon_badge.py make <picture.png> --out <app_<game>/art/icon.png> [--bg "#1B2230"] [--zoom 1.0]
        Scales the picture to cover the hexagon (keeping its aspect, centred; --zoom > 1 crops tighter), lays it
        over a solid backdrop (--bg, used where the picture is transparent), and cuts it with the standard
        hexagon. Writes a 160x160 RGBA PNG.
    python icon_badge.py check <icon.png>
        Exit 0 when the icon stays inside the standard hexagon; exit 1 (and says where) when it paints outside it
        (a hand-drawn badge that is too big) or covers less than 80 % of it (too small); exit 2 on a bad file.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

MASK = Path(__file__).resolve().parents[1] / "templates" / "app_ai_template" / "art" / "icon_mask.png"
SIDE = 160
OUTSIDE_ALPHA = 32          # alpha above this where the mask is 0 = painted outside the hexagon
MIN_COVER = 0.80            # share of the hexagon's inside (mask 255) that must be opaque


def load_mask() -> Image.Image:
    m = Image.open(MASK).convert("L")
    if m.size != (SIDE, SIDE):
        raise SystemExit(f"{MASK}: expected {SIDE}x{SIDE}, got {m.size[0]}x{m.size[1]}")
    return m


def _hex_rgb(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    if len(s) != 6:
        raise argparse.ArgumentTypeError(f"--bg wants #RRGGBB, got {s!r}")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def make(picture: Image.Image, bg=(27, 34, 48), zoom: float = 1.0) -> Image.Image:
    """The 160x160 RGBA badge: the picture covering the standard hexagon, over bg, cut by the mask."""
    mask = load_mask()
    x0, y0, x1, y1 = mask.getbbox()
    bw, bh = x1 - x0, y1 - y0
    pic = picture.convert("RGBA")
    scale = max(bw / pic.width, bh / pic.height) * max(zoom, 0.1)
    w, h = max(1, round(pic.width * scale)), max(1, round(pic.height * scale))
    pic = pic.resize((w, h), Image.LANCZOS)
    canvas = Image.new("RGBA", (SIDE, SIDE), bg + (255,))
    canvas.alpha_composite(pic, (x0 + (bw - w) // 2, y0 + (bh - h) // 2))
    canvas.putalpha(mask)
    return canvas


def check(icon: Image.Image) -> list[str]:
    """Problems of an icon against the standard hexagon; empty when it fits."""
    if icon.size != (SIDE, SIDE):
        return [f"the icon is {icon.size[0]}x{icon.size[1]}, the launcher wants {SIDE}x{SIDE}"]
    a = np.asarray(icon.convert("RGBA"))[:, :, 3].astype(int)
    m = np.asarray(load_mask()).astype(int)
    out = (a > OUTSIDE_ALPHA) & (m == 0)
    problems = []
    if out.any():
        ys, xs = np.nonzero(out)
        problems.append(f"it paints outside the launcher's standard hexagon ({int(out.sum())} px, x {xs.min()}..{xs.max()}, "
                        f"y {ys.min()}..{ys.max()}): it will look bigger than every other icon. Remake it with "
                        f"'icon_badge.py make <picture>'")
    inside = m >= 255
    cover = float((a[inside] > 127).mean()) if inside.any() else 0.0
    if cover < MIN_COVER:
        problems.append(f"it covers only {cover:.0%} of the standard hexagon: it will look smaller than the other "
                        f"icons. Remake it with 'icon_badge.py make <picture>'")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make", help="cut a launcher icon out of a square picture")
    mk.add_argument("picture", type=Path)
    mk.add_argument("--out", type=Path, required=True)
    mk.add_argument("--bg", type=_hex_rgb, default=(27, 34, 48), help="backdrop where the picture is transparent")
    mk.add_argument("--zoom", type=float, default=1.0, help=">1 crops the picture tighter")
    ck = sub.add_parser("check", help="does an icon fit the standard hexagon?")
    ck.add_argument("icon", type=Path)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "make":
            badge = make(Image.open(a.picture), a.bg, a.zoom)
            a.out.parent.mkdir(parents=True, exist_ok=True)
            badge.save(a.out, optimize=True)
            print(f"launcher icon -> {a.out} (the standard hexagon, {SIDE}x{SIDE})")
            return 0
        problems = check(Image.open(a.icon))
    except (OSError, ValueError) as e:
        print(f"icon_badge: {e}", file=sys.stderr)
        return 2
    for p in problems:
        print(f"{a.icon}: {p}")
    if not problems:
        print(f"{a.icon}: fits the standard hexagon")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
