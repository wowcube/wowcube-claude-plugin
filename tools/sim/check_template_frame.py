#!/usr/bin/env python3
"""Check a cross frame (--frames, --face -1) of templates/app_ai_template's Demo 0, as CI does after a headless run.

    python check_template_frame.py <frame.png>

Demo 0 shows the teal arrow disc (sprite shape_arrow, the template's own art) on all four
TOP screens and on one FRONT screen (top-left); every other screen is black.
Exit 0 = matches, 1 = does not, 2 = unreadable. Needs Pillow.
"""
import sys

from PIL import Image

SIDE, SCRGAP, FACEGAP = 240, 4, 12
FACE = 2 * SIDE + SCRGAP
COL = {"top": 1, "front": 1, "right": 2, "back": 3, "left": 0, "bottom": 1}
ROW = {"top": 0, "front": 1, "right": 1, "back": 1, "left": 1, "bottom": 2}
EXPECT_TEAL = {("top", 0, 0), ("top", 1, 0), ("top", 0, 1), ("top", 1, 1), ("front", 0, 0)}


def teal_share(img, x0, y0):
    px = img.crop((x0, y0, x0 + SIDE, y0 + SIDE)).tobytes()
    px = zip(px[0::3], px[1::3], px[2::3])
    teal = sum(1 for r, g, b in px if r < 90 and g > 140 and b > 120 and g - r > 80)
    return teal / (SIDE * SIDE)


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    try:
        img = Image.open(argv[1]).convert("RGB")
    except OSError as e:
        print(f"unreadable: {e}")
        return 2
    if img.size != (4 * FACE + 3 * FACEGAP, 3 * FACE + 2 * FACEGAP):
        print(f"not a cross frame: {img.size}")
        return 2
    bad = 0
    for face in COL:
        for sx in (0, 1):
            for sy in (0, 1):
                x0 = COL[face] * (FACE + FACEGAP) + sx * (SIDE + SCRGAP)
                y0 = ROW[face] * (FACE + FACEGAP) + sy * (SIDE + SCRGAP)
                share = teal_share(img, x0, y0)
                want = (face, sx, sy) in EXPECT_TEAL
                ok = share > 0.2 if want else share < 0.01
                bad += not ok
                print(f"{'ok ' if ok else 'BAD'} {face:6s} screen ({sx},{sy}) teal {share:5.1%} (expected {'disc' if want else 'none'})")
    print("MATCH: Demo 0 as expected" if not bad else f"MISMATCH: {bad} screen(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
