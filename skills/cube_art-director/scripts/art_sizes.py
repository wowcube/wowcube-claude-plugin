"""Sprite sizes for the WowCube, by role: the art director's sizing reference (references/SIZES.md) as code.

The cube has 24 screens of 240x240 pixels. Most sprites are drawn at HALF size and shown x2 (a sprite that
should look 64 px tall on the screen is drawn 32 px tall; at most 120x120 = one whole screen). Only sprites
marked fullsize are drawn 1:1 (at most 240x240) and they always sit above every half-size sprite. The launcher
icon is its own thing: 160x160.

`check(project)` flags a size that cannot work (an error) or that is unusual for the sprite's role (a
warning). The role is the asset's `role` field, else it is guessed from the name. Only the WowCube target is
checked: an art.json with `"target"` set to anything else ("godot", "web", ...) gets no size findings.
"""
from __future__ import annotations

import re

HALF_MAX = 120          # half-size sprites: at most one screen (shown x2)
FULL_MAX = 240          # fullsize sprites: drawn 1:1
SCREEN = 240
ICON = 160

# role -> (typical drawn size range per side for half-size sprites, what it is)
ROLES = {
    "background": ((120, 120), "a full-screen background: 120x120 drawn (x2 = the whole 240x240 screen)"),
    "panorama": ((120, 120), "one piece of a picture that spans several screens: 120x120 per screen"),
    "character": ((16, 60), "a character or creature: 16-60 px drawn (32-120 px on screen)"),
    "tile": ((10, 60), "a board tile: 10-60 px drawn; a tile that divides 120 (12, 15, 20, 24, 30, 40, 60) fills a screen evenly"),
    "button": ((20, 80), "a button or panel: 20-80 px drawn wide (40-160 px on screen; a finger needs 60+ px on screen)"),
    "hud_icon": ((8, 32), "a small HUD icon (heart, coin, star): 8-32 px drawn"),
    "particle": ((2, 16), "a particle or spark: 2-16 px drawn"),
    "launcher_icon": ((160, 160), "the launcher icon: a 160x160 square picture (icon_badge.py cuts the hexagon)"),
    "sprite": ((4, 120), "any other sprite: at most 120 px drawn per side"),
}

_NAME_RULES = [
    (r"(^|_)(launcher_icon|app_icon)($|_)|^icon$", "launcher_icon"),
    (r"(^|_)(bg|background|backdrop|sky|wall)($|_)", "background"),
    (r"(^|_)(pano|panorama)($|_)", "panorama"),
    (r"(^|_)(tile|cell|block)($|_|\d)", "tile"),
    (r"(^|_)(btn|button|panel)($|_)", "button"),
    (r"(^|_)(particle|spark|fx|dust|star_small)($|_)", "particle"),
    (r"(^|_)(heart|coin|hud|life|lives)($|_)", "hud_icon"),
    (r"(^|_)(hero|player|enemy|char|character|monster|npc|dino|fox|snake)($|_)", "character"),
]


def role_of(asset) -> str:
    role = getattr(asset, "role", None)
    if role in ROLES:
        return role
    for rx, r in _NAME_RULES:
        if re.search(rx, asset.name):
            return r
    return "sprite"


def check_asset(asset) -> list[tuple[str, str]]:
    """[(level, message)] for one asset; level 'error' (cannot work on the cube) or 'warn' (unusual)."""
    w, h = (int(asset.size[0]), int(asset.size[1]))
    role = role_of(asset)
    out = []
    if w < 1 or h < 1:
        return [("error", f"size {w}x{h} is empty")]
    if role == "launcher_icon":
        if (w, h) != (ICON, ICON):
            out.append(("warn", f"the launcher icon is {ICON}x{ICON}, not {w}x{h}"))
        return out
    limit = FULL_MAX if asset.fullsize else HALF_MAX
    if w > limit or h > limit:
        if asset.fullsize:
            out.append(("error", f"{w}x{h} is larger than a screen ({SCREEN}x{SCREEN}) even at full size"))
        else:
            out.append(("error", f"{w}x{h} is drawn at half size and shown x2: at most {HALF_MAX}x{HALF_MAX} "
                                 f"(= one {SCREEN}x{SCREEN} screen). Draw it at half the on-screen size, or mark it "
                                 "fullsize (1:1, up to 240, always above the half-size sprites)"))
        return out
    lo, hi = ROLES[role][0]
    if asset.fullsize:
        lo, hi = lo * 2, hi * 2
    if role in ("background", "panorama"):
        want = hi if not asset.fullsize else SCREEN
        if (w, h) != (want, want):
            out.append(("warn", f"a {role} usually fills one screen: {want}x{want}, not {w}x{h}"))
    elif max(w, h) > hi or max(w, h) < lo:
        out.append(("warn", f"unusual for a {role.replace('_', ' ')} ({ROLES[role][1]}): {w}x{h}"))
    return out


def check(project) -> list[tuple[str, str, str]]:
    """[(level, asset name, message)] for every asset of a WowCube project; [] for another target."""
    target = str(getattr(project, "target", "wowcube") or "wowcube").lower()
    if target not in ("wowcube", "cube"):
        return []
    out = []
    for a in project.assets:
        if a.name == "0" or getattr(a, "keep", False):
            continue
        for level, msg in check_asset(a):
            out.append((level, a.name, msg))
    return out


GUIDE = """WowCube sprite sizes (each of the 24 screens is 240x240 pixels)
- Most sprites are drawn at HALF size and shown twice as big: on screen 64 px tall -> draw 32 px. At most
  120x120 drawn = one whole screen. Crisp shapes survive the x2; fine lines and soft brush texture do not.
- 'fullsize' sprites are drawn 1:1 (up to 240x240) and always sit ABOVE every half-size sprite (they hide
  it and the text): only for special cases.
- Typical drawn sizes:""" + "".join(f"\n    {r:14s} {d}" for r, (_, d) in ROLES.items()) + """
- Colours: each picture keeps at most 256 colours (one of them transparent); similar sprites share one
  palette. Flat colours and a few deliberate shades survive; smooth gradients, glows and textured brushes
  are reduced and may band. Full-colour pictures (backgrounds) have no transparency.
- Edges are cut hard (each pixel fully on or off) unless the sprite is marked soft-edged."""
