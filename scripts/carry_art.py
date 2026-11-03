#!/usr/bin/env python3
"""Carry-through plan: which packed records of an extracted game the manifest pack reuses byte for byte.

A game delivered without its art sources is extracted by scripts/extract_art.py, which keeps every packed
sprite, glyph and palette record verbatim in <out>/original/packed/ and lists them in <out>/extracted.json
(with a digest of each sprite's pixels). Re-encoding such a sprite from its PNG is not lossless: the packer
regroups palettes, may pick a smaller palette and sets its own flags. So the manifest pack
(build_pipeline.py pack -> pack.py --carry) reuses the original record of every sprite nobody changed:

  * a manifest sprite whose PNG in <workspace>/art/ still shows the extracted pixels (pixel digest) and whose
    manifest entry still says what the extraction wrote (size, colour tier, flags, pivot): its record is
    written as it was, only Pidx / Seq renumbered to the new asset ids; its palette is carried with it (a
    palette shared by several carried sprites is carried once);
  * a font glyph (font_<n>_<5 digits>) while its font's source is what the extraction saw: no
    <workspace>/fonts/<font>.fnt, or one with the digest extract_art recorded (listing `fonts`, the .fnt and
    its atlas pages). An edited or newly added source rebuilds that font's glyphs, and only that font's. A
    font source the original pack never held (a game that ships art/font_*.fnt it never packed) is not
    packed unless the manifest names it (`"fonts": ["font_<n>"]`); an unchanged or unpacked font's .fnt is
    not exported at all (`font_skip`), so it adds no glyph either;
  * the launcher icon (ico_idle) when the icon PNG and the manifest icon tier are unchanged.

Every other sprite (edited, added, or with changed manifest flags) is encoded from its PNG as usual. The
original asset order is kept, so an untouched game repacks to the same index.bin records.

    python scripts/carry_art.py --manifest plans/<game>_assets.json --workspace assets_<game> [--icon PATH]

prints the plan (what is carried, what is re-encoded and why).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_art  # noqa: E402

PLAN_VERSION = 1


def load_listing(manifest_path: str | Path) -> tuple[dict, Path] | None:
    """(listing, its folder) of the extraction the manifest came from (`_origin.listing`), or None."""
    manifest_path = Path(manifest_path)
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    rel = (data.get("_origin") or {}).get("listing")
    if not rel:
        return None
    path = Path(rel)
    path = path if path.is_absolute() else (manifest_path.parent / path)
    try:
        listing = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return listing, path.parent


def _same_sprite(raw: dict, expected: dict) -> str | None:
    """None when the manifest entry `raw` asks for what `expected` (the extraction's entry) packs; else why not."""
    from manifest_schema import _parse_sprite
    try:
        a, b = _parse_sprite(raw), _parse_sprite(expected)
    except (KeyError, TypeError, ValueError) as exc:
        return f"manifest entry unreadable ({exc})"
    for field in ("size", "color", "flags", "pivot"):
        if getattr(a, field) != getattr(b, field):
            return f"manifest {field} changed"
    return None


def font_plan(listing: dict, manifest: dict, fonts_dir: Path) -> dict:
    """Per BMFont source in <workspace>/fonts: `action` carry (packed, source unchanged: its glyph records are
    written as they were, the .fnt is not exported), rebuild (its glyphs are encoded anew from the .fnt) or
    skip (the original pack never held it and the manifest does not ask for it: not packed), and `why`."""
    recorded = listing.get("fonts")
    asked = {str(n) for n in (manifest.get("fonts") or [])}
    out: dict[str, dict] = {}
    for fnt in sorted(fonts_dir.glob("*.fnt")) if fonts_dir.is_dir() else []:
        name = fnt.stem
        if recorded is None:
            # an extraction made before fonts were recorded: the source cannot be compared, the old rule holds
            out[name] = {"action": "rebuild", "why": f"{fnt.name} present (the extraction recorded no font "
                                                      f"sources: re-run extract_art.py --force to compare)"}
            continue
        rec = recorded.get(name)
        if rec and rec.get("packed"):
            if rec.get("digest") and rec["digest"] == extract_art.font_digest(fnt):
                out[name] = {"action": "carry", "why": "source unchanged since the extraction"}
            elif rec.get("digest"):
                out[name] = {"action": "rebuild", "why": f"{fnt.name} or its atlas changed since the extraction"}
            else:
                out[name] = {"action": "rebuild", "why": f"{fnt.name} added (the extracted game had no source)"}
        elif name in asked:
            out[name] = {"action": "rebuild", "why": "not in the original pack, added by the manifest's fonts"}
        else:
            out[name] = {"action": "skip", "why": "the original pack never held it and the manifest's "
                                                  "\"fonts\" does not name it"}
    for name in asked - set(out):
        out[name] = {"action": "missing", "why": f"named by the manifest's fonts but no {name}.fnt in {fonts_dir}"}
    return out


def build_plan(manifest_path: str | Path, workspace: str | Path, icon_path: str | Path | None = None,
               fonts_dir: str | Path | None = None) -> dict | None:
    """The carry plan for one pack, or None when the manifest has no extraction behind it."""
    got = load_listing(manifest_path)
    if got is None:
        return None
    listing, ldir = got
    workspace = Path(workspace)
    fonts_dir = Path(fonts_dir) if fonts_dir is not None else workspace / "fonts"
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    wanted = {s.get("name"): s for s in manifest.get("sprites", []) if isinstance(s, dict)}

    pal_order = [a for a in listing.get("assets", []) if a.get("kind") == "PAL"]
    plan = {"version": PLAN_VERSION, "listing": str((ldir / "extracted.json").resolve()),
            "sprites": {}, "palettes": [], "icon": None,
            "order": {}, "links": {}, "rates": {}, "reencoded": {},
            "fonts": {}, "font_skip": [], "glyphs_rebuilt": {}}
    plan["fonts"] = font_plan(listing, manifest, fonts_dir)
    plan["font_skip"] = sorted(n for n, f in plan["fonts"].items() if f["action"] != "rebuild")
    for a in listing.get("assets", []):
        if a.get("kind") != "SPRITE" or "record" not in a:
            continue
        name = a["name"]
        record = ldir / a["record"]
        plan["order"][name] = a["id"]
        plan["links"][name] = a.get("next_frame")
        plan["rates"][name] = a.get("rate", 1)
        why = None
        if not record.is_file():
            why = f"record {record} missing"
        elif a.get("glyph"):
            f = plan["fonts"].get(a.get("font"))
            if f is not None and f["action"] == "rebuild":
                why = f"rebuilt from {a.get('font')}.fnt"
                plan["glyphs_rebuilt"][a["font"]] = plan["glyphs_rebuilt"].get(a["font"], 0) + 1
        elif name == extract_art.LAUNCHER_ICON:
            if icon_path is None or not Path(icon_path).is_file():
                why = "no icon PNG given"
            elif extract_art.pixel_digest(icon_path) != a.get("pixels"):
                why = "icon pixels changed"
            else:
                tier = manifest.get("icon") or {"color": "full", "side": 160}
                exp = extract_art.manifest_icon(a)
                if (tier.get("color", "full"), int(tier.get("side", 160))) != (exp["color"], exp["side"]):
                    why = "manifest icon tier changed"
        elif name not in wanted:
            why = "not in the manifest"
        else:
            png = workspace / "art" / f"{name}.png"
            if not png.is_file():
                why = f"no {png}"
            elif extract_art.pixel_digest(png) != a.get("pixels"):
                why = "pixels changed"
            else:
                why = _same_sprite(wanted[name], extract_art.manifest_sprite(a))
        if why is not None:
            if not a.get("glyph") and (name in wanted or name == extract_art.LAUNCHER_ICON):
                plan["reencoded"][name] = why
            continue
        entry = {"record": str(record.resolve()), "palette": a.get("palette"), "next_frame": a.get("next_frame")}
        if name == extract_art.LAUNCHER_ICON:
            plan["icon"] = entry
        else:
            plan["sprites"][name] = entry
    used = {e["palette"] for e in plan["sprites"].values() if e["palette"]}
    if plan["icon"] and plan["icon"]["palette"]:
        used.add(plan["icon"]["palette"])
    # every original palette is carried, also one no sprite uses any more (its sprites were re-encoded into
    # new palette groups) or never used: the original asset ids stay where they were
    used |= {p["name"] for p in pal_order}
    kinds = {"SPRITE": 0, "SOUND": 1, "PAL": 2, "MAP": 3}
    plan["original"] = [[kinds[a["kind"]], a["name"], a["id"]] for a in listing.get("assets", [])
                        if a.get("kind") in kinds and isinstance(a.get("id"), int)]
    for p in pal_order:
        if p["name"] in used:
            rec = ldir / p.get("record", "")
            if "record" not in p or not rec.is_file():
                # a carried sprite without its palette cannot be carried: re-encode the sprites of that palette
                for n in [n for n, e in plan["sprites"].items() if e["palette"] == p["name"]]:
                    del plan["sprites"][n]
                    if n in wanted:
                        plan["reencoded"][n] = f"palette record {p['name']} missing"
                if plan["icon"] and plan["icon"]["palette"] == p["name"]:
                    plan["icon"] = None
                    plan["reencoded"][extract_art.LAUNCHER_ICON] = f"palette record {p['name']} missing"
                continue
            plan["palettes"].append({"name": p["name"], "record": str(rec.resolve())})
    known = {p["name"] for p in pal_order}
    for n in [n for n, e in plan["sprites"].items() if e["palette"] and e["palette"] not in known]:
        del plan["sprites"][n]
        if n in wanted:
            plan["reencoded"][n] = "palette not in the listing"
    return plan


def font_lines(plan: dict | None) -> list[str]:
    """What the plan does with each font source, one line each (build_pipeline and this tool print them)."""
    if not plan:
        return []
    out = []
    for name, f in sorted(plan.get("fonts", {}).items()):
        n = plan.get("glyphs_rebuilt", {}).get(name, 0)
        if f["action"] == "rebuild":
            out.append(f"  font {name}: glyphs rebuilt from {name}.fnt ({f['why']}; {n} packed glyph record(s) "
                       f"replaced)")
        elif f["action"] == "carry":
            out.append(f"  font {name}: glyph records carried through ({f['why']})")
        elif f["action"] == "skip":
            out.append(f"  font {name}: not packed ({f['why']})")
        else:
            out.append(f"  WARNING: font {name}: {f['why']}")
    return out


def carried_names(plan: dict | None) -> set[str]:
    """Every sprite name the plan carries (not the icon)."""
    return set(plan["sprites"]) if plan else set()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--workspace", type=Path, required=True)
    ap.add_argument("--icon", type=Path, default=None)
    ap.add_argument("--json", action="store_true", help="print the whole plan as JSON")
    args = ap.parse_args(argv)
    icon = args.icon if args.icon is not None else args.workspace / "icon.png"
    plan = build_plan(args.manifest, args.workspace, icon)
    if plan is None:
        print("no extraction behind this manifest (no _origin.listing): nothing is carried through")
        return 0
    if args.json:
        print(json.dumps(plan, indent=1))
        return 0
    glyphs = sum(1 for n in plan["sprites"] if extract_art.GLYPH_RE.match(n))
    rebuilt = sum(plan.get("glyphs_rebuilt", {}).values())
    print(f"carried through unchanged: {len(plan['sprites']) - glyphs} sprite(s), {glyphs} font glyph(s), "
          f"{len(plan['palettes'])} palette(s), icon {'yes' if plan['icon'] else 'no'}; re-encoded: "
          f"{len(plan['reencoded'])} sprite(s), {rebuilt} font glyph(s)")
    for n, why in sorted(plan["reencoded"].items()):
        print(f"  re-encoded from its PNG: {n} ({why})")
    for line in font_lines(plan):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
