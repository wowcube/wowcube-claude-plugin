#!/usr/bin/env python3
"""cube_art-director CLI: style-locked asset generation with Codex.

  python art.py doctor   <spec>                     setup check: python deps, Codex CLI, ChatGPT login, model
  python art.py init     <dir>                      new project: art.json, style/STYLE.md, style/anchors/, refs/, drawn/
  python art.py candidates <spec> --subject "<what to draw>" [--n 3]
                                                    first style frames from the artist's refs/ (before any lock)
  python art.py style    <spec>                     profile the approved anchors -> style/profile.json + palette.png
  python art.py anchor   <spec> --originals [--count 3]
                                                    a modded game's own art is its style: anchor up to N of
                                                    its kept sprites (largest cut-outs, one per family),
                                                    picked automatically (scripts/extract_art.py runs it)
  python art.py anchor   <spec> --only a,b          promote approved assets to style anchors (profile rebuilt):
                                                    the final image (what qa measures) is the anchor; the
                                                    keyed raw-resolution look goes to anchors/hires/ and is
                                                    what Codex gets as the style reference
  python art.py gen      <spec> [--only a,b] [--set s] [--force] [--jobs 3]
                                                    Codex draws every asset that has no raw image yet
  python art.py process  <spec> [--only a,b]        key + fit (sets share scale) -> final images; with --only,
                                                    an incomplete set fits the members that have a raw image
                                                    together (warning "partial set": family leaders first),
                                                    a complete set is always refitted whole; every
                                                    keyed raw's backdrop decision goes to raw/keys.json
                                                    (qa reads the same); fixed_canvas assets are scaled
                                                    as drawn (no crop, no recentring); `keep` assets
                                                    (a modded game's own sprites) are copied byte-exact
                                                    from their original, never refitted
  python art.py qa       <spec> [--only a,b] [--set s]   checks + style scores; exit 1 on hard failures
  python art.py waive    <spec> --only a[,b] --check style[,set_area] --reason "<what the picture shows>"
                                                    a numeric FAIL that a look at the picture shows is false:
                                                    qa reports it WAIVED and does not count it while the
                                                    final image is unchanged (its hash is stored); waivable
                                                    checks: style, fill, set_centroid, set_area, set_height,
                                                    set_colour (never size, key, alpha, cut-out, missing,
                                                    empty, kept-file checks); --drop removes; no --only lists
  python art.py review   <spec>                     <workspace>/review.html for the artist
  python art.py feedback <spec> --file fb.json      fold the page's "Copy feedback" JSON into fixes.json
  python art.py all      <spec> [gen options]       gen -> process -> qa -> review
  python art.py budget   <spec>                     image budget: requests spent, the cap and where it comes from
  python art.py budget   <spec> --video <anim> [--video-frames N] [--credits C]
                                                    record one animation video job before it is submitted
                                                    (counts as its N frames; exit 4 when it does not fit)
  python art.py sheet    <spec> [--only a,b] [--set s] [--cols N] [--padding 2] [--name sheet]
                                                    the finished images on one grid PNG + a JSON atlas
                                                    (<workspace>/sheet/<name>.png + <name>.json: frames
                                                    x/y/w/h, one animation list per set)
  python art.py sizes    [<spec>]                   the WowCube size guide; with a spec, every asset's size
                                                    checked against its role (exit 1 on a size that cannot work)
  python art.py slice    <sheet.png> (--cell WxH | --grid COLSxROWS | --atlas a.json) [--names a,b,..]
                         [--padding P] [--margin M] [--out dir]
                                                    cut a sprite sheet someone sent into one named PNG per
                                                    sprite (empty cells skipped), ready to use as drawings
  python art.py doctor   [<spec>] --no-codex        art drawn in code or the artist's own: Codex is a note

Image budget (art_budget.py): every Codex request (each attempt of a sprite, each panorama
picture, each style candidate) is recorded in a ledger before it is made; `gen` and
`candidates` print spent/budget and refuse (exit 4, nothing drawn) a run that does not fit
in what is left; a run with nothing left to draw always passes. `--budget N` lowers the cap for
this run only (never stored; a number above the budget is refused unless `--over-budget` is given
too); `--over-budget` draws past the budget (only on the user's yes; such entries are marked in the
ledger). A context file that does not parse is an error (exit 2), never a silent default.

<spec> is an art.json project file or a WowCube manifest plans/<game>_assets.json
(then the workspace defaults to assets_<game>/ and final images go to its art/
folder, where the WowCube pack stage reads them). --workspace overrides.

Project layout (art.json kind):
  <project>/art.json, refs/ (artist references), drawn/ (artist drawings),
  style/STYLE.md + style/anchors/ + style/profile.json + style/candidates/,
  <workspace>/raw/ (model output, keys.json, prompts.json, logs/),
  <workspace>/final/ (exact-size images), <workspace>/qa/, <workspace>/review.html, <workspace>/fixes.json
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import art_budget  # noqa: E402
import art_codex  # noqa: E402
import art_qa  # noqa: E402
import art_review  # noqa: E402
import art_sizes  # noqa: E402
import art_style  # noqa: E402
from art_image import (fit_canvas, fit_opaque, fit_rgba, fit_rgba_set, has_transparency,  # noqa: E402
                       key_backdrop, match_colours, pick_key)
from art_spec import (apply_meta, colour_ref, dependency_order, fix_for, load_fixes,  # noqa: E402
                      load_project, original_of, read_json, validate)

HERE = Path(__file__).resolve().parent


def style_dir(p) -> Path:
    """One stable style folder per project (anchors may live anywhere)."""
    return p.workspace / "style" if p.kind == "cube-manifest" else p.root / "style"


def final_dir(p) -> Path:
    return p.workspace / ("art" if p.kind == "cube-manifest" else "final")


_WARNED: set = set()


def prompt_block(p) -> str:
    """The '## Prompt block' section of STYLE.md: the operational style
    paragraph injected into every prompt. A WowCube manifest's `_style` seeds
    it when STYLE.md has none; when both exist and differ, STYLE.md wins and a
    warning says so (the two must not drift apart silently)."""
    block = ""
    if p.bible and p.bible.exists():
        text = p.bible.read_text(encoding="utf-8")
        m = re.search(r"^##\s*Prompt block\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
        if m:
            block = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S).strip()
            if block.startswith("<") and block.endswith(">"):
                block = ""                      # untouched template placeholder
    style = getattr(p, "style_text", None)
    if not block and style:
        return style
    if block and style and " ".join(block.split()) != " ".join(style.split()) and "style" not in _WARNED:
        _WARNED.add("style")
        print("WARNING: STYLE.md Prompt block differs from the manifest's _style - STYLE.md is used; "
              "update _style (Stage 2) or STYLE.md so they agree", file=sys.stderr)
    return block


def ledger(p, args) -> "art_budget.Ledger":
    """The image ledger of this project (art_budget.py: where it lives, which budget applies)."""
    spec_data = read_json(args.spec) if p.kind == "art" else None
    return art_budget.for_workspace(p.root, p.name, p.workspace, cube=p.kind == "cube-manifest",
                                    spec_data=spec_data, cli_budget=getattr(args, "budget", None),
                                    override=getattr(args, "over_budget", False))


def gate_for(led, name: str, kind: str):
    return lambda attempt: led.charge(name, kind, attempt)


_HEX_RE = re.compile(r"#([0-9a-fA-F]{6})\b")


def variant_colours(p) -> list[str]:
    """Hex colours listed under STYLE.md's `## Variant colours` (or `## Variant colors`, with or without
    trailing words such as `(optional)`): the colours a
    legitimate variant may use besides the anchors' palette (the other ship colours, team colours). They
    widen the measured palette (art_style.variant_ramp); `style` / `anchor` rebuild the profile with them."""
    if not (p.bible and p.bible.exists()):
        return []
    text = re.sub(r"<!--.*?-->", "", p.bible.read_text(encoding="utf-8"), flags=re.S)
    m = re.search(r"^##[ \t]*Variant[ \t]+colou?rs\b[^\n]*$(.*?)(?=^##\s|\Z)", text, re.M | re.S | re.I)
    if not m:
        return []
    seen = []
    for h in _HEX_RE.findall(m.group(1)):
        if h.lower() not in seen:
            seen.append(h.lower())
    return seen


REF_EXTS = (".png", ".jpg", ".jpeg")


def reference_images(p) -> list[Path]:
    """The artist's reference images: refs/ and drawn/, every REF_EXTS file (any case), sorted. `doctor` and
    `candidates` read the same list."""
    return sorted(f for d in (p.root / "refs", p.root / "drawn") if d.is_dir() for f in d.iterdir()
                  if f.is_file() and f.suffix.lower() in REF_EXTS)


def load(args):
    p = load_project(args.spec, args.workspace)
    fixes = load_fixes(p.workspace)
    apply_meta(p, fixes)
    errs = validate(p)
    if errs:
        print("spec problems:\n  " + "\n  ".join(errs), file=sys.stderr)
        raise SystemExit(2)
    return p, fixes


def pick(p, only: str | None, set_name: str | None):
    names = set(only.split(",")) if only else None
    out = [a for a in p.assets if (names is None or a.name in names) and (set_name is None or a.set == set_name)]
    if names and names - {a.name for a in out}:
        raise SystemExit(f"unknown asset(s): {sorted(names - {a.name for a in out})}")
    return out


def cmd_line(args, *extra: str) -> str:
    """A copy-pasteable command for the current interpreter, script, spec and workspace."""
    parts = [sys.executable, str(Path(__file__).resolve()), *extra[:1], str(Path(args.spec).resolve())]
    if args.workspace:
        parts += ["--workspace", str(Path(args.workspace).resolve())]
    parts += list(extra[1:])
    if sys.platform == "win32":
        return " ".join(f'"{x}"' if (" " in x or "\\" in x) else x for x in parts)
    return " ".join(shlex.quote(x) for x in parts)


def resolve_ref(p, ref: str) -> Path:
    """An image reference that is not an asset name: absolute, or relative to
    the workspace (fixes.json refs such as raw/<frame>.png), or to the project
    root (art.json paths such as drawn/pose.png) - first one that exists."""
    r = Path(ref)
    if r.is_absolute():
        return r
    for base in (p.workspace, p.root):
        if (base / r).exists():
            return base / r
    return p.workspace / r


def keys_file(p) -> Path:
    return p.workspace / "raw" / "keys.json"


def load_keys(p) -> dict:
    f = keys_file(p)
    return read_json(f) if f.exists() else {}


def key_of(p, a, keys: dict, prof=None) -> str:
    """The backdrop colour an asset was DRAWN on: recorded at generation time, so
    adding anchors later can never flip how an existing raw image is keyed.
    Without a record (art drawn in code or by hand): "none" when the raw image
    has real transparency, else the prompt's pick. `process` records the
    decision in raw/keys.json and `qa` reads it back, so both use one key."""
    if a.key != "auto":
        return a.key
    if a.name in keys:
        return keys[a.name]
    f = p.workspace / "raw" / f"{a.name}.png"
    if f.exists():
        with Image.open(f) as im:
            if has_transparency(im):
                return "none"
    return pick_key(a.prompt)      # legacy raw without a record: prompt only, deterministic


# --------------------------------------------------------------------------- commands
def cmd_doctor(args) -> int:
    ok = True
    try:
        import numpy  # noqa: F401
        import PIL  # noqa: F401
        print(f"ok   python {sys.version.split()[0]}, pillow {PIL.__version__}, numpy {numpy.__version__}")
    except ImportError as e:
        ok = False
        print(f"FAIL python deps: {e} (pip install pillow numpy)")
    no_codex = getattr(args, "no_codex", False)
    for good, msg in art_codex.doctor():
        if no_codex:          # drawn in code or the artist's own art: Codex is information only
            print(("ok   " if good else "note ") + msg + ("" if good else " (not needed: --no-codex)"))
            continue
        ok &= good
        print(("ok   " if good else "FAIL ") + msg)
    if args.spec and Path(args.spec).exists() and Path(args.spec).is_file():
        try:
            p, _ = load(args)
            print(f"ok   spec: {len(p.assets)} assets, {len(p.anchors)} anchor(s), workspace {p.workspace}")
            if not p.anchors:
                if reference_images(p):
                    print("note no style anchors yet: run `candidates` (style frames from refs/ and drawn/), get "
                          "the artist's pick, then `style`")
                else:
                    print("note no style anchors yet and no references in refs/ or drawn/: draw the family leaders "
                          "(`gen --only <leaders>`, `process --only <leaders>`), get the approval, then "
                          "`anchor --only <leaders>` and `style`")
            print(f"ok   {ledger(p, args).status()}")
        except SystemExit:
            ok = False
        except art_budget.BudgetError as e:
            ok = False
            print(f"FAIL {e}")
    return 0 if ok else 1


def cmd_init(args) -> int:
    d = Path(args.spec)
    for sub in ("style/anchors", "style/candidates", "refs", "drawn"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    bible = d / "style" / "STYLE.md"
    if not bible.exists():
        shutil.copyfile(HERE.parent / "references" / "STYLE_TEMPLATE.md", bible)
    spec = d / "art.json"
    if not spec.exists():
        spec.write_text(json.dumps({
            "project": d.name, "workspace": "art_work",
            "style": {"bible": "style/STYLE.md", "anchors": []},
            "defaults": {"background": "key", "key": "auto", "alpha": "binary"},
            "assets": [{"name": "example_00", "size": [40, 40], "set": "example", "motion": True,
                        "colour_lock": True, "prompt": "describe the subject, pose and colours here"}],
        }, indent=2), encoding="utf-8")
    print(f"project ready: {spec}\n- artist references -> {d / 'refs'}, drawings -> {d / 'drawn'}"
          f"\n- write the style bible {bible}\n- approved style frames go to {d / 'style' / 'anchors'} "
          f"and art.json style.anchors")
    return 0


def cmd_candidates(args) -> int:
    """Style frames BEFORE the lock: the artist's refs/ (and drawn/) are attached
    as style references; the artist picks one -> it becomes the first anchor."""
    p, fixes = load(args)
    refs = reference_images(p)[:6]
    if not refs:
        raise SystemExit(f"no references in {p.root / 'refs'} or {p.root / 'drawn'}")
    if not args.subject:
        raise SystemExit('candidates needs --subject "a representative character/prop/scene in this game"')
    out = style_dir(p) / "candidates"
    body = "\n\n".join(x for x in (prompt_block(p), args.subject) if x)
    led = ledger(p, args)
    if not led.can_afford(args.n):
        print(led.refusal(args.n), file=sys.stderr)
        return art_budget.EXIT_OVER_BUDGET
    ok_all = True
    for i in range(args.n):
        name = f"candidate_{i + 1:02d}"
        prompt = art_codex.build_prompt(name, body + f"\n\n(Variation {i + 1} of {args.n}: interpret the "
                                        "references faithfully; vary only composition details.)",
                                        n_anchors=0, subject=False, sketch=False, background="opaque",
                                        key="magenta", n_style_refs=len(refs))
        ok, info = art_codex.run(name, prompt, refs, out / f"{name}.png", out / "logs",
                                 gate=gate_for(led, name, "candidate"))
        ok_all &= ok
        print(f"  {'ok ' if ok else 'ERR'} {name}: {info}")
    print(led.status())
    print(f"candidates in {out}: show them to the artist; copy the approved one to style/anchors/, list it in "
          f"art.json and run: {cmd_line(args, 'style')}")
    return 0 if ok_all else 1


def cmd_style(args) -> int:
    p, _ = load(args)
    var = variant_colours(p)
    prof = art_style.extract(p.anchors, style_dir(p), k=args.k, variants=var)
    if var:
        print(f"variant colours from STYLE.md (palette widened): {', '.join('#' + h for h in var)}")
    print(f"profile: {style_dir(p) / 'profile.json'}  palette: {', '.join(prof['palette_hex'][:12])}"
          f"{' ...' if len(prof['palette_hex']) > 12 else ''}\nthresholds: {prof['thresholds']}"
          + ("" if len(p.anchors) > 1 else "\nnote: one anchor -> default thresholds (no self-calibration)"))
    return 0


def _approved_look(p, a, keys: dict) -> Image.Image:
    """The asset as approved, at raw resolution: keyed, and colour-matched the
    same way processing matched it (so an anchor never differs from the final)."""
    raw = p.workspace / "raw"
    img = Image.open(raw / f"{a.name}.png")
    if a.background != "key":
        return img.convert("RGBA")
    img = key_backdrop(img, key_of(p, a, keys))
    members = [m for m in p.assets if m.set == a.set and tuple(m.size) == tuple(a.size)] if a.set else [a]
    i = members.index(a)
    j = colour_ref(members, i)
    if j != i and (raw / f"{members[j].name}.png").exists():
        ref = key_backdrop(Image.open(raw / f"{members[j].name}.png"), key_of(p, members[j], keys))
        img = match_colours(img, ref)
    return img


def hires_of(anchor: Path) -> Path:
    """The raw-resolution look of an anchor (`anchors/hires/<name>.png`), when `anchor` saved one."""
    return anchor.parent / "hires" / anchor.name


ORIGINAL_ANCHOR_SKIP = ("launcher_icon", "0")


def _family(a) -> str:
    """One family per animation / set / numbered series (hero_walk_01 and hero_walk_02 are one)."""
    if a.set:
        return a.set
    return re.sub(r"[_-]?\d+$", "", a.name) or a.name


def pick_originals(p, count: int = 3) -> list[str]:
    """The kept sprites that best show a modded game's style: cut-outs (`background: key`) first, the largest
    visible area first, one per family, at least 8x8 visible pixels; full pictures only when there are not
    enough cut-outs. Never the launcher icon or the packer's slot 0."""
    scored = []
    for a in p.assets:
        if not a.keep or a.name in ORIGINAL_ANCHOR_SKIP or a.name.startswith("font_"):
            continue
        f = original_of(p, a)
        if not f.exists():
            f = final_dir(p) / f"{a.name}.png"
        if not f.exists():
            continue
        with Image.open(f) as im:
            area = int((np.array(im.convert("RGBA"))[..., 3] > 0).sum())
        if area < 64:
            continue
        scored.append((a.background != "key", -area, a.name, _family(a)))
    picked, families = [], set()
    for _opaque, _area, name, fam in sorted(scored):
        if fam in families:
            continue
        picked.append(name)
        families.add(fam)
        if len(picked) >= count:
            break
    return picked


def cmd_anchor(args) -> int:
    """Promote approved assets to style anchors (the style lock grows with
    every approval: the first approved character becomes the reference for
    every later character).

    The anchor is the FINAL image (exact size, what the game shows): `style`
    measures the profile on it and `qa` scores finals against that profile,
    so both sides are measured at the same scale (a supersampled raw anchor
    made every small final fail the outline and palette numbers, and a
    modded game's own sprites have no raw at all). When a raw image exists,
    its keyed raw-resolution look is saved next to it as anchors/hires/<name>.png:
    that is the picture Codex gets as the style reference (a 24 px final says
    little to the model). Not profiled: `style` reads anchors/*.png only."""
    p, _ = load(args)
    if getattr(args, "originals", False):
        if args.only:
            raise SystemExit("anchor: --originals picks the sprites itself; pass either --originals or --only")
        names = pick_originals(p, max(1, args.count))
        if not names:
            raise SystemExit("anchor --originals: no kept sprite with an original and at least 8x8 visible pixels "
                             "(extract the game's art first: scripts/extract_art.py --manifest)")
        print(f"style reference = the game's own sprites: {', '.join(names)}")
        args.only = ",".join(names)
    if not args.only:
        raise SystemExit("anchor needs --only name1,name2 (the approved assets to promote) or --originals")
    sdir = style_dir(p) / "anchors"
    sdir.mkdir(parents=True, exist_ok=True)
    keys = load_keys(p)
    added = []
    for a in pick(p, args.only, None):
        final = final_dir(p) / f"{a.name}.png"
        has_raw = (p.workspace / "raw" / f"{a.name}.png").exists()
        if not final.exists() and not has_raw:
            raise SystemExit(f"{a.name}: no final or raw image to promote (run process first)")
        dst = sdir / f"{a.name}.png"
        if final.exists():
            shutil.copyfile(final, dst)
        else:
            print(f"  NOTE: {a.name}: no final image yet - anchoring its raw look; run process and anchor it "
                  f"again so the profile is measured at final size", file=sys.stderr)
            _approved_look(p, a, keys).save(dst)
        if has_raw and final.exists():
            hires_of(dst).parent.mkdir(parents=True, exist_ok=True)
            _approved_look(p, a, keys).save(hires_of(dst))
        added.append(dst)
    if p.kind == "art":
        spec = Path(args.spec)
        data = read_json(spec)
        anchors = data.setdefault("style", {}).setdefault("anchors", [])
        for dst in added:
            try:
                rel = dst.resolve().relative_to(p.root.resolve()).as_posix()
            except ValueError:
                rel = str(dst.resolve())
            if rel not in anchors:
                anchors.append(rel)
        spec.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    p2, _ = load(args)
    art_style.extract(p2.anchors, style_dir(p2), k=args.k, variants=variant_colours(p2))
    print(f"anchors now: {', '.join(x.name for x in p2.anchors)} (profile rebuilt)")
    return 0


def full_prompt(p, a, fixes: dict, block: str) -> str:
    parts = []
    if block:
        parts.append(block)
    if a.view:
        parts.append(f"Viewpoint: {a.view}.")
    parts.append(a.prompt.strip())
    g, _ = fix_for(fixes, "*")
    t, _ = fix_for(fixes, a.name)
    parts += [x for x in (g, t) if x]
    return "\n\n".join(parts)


_NEG_RE = re.compile(r"\b(?:no|not|never|without|avoid|remove|drop|instead of|less)\s+(?:a |an |the |any )?"
                     r"([a-z][a-z\-]*(?:\s+[a-z][a-z\-]*){0,2})", re.I)
_STOP = {"and", "or", "but", "with", "on", "in", "of", "to", "at", "for", "the", "a", "an"}


def note_conflicts(note: str, text: str) -> list[str]:
    """Phrases a fixes.json note rules out ("no outline", "without gradients") that the prompt text still asks
    for. A note is only APPENDED to the prompt: it never removes the contradicting words, and the model often
    follows the first instruction. A heuristic for a warning, never a gate."""
    found = []
    low = " ".join(text.lower().split())
    for m in _NEG_RE.finditer(note or ""):
        words = [w for w in m.group(1).lower().split() if w not in _STOP]
        for n in range(len(words), 0, -1):          # the longest phrase the prompt still says
            phrase = " ".join(words[:n])
            if len(phrase) < 4:
                continue
            for hit in re.finditer(r"\b" + re.escape(phrase) + r"\b", low):
                before = low[max(0, hit.start() - 12):hit.start()]
                if not re.search(r"\b(no|not|never|without|avoid)\s+(a |an |the |any )?$", before):
                    found.append(phrase)
                    break
            if found and found[-1] == phrase:
                break
    return sorted(set(found))


def warn_note_conflicts(p, todo, fixes: dict, block: str) -> None:
    g, _ = fix_for(fixes, "*")
    seen = set()
    for a in todo:
        t, _ = fix_for(fixes, a.name)
        base = "\n".join(x for x in (block, a.prompt) if x)
        for label, note in (("*", g), (a.name, t)):
            bad = note_conflicts(note, base)
            if bad:
                in_block = any(b in " ".join((block or "").lower().split()) for b in bad)
                where = ("STYLE.md's Prompt block (and the manifest's _style)" if in_block
                         else "its gen_prompt in the manifest" if p.kind == "cube-manifest" else "its prompt in art.json")
                if (label, tuple(bad), in_block) in seen:
                    continue
                seen.add((label, tuple(bad), in_block))
                print(f"WARNING: fixes.json[{label!r}] rules out {', '.join(repr(b) for b in bad)} but {a.name}'s "
                      f"prompt still asks for it: a note is only appended and does not override. Edit {where} "
                      f"(cube_art-director SKILL.md, 'Style notes edit the source').", file=sys.stderr)


def cmd_gen(args) -> int:
    p, fixes = load(args)
    raw = p.workspace / "raw"
    logs = raw / "logs"
    raw.mkdir(parents=True, exist_ok=True)
    prof = art_style.load_profile(style_dir(p))
    block = prompt_block(p)
    todo = [a for a in pick(p, args.only, args.set)
            if not a.keep and (args.force or not (raw / f"{a.name}.png").exists())]
    prompts_f = raw / "prompts.json"
    prompts = read_json(prompts_f) if prompts_f.exists() else {}
    keys = load_keys(p)
    names = {a.name for a in p.assets}
    failed: set[str] = set()
    # Panoramas (cube manifests): ONE picture per `_panoramas` entry, drawn once and cut into its
    # row-major pieces (grid [cols, rows]); the pieces are never drawn one by one.
    piece_of = {pc: pn for pn, pv in p.panoramas.items() for pc in pv.get("pieces", [])}
    wanted = {piece_of[a.name] for a in todo if a.name in piece_of}
    led = ledger(p, args)
    need = len(wanted) + sum(1 for a in todo if a.name not in piece_of and not a.source)
    if not led.can_afford(need):
        print(led.refusal(need), file=sys.stderr)
        return art_budget.EXIT_OVER_BUDGET
    warn_note_conflicts(p, todo, fixes, block)

    def refs_for(a):
        # the raw-resolution look of an anchor when `anchor` saved one (a final may be 24 px)
        anchors = [hires_of(x) if hires_of(x).exists() else x for x in p.anchors if x.exists()]
        _, fix_ref = fix_for(fixes, a.name)
        subj = fix_ref or a.subject_ref
        subj_path = None
        if subj:
            subj_path = (raw / f"{subj}.png") if subj in names else resolve_ref(p, subj)
        sk = (p.root / a.sketch) if a.sketch else None
        return anchors, subj, subj_path, sk

    def job(a):
        if a.source:
            shutil.copyfile(p.root / a.source, raw / f"{a.name}.png")
            return a.name, True, "artist source copied"
        anchors, subj, subj_path, sk = refs_for(a)
        if subj in failed:
            return a.name, False, f"skipped: its subject reference {subj} failed"
        if subj_path is not None and not subj_path.exists():
            return a.name, False, f"subject reference {subj_path} does not exist"
        body = full_prompt(p, a, fixes, block)
        key = a.key if a.key != "auto" else art_style.suggest_key(prof, a.prompt)
        prompt = art_codex.build_prompt(a.name, body, n_anchors=len(anchors), subject=subj_path is not None,
                                        sketch=sk is not None, background=a.background, key=key)
        refs = anchors + ([subj_path] if subj_path is not None else []) + ([sk] if sk is not None else [])
        ok, info = art_codex.run(a.name, prompt, refs, raw / f"{a.name}.png", logs,
                                 gate=gate_for(led, a.name, "asset"))
        if ok:
            prompts[a.name] = body
            keys[a.name] = key
        return a.name, ok, info

    pano_ok = 0
    for pname in sorted(wanted):
        pv = p.panoramas[pname]
        ok, info = draw_panorama(p, pname, pv, block, fixes, raw, logs,
                                 gate=gate_for(led, f"_pano_{pname}", "panorama"))
        pano_ok += int(ok)
        print(f"  {'ok ' if ok else 'ERR'} panorama {pname} -> {', '.join(pv.get('pieces', []))}: {info}", flush=True)
        if ok:
            for pc in pv.get("pieces", []):
                prompts[pc] = f"(cut from panorama {pname})"
                keys[pc] = "opaque"
        else:
            failed.update(pv.get("pieces", []))
    pieces = [a for a in todo if a.name in piece_of]
    todo = [a for a in todo if a.name not in piece_of]
    if wanted:
        prompts_f.write_text(json.dumps(prompts, indent=1, ensure_ascii=False), encoding="utf-8")
        keys_file(p).write_text(json.dumps(keys, indent=1), encoding="utf-8")

    for batch in dependency_order(todo, fixes, names):
        with cf.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            for f in cf.as_completed([pool.submit(job, a) for a in batch]):
                name, ok, info = f.result()
                print(f"  {'ok ' if ok else 'ERR'} {name}: {info}", flush=True)
                if not ok:
                    failed.add(name)
        prompts_f.write_text(json.dumps(prompts, indent=1, ensure_ascii=False), encoding="utf-8")
        keys_file(p).write_text(json.dumps(keys, indent=1), encoding="utf-8")
    sprite_failed = failed - set(piece_of)
    pano_line = (f" + {pano_ok}/{len(wanted)} panorama picture(s) cut into {len(pieces)} piece(s)" if wanted else "")
    print(f"gen: {len(todo) - len(sprite_failed)}/{len(todo)} sprite(s) drawn{pano_line}"
          + (f"; failed: {','.join(sorted(failed))}" if failed else ""))
    print(led.status() + ("" if led.remaining() is None else f"; {led.remaining()} left"))
    if failed:
        print(f"retry: {cmd_line(args, 'gen', '--only', ','.join(sorted(failed)), '--force')}")
    return 1 if failed else 0


def draw_panorama(p, pname: str, pv: dict, block: str, fixes: dict, raw: Path, logs: Path,
                  gate=None) -> tuple[bool, str]:
    """Draw one panorama with Codex (opaque, anchors attached) and cut it into the pieces' raw images."""
    pieces = pv.get("pieces", [])
    cols, rows = (pv.get("grid") or [2, 2])[:2]
    if len(pieces) != cols * rows:
        return False, f"grid {cols}x{rows} does not match {len(pieces)} pieces"
    extra, _ = fix_for(fixes, pname)
    body = "\n\n".join(x for x in (
        block, pv.get("gen_prompt", ""),
        f"One continuous picture that will be cut into a {cols}x{rows} grid of equal screens: no focal object on "
        "the cut lines; the left and right edges join seamlessly (it repeats around the cube).", extra) if x)
    # "anchors": [asset names] in the _panoramas entry picks the style anchors to attach (scenery anchors, not a
    # character that would leak into the landscape); without the field every anchor goes, an empty list sends none
    want = pv.get("anchors")                # absent = every anchor, [] = none
    anchors = [x for x in p.anchors if x.exists() and (want is None or x.stem in set(want))]
    prompt = art_codex.build_prompt(f"_pano_{pname}", body, n_anchors=len(anchors), subject=False, sketch=False,
                                    background="opaque", key="magenta")
    src = raw / f"_pano_{pname}.png"
    ok, info = art_codex.run(f"_pano_{pname}", prompt, anchors, src, logs, gate=gate)
    if not ok:
        return False, info
    img = Image.open(src).convert("RGB")
    w, h = img.width // cols, img.height // rows
    for i, piece in enumerate(pieces):
        r, c = divmod(i, cols)
        img.crop((c * w, r * h, (c + 1) * w, (r + 1) * h)).save(raw / f"{piece}.png")
    return True, info


# Approvals of fixes.json "@post" scripts live OUTSIDE every workspace (a downloaded or shared workspace can
# ship any file of its own): {"<resolved workspace path>": ["<sha256 of an approved script>", ...]}.
TRUST_FILE = Path.home() / ".wowcube" / "trusted_post.json"


def post_script(p, post) -> tuple[Path | None, str]:
    """(script, "") for a `@post` value that names a file inside the workspace, else (None, why). Absolute
    paths, drive letters, `..` and anything that resolves outside the workspace (a symlink escape) are refused."""
    text = str(post or "").strip()
    norm = text.replace("\\", "/")
    if (not text or norm.startswith("/") or re.match(r"^[A-Za-z]:", norm) or ".." in norm.split("/")
            or Path(text).is_absolute()):
        return None, f"@post {text!r}: must be a relative path inside the workspace (no absolute path, no '..')"
    root = p.workspace.resolve()
    script = (root / norm).resolve()
    try:
        script.relative_to(root)
    except ValueError:
        return None, f"@post {text!r} resolves to {script}, outside the workspace {root}"
    if not script.is_file():
        return None, f"@post: {script} not found (fixes.json)"
    return script, ""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# Runs the approved bytes, fed through stdin, as `python <script> <final dir> <names>` would: argv[0] and __file__
# name the script, sys.path[0] is its folder. The file is never opened again after it was hashed, so a writer
# that swaps or edits it later (a hardlink, a junction) changes nothing that runs.
_POST_RUNNER = ("import os, sys; src = sys.stdin.buffer.read(); sys.argv = sys.argv[1:]; "
                "sys.path[0] = os.path.dirname(sys.argv[0]); "
                "g = {'__name__': '__main__', '__file__': sys.argv[0], '__builtins__': __builtins__}; "
                "exec(compile(src, sys.argv[0], 'exec'), g)")


def _trust_db() -> dict:
    try:
        data = json.loads(TRUST_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def post_trusted(p, data: bytes) -> bool:
    """Were exactly these script bytes (their sha256) approved for this workspace (its resolved path)?"""
    approved = _trust_db().get(str(p.workspace.resolve()), [])
    return isinstance(approved, list) and _sha256(data) in approved


def trust_post(p, data: bytes) -> None:
    """Record the user's approval of this script's current content for this workspace (`--trust-post`)."""
    db = _trust_db()
    key = str(p.workspace.resolve())
    entries = [h for h in db.get(key, []) if isinstance(h, str)]
    digest = _sha256(data)
    if digest not in entries:
        entries.append(digest)
    db[key] = entries
    TRUST_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRUST_FILE.write_text(json.dumps(db, indent=1), encoding="utf-8")


def _hash(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()[:12]


def cmd_process(args) -> int:
    p, fixes = load(args)
    raw, out = p.workspace / "raw", final_dir(p)
    post = fixes.get("@post")
    script = None
    if post:
        # checked before any final is replaced: a requested fix that cannot run fails the whole run
        script, why = post_script(p, post)
        if script is None:
            print(f"ERROR: {why}; nothing processed", file=sys.stderr)
            return 1
        post_bytes = script.read_bytes()       # read ONCE: these bytes are hashed, approved and run
        if getattr(args, "trust_post", False):
            trust_post(p, post_bytes)
            print(f"  @post {post}: approved for {p.workspace.resolve()} (sha256 recorded in {TRUST_FILE})")
        elif not post_trusted(p, post_bytes):
            # fixes.json can come with a downloaded or shared workspace: never run its code unasked
            print(f"ERROR: @post not run - fixes.json asks to run `python {script} {out} <names>`, and this script "
                  f"(this content, in this workspace) was never approved. Read it; if it is yours, run process again "
                  f"with --trust-post (the approval is stored in {TRUST_FILE}, keyed by workspace and sha256: a "
                  f"changed script needs a new approval). Nothing was processed.", file=sys.stderr)
            return 1
    out.mkdir(parents=True, exist_ok=True)
    if p.kind == "cube-manifest":
        Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(out / "0.png")   # packer sentinel
    keys = load_keys(p)
    keys_before = dict(keys)
    selected = {a.name for a in pick(p, args.only, None)}
    provenance_f = p.workspace / "qa" / "provenance.json"
    provenance = read_json(provenance_f) if provenance_f.exists() else {}
    problems = []
    written: list[str] = []
    for a in p.assets:
        if not a.keep or a.name not in selected:
            continue
        # carried through unchanged: the original, byte for byte, never keyed, refitted or colour-matched
        src, dst = original_of(p, a), out / f"{a.name}.png"
        if src.exists():
            if not dst.exists() or dst.read_bytes() != src.read_bytes():
                shutil.copyfile(src, dst)
            provenance[a.name] = {"keep": True, "final": _hash(dst)}
            print(f"  {a.name} -> kept (original copied unchanged)")
        elif dst.exists():
            provenance[a.name] = {"keep": True, "final": _hash(dst), "no_original": True}
            print(f"  {a.name} -> kept (no original at {src}; the final in place stays as it is)")
        else:
            problems.append(f"{a.name}: keep, but neither its original {src} nor a final {dst} exists "
                            f"(extract the game's art first: scripts/extract_art.py)")
    groups: dict[tuple, list] = {}
    for a in p.assets:
        if a.keep:
            continue
        if a.background == "key" and a.set:
            groups.setdefault(("set", a.set, tuple(a.size)), []).append(a)
        else:
            groups.setdefault(("one", a.name), []).append(a)
    for members in groups.values():
        if not any(m.name in selected for m in members):
            continue          # a set is always re-fitted whole, even when --only names one member
        missing = [m.name for m in members if not (raw / f"{m.name}.png").exists()]
        partial = False
        if missing:
            present = [m for m in members if m.name not in missing]
            if not args.only or not present or len(members) == 1:
                # a full run never fits part of a set: the shared scale would no longer match
                problems.append(f"set {'+'.join(m.name for m in members)}: no raw image for {','.join(missing)}")
                continue
            # --only <family leaders> before the rest of the family is drawn: fit the members that have a raw
            # image TOGETHER (shared scale among them) so the leaders can be reviewed; the whole set is refitted
            # (one shared scale for every member) as soon as the family is complete
            print(f"  WARNING: partial set: refit when the family is complete - fitting "
                  f"{'+'.join(m.name for m in present)} without {','.join(missing)}", file=sys.stderr)
            members, partial = present, True
        first = members[0]
        if first.background == "opaque":
            outs = [fit_opaque(Image.open(raw / f"{first.name}.png"), tuple(first.size))]
        else:
            for m in members:
                keys.setdefault(m.name, key_of(p, m, keys))     # one decision, shared with qa
            keyed = [key_backdrop(Image.open(raw / f"{m.name}.png"), keys[m.name]) for m in members]
            matched = list(keyed)
            for i in range(len(members)):         # colour lock is independent of motion
                j = colour_ref(members, i)
                if j != i:
                    matched[i] = match_colours(keyed[i], keyed[j])
            if all(m.fixed_canvas for m in members):
                # scaled as drawn: a draining ring or a progress bar keeps its place and size in every frame
                sizes = {k.size for k in keyed}
                if len(sizes) > 1:
                    print(f"  WARNING: fixed_canvas set {'+'.join(m.name for m in members)}: raw canvases differ "
                          f"({', '.join(f'{w}x{h}' for w, h in sorted(sizes))}); draw every frame on one canvas",
                          file=sys.stderr)
                outs = [fit_canvas(k, tuple(m.size), m.alpha == "binary") for m, k in zip(members, matched)]
            elif any(m.fixed_canvas for m in members):
                problems.append(f"set {'+'.join(m.name for m in members)}: fixed_canvas on only some members "
                                f"({','.join(m.name for m in members if m.fixed_canvas)}); set it on the whole set")
                continue
            elif any(m.motion for m in members):
                outs = fit_rgba_set(matched, tuple(first.size), [m.alpha == "binary" for m in members])
            else:
                outs = [fit_rgba(k, tuple(m.size), m.alpha == "binary") for m, k in zip(members, matched)]
        for m, o in zip(members, outs):
            o.save(out / f"{m.name}.png")
            provenance[m.name] = {"raw": _hash(raw / f"{m.name}.png"), "final": _hash(out / f"{m.name}.png")}
            if partial:
                provenance[m.name]["partial_set"] = True    # cleared by the next whole-set fit
        print(f"  {'+'.join(m.name for m in members)} -> {first.size[0]}x{first.size[1]}"
              + (" (partial set)" if partial else ""))
        written.extend(m.name for m in members)
    if script is not None and written:
        # a reviewer's processing fix that no option expresses (outline, crop, chroma clamp) lives in one workspace
        # script, re-applied on every process run instead of being silently undone by it
        rc = subprocess.run([sys.executable, "-c", _POST_RUNNER, str(script), str(out), *written],
                            input=post_bytes, cwd=str(p.workspace)).returncode
        print(f"  @post {post} on {len(written)} final(s): exit {rc}")
        if rc != 0:
            problems.append(f"@post {post} failed (exit {rc}): the finals of this run are unfinished")
        for n in written:
            if (out / f"{n}.png").exists():
                provenance[n]["final"] = _hash(out / f"{n}.png")
                provenance[n]["post"] = post
    provenance_f.parent.mkdir(parents=True, exist_ok=True)
    provenance_f.write_text(json.dumps(provenance, indent=1), encoding="utf-8")
    if keys != keys_before:
        keys_file(p).parent.mkdir(parents=True, exist_ok=True)
        keys_file(p).write_text(json.dumps(keys, indent=1), encoding="utf-8")
    for pr in problems:
        print(pr, file=sys.stderr)
    return 1 if problems else 0


def cmd_qa(args) -> int:
    p, _ = load(args)
    prof = art_style.load_profile(style_dir(p))
    if prof is None:
        print("NOTE: no style profile yet (run `style` once anchors are approved) - style scores are UNCHECKED",
              file=sys.stderr)
    elif sorted(prof.get("variant_hex", [])) != sorted("#" + h for h in variant_colours(p)):
        print("WARNING: STYLE.md's '## Variant colours' changed since the profile was built: run `style` again "
              "so the palette check uses them", file=sys.stderr)
    scope = {a.name for a in pick(p, args.only, args.set)} if (args.only or args.set) else None
    keys = load_keys(p)
    # the key process used (recorded, else the same decision process makes): never "both keys" by default
    keys = {a.name: key_of(p, a, keys) for a in p.assets if a.background == "key"}
    fails, _ = art_qa.run(p, final_dir(p), prof, keys=keys, scope=scope)
    report = (p.workspace / "qa" / "report.txt").read_text(encoding="utf-8")
    print("\n".join(line for line in report.splitlines() if not line.startswith("PASS")))
    for level, name, msg in art_sizes.check(p):          # the spec's sizes against each sprite's role
        if scope is None or name in scope:
            print(f"SIZE {level.upper()} {name}: {msg}", file=sys.stderr)
    return 1 if fails else 0


def cmd_waive(args) -> int:
    """Record (or with --drop remove) a waiver: a numeric QA check that a look at the picture showed to be false
    for this asset. Bound to the final image's hash: redraw or reprocess it and the check counts again."""
    import datetime
    p, _ = load(args)
    waivers = art_qa.load_waivers(p)
    if not args.only:
        if not waivers:
            print("no waivers")
        for name, checks in sorted(waivers.items()):
            for cid, w in sorted(checks.items()):
                f = final_dir(p) / f"{name}.png"
                live = f.exists() and art_qa.file_hash(f) == w.get("sha256")
                print(f"{name}: {cid} - {w.get('reason', '')}" + ("" if live else "   (STALE: the image changed)"))
        return 0
    checks = [c.strip() for c in (args.check or "").split(",") if c.strip()]
    if not checks:
        raise SystemExit("waive needs --check <id>[,<id>] (waivable: " + ", ".join(art_qa.WAIVABLE) + ")")
    for c in checks:
        if c in art_qa.UNWAIVABLE:
            raise SystemExit(f"waive: '{c}' ({art_qa.UNWAIVABLE[c]}) is a technical check and cannot be waived: "
                             f"fix it (process, the key, the size). Waivable: {', '.join(art_qa.WAIVABLE)}")
        if c not in art_qa.WAIVABLE:
            raise SystemExit(f"waive: unknown check '{c}' (waivable: {', '.join(art_qa.WAIVABLE)})")
    assets = pick(p, args.only, None)
    if not args.drop:
        reason = (args.reason or "").strip()
        if not reason or "\n" in reason:
            raise SystemExit('waive needs --reason "<one line: what you saw in the picture>"')
    for a in assets:
        f = final_dir(p) / f"{a.name}.png"
        if args.drop:
            for c in checks:
                (waivers.get(a.name) or {}).pop(c, None)
            continue
        if a.keep:
            raise SystemExit(f"waive: {a.name} is kept (`keep`): only technical checks apply to it")
        if not f.exists():
            raise SystemExit(f"waive: {a.name} has no final image (run process, look at it, then waive)")
        for c in checks:
            waivers.setdefault(a.name, {})[c] = {"reason": reason, "sha256": art_qa.file_hash(f),
                                                 "date": datetime.date.today().isoformat()}
    where = art_qa.save_waivers(p, waivers)
    verb = "dropped" if args.drop else "waived"
    print(f"{verb}: {', '.join(a.name for a in assets)}: {', '.join(checks)} -> {where}")
    if not args.drop:
        print("  holds while the final image is unchanged; run qa again")
    return 0


def cmd_sizes(args) -> int:
    """The size guide; with a spec, every asset's size against its role (exit 1 when one cannot work)."""
    print(art_sizes.GUIDE)
    if not args.spec:
        return 0
    p, _ = load(args)
    findings = art_sizes.check(p)
    print()
    if not findings:
        print(f"sizes: all {len(p.assets)} asset(s) fit their role" if p.target.lower() in ("wowcube", "cube")
              else f"sizes: target {p.target!r}, the cube size rules do not apply")
    for level, name, msg in findings:
        print(f"{level.upper():5s} {name} ({art_sizes.role_of(p.get(name))}): {msg}")
    return 1 if any(level == "error" for level, _, _ in findings) else 0


def _cells(img_w: int, img_h: int, cell, grid, padding: int, margin: int) -> list[tuple[int, int, int, int]]:
    """(x, y, w, h) per cell, row by row."""
    if grid:
        cols, rows = grid
        cw = (img_w - 2 * margin - padding * (cols - 1)) // cols
        ch = (img_h - 2 * margin - padding * (rows - 1)) // rows
    else:
        cw, ch = cell
        cols = (img_w - 2 * margin + padding) // (cw + padding)
        rows = (img_h - 2 * margin + padding) // (ch + padding)
    if cw < 1 or ch < 1 or cols < 1 or rows < 1:
        raise ValueError(f"the grid does not fit a {img_w}x{img_h} sheet")
    return [(margin + c * (cw + padding), margin + r * (ch + padding), cw, ch)
            for r in range(rows) for c in range(cols)]


def _wh(text: str, what: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d+)\s*[xX*,]\s*(\d+)\s*", text or "")
    if not m:
        raise ValueError(f"{what} {text!r}: write it as WxH, e.g. 32x32")
    return int(m.group(1)), int(m.group(2))


def cmd_slice(args) -> int:
    """Cut a sprite sheet into one named PNG per sprite: by a cell size, a COLSxROWS grid or a JSON atlas
    (TexturePacker "JSON hash" / "array", or the one `sheet` writes). Fully transparent cells are skipped.
    The PNGs are drawings to process like any other (`"source": "drawn/<name>.png"` in art.json)."""
    sheet_path = Path(args.spec)
    if not sheet_path.is_file():
        print(f"ERROR: no sheet {sheet_path}", file=sys.stderr)
        return 1
    names = [n.strip() for n in (args.names or "").split(",") if n.strip()]
    bad = [n for n in names if not re.fullmatch(r"[a-z0-9_]+", n)]
    if bad:
        print(f"ERROR: --names {', '.join(bad)}: lower-case letters, digits and '_' only", file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else sheet_path.parent / "sliced"
    stem = re.sub(r"[^a-z0-9_]+", "_", sheet_path.stem.lower()).strip("_") or "sprite"
    with Image.open(sheet_path) as im:
        sheet = im.convert("RGBA")
    rects = []
    try:
        if args.atlas:
            data = read_json(args.atlas)
            frames = data.get("frames", {})
            items = frames.items() if isinstance(frames, dict) else [(f.get("filename"), f) for f in frames]
            for fname, f in items:
                r = f.get("frame", f)
                base = re.sub(r"[^a-z0-9_]+", "_", Path(str(fname)).stem.lower()).strip("_")
                rects.append((base or None, (int(r["x"]), int(r["y"]), int(r["w"]), int(r["h"]))))
        elif args.cell or args.grid:
            cell = _wh(args.cell, "--cell") if args.cell else None
            grid = _wh(args.grid, "--grid") if args.grid else None
            rects = [(None, r) for r in _cells(sheet.width, sheet.height, cell, grid, args.padding, args.margin)]
        else:
            print("ERROR: say how the sheet is laid out: --cell WxH, --grid COLSxROWS or --atlas <json>",
                  file=sys.stderr)
            return 1
    except (ValueError, KeyError, TypeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=True)
    written, skipped = [], 0
    for atlas_name, (x, y, w, h) in rects:
        crop = sheet.crop((x, y, x + w, y + h))
        if crop.getchannel("A").getextrema()[1] == 0:
            skipped += 1                                  # an empty cell
            continue
        k = len(written)
        name = names[k] if k < len(names) else (atlas_name or f"{stem}_{k:02d}")
        crop.save(out / f"{name}.png")
        written.append(name)
    if names and len(names) != len(written):
        print(f"WARNING: {len(names)} name(s) for {len(written)} sprite(s): check the order and the grid",
              file=sys.stderr)
    print(f"sliced {sheet_path.name}: {len(written)} sprite(s) into {out}"
          + (f" ({skipped} empty cell(s) skipped)" if skipped else "") + "\n" + ", ".join(written))
    return 0 if written else 1


def cmd_review(args) -> int:
    p, _ = load(args)
    rj = p.workspace / "qa" / "report.json"
    report = read_json(rj) if rj.exists() else {}
    pj = p.workspace / "raw" / "prompts.json"
    prompts = read_json(pj) if pj.exists() else {}
    out = art_review.build(p, final_dir(p), p.workspace / "raw", report, prompts, style_dir(p))
    print(f"review page: {out}")
    return 0


def cmd_feedback(args) -> int:
    """Fold the review page's 'Copy feedback' JSON into fixes.json. Every asset
    marked Fix gets its note added once (re-importing the same feedback is a
    no-op); unrelated fields of an existing fix entry are kept."""
    p, fixes = load(args)
    src = Path(args.file) if args.file else None
    if src is None or not src.exists():
        raise SystemExit("feedback needs --file <json pasted from the review page>")
    data = read_json(src)
    if data.get("project") not in (None, p.name):
        raise SystemExit(f"this feedback is for project {data.get('project')!r}, not {p.name!r}")
    fb = data.get("review", {})
    names = {a.name for a in p.assets}
    to_fix, ok, unmarked = [], [], []
    for name, v in fb.items():
        if name not in names:
            print(f"  skip unknown asset {name}", file=sys.stderr)
            continue
        status, note = v.get("status"), (v.get("note") or "").strip()
        if status == "fix":
            to_fix.append(name)
            if note:
                cur = fixes.get(name, "")
                entry = {"text": cur} if isinstance(cur, str) else dict(cur)
                notes = entry.setdefault("notes", [])
                if note not in notes:
                    notes.append(note)
                    entry["text"] = " ".join(x for x in (entry.get("text", ""), note) if x).strip()
                fixes[name] = entry
        elif status == "ok":
            ok.append(name)
        elif note:
            unmarked.append(name)
    p.workspace.mkdir(parents=True, exist_ok=True)
    (p.workspace / "fixes.json").write_text(json.dumps(fixes, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"approved: {', '.join(ok) or '-'}\nto fix: {', '.join(to_fix) or '-'}")
    if unmarked:
        print(f"notes without OK/Fix (ignored, ask the artist): {', '.join(unmarked)}")
    if to_fix:
        print(f"next: {cmd_line(args, 'all', '--only', ','.join(to_fix), '--force')}")
    return 0


def build_sheet(items, cols: int | None = None, padding: int = 2):
    """Lay finished sprites out on one grid: every cell is as large as the largest sprite, each sprite sits
    centred in its cell. `items` is [(name, RGBA image, set or None)] in order. Returns (sheet image, atlas
    dict); the atlas is the common "JSON hash" sprite-sheet format (frames -> {x, y, w, h}), which game
    engines and tools such as Phaser, Godot importers and TexturePacker readers load, plus `animations` (one
    list of frame names per set, in order)."""
    if not items:
        raise ValueError("no sprites to put on the sheet")
    padding = max(0, int(padding))
    n = len(items)
    cols = max(1, min(n, int(cols) if cols else int(np.ceil(np.sqrt(n)))))
    rows = (n + cols - 1) // cols
    cw = max(im.width for _, im, _ in items)
    ch = max(im.height for _, im, _ in items)
    W = cols * cw + (cols + 1) * padding
    H = rows * ch + (rows + 1) * padding
    sheet = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    frames, animations = {}, {}
    for i, (name, im, set_name) in enumerate(items):
        r, c = divmod(i, cols)
        x = padding + c * (cw + padding) + (cw - im.width) // 2
        y = padding + r * (ch + padding) + (ch - im.height) // 2
        sheet.paste(im, (x, y))
        frames[name] = {"frame": {"x": x, "y": y, "w": im.width, "h": im.height}, "rotated": False,
                        "trimmed": False, "spriteSourceSize": {"x": 0, "y": 0, "w": im.width, "h": im.height},
                        "sourceSize": {"w": im.width, "h": im.height}}
        if set_name:
            animations.setdefault(set_name, []).append(name)
    atlas = {"frames": frames, "animations": animations,
             "meta": {"app": "cube_art-director art.py sheet", "version": "1", "image": "", "format": "RGBA8888",
                      "size": {"w": W, "h": H}, "scale": "1", "cell": {"w": cw, "h": ch}, "columns": cols,
                      "rows": rows, "padding": padding}}
    return sheet, atlas


def cmd_sheet(args) -> int:
    """Pack the finished (exact-size) images into one sprite sheet: <workspace>/sheet/<name>.png plus the
    atlas <name>.json that says where each sprite is. Takes the finals `process` wrote; nothing is redrawn."""
    p, _ = load(args)
    chosen = [a for a in pick(p, args.only, args.set) if a.name != "0"]
    src = final_dir(p)
    missing = [a.name for a in chosen if not (src / f"{a.name}.png").exists()]
    if missing:
        print(f"ERROR: no final image for {', '.join(missing)} in {src}: run process (and qa) first",
              file=sys.stderr)
        return 1
    items = []
    for a in chosen:
        with Image.open(src / f"{a.name}.png") as im:
            items.append((a.name, im.convert("RGBA"), a.set))
    try:
        sheet, atlas = build_sheet(items, args.cols, args.padding)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    name = args.name or args.set or "sheet"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        print(f"ERROR: --name {name!r}: letters, digits, '_', '-' and '.' only", file=sys.stderr)
        return 1
    out = p.workspace / "sheet"
    out.mkdir(parents=True, exist_ok=True)
    atlas["meta"]["image"] = f"{name}.png"
    sheet.save(out / f"{name}.png")
    (out / f"{name}.json").write_text(json.dumps(atlas, indent=1), encoding="utf-8")
    m = atlas["meta"]
    print(f"sprite sheet: {out / (name + '.png')} ({m['size']['w']}x{m['size']['h']}, {len(items)} sprite(s), "
          f"{m['columns']}x{m['rows']} cells of {m['cell']['w']}x{m['cell']['h']}, padding {m['padding']})\n"
          f"atlas: {out / (name + '.json')}")
    return 0


def cmd_budget(args) -> int:
    p, _ = load(args)
    led = ledger(p, args)
    if args.video:
        # an animation from a video service (references/ANIMATION_VIDEO.md): one job, recorded BEFORE it is
        # submitted, counting the frames it replaces (the spec's <anim>_NN frames, or --video-frames)
        rx = re.compile(rf"^{re.escape(args.video)}_\d{{2,}}$")
        frames = [a.name for a in p.assets if rx.match(a.name)]
        count = args.video_frames if args.video_frames is not None else len(frames)
        if count < 1:
            print(f"ERROR: no frames named {args.video}_00, {args.video}_01, ... in the spec: give --video-frames N",
                  file=sys.stderr)
            return 1
        extra = {"credits": args.credits} if args.credits is not None else None
        ok, why = led.charge(args.video, "video", 1, count=count, extra=extra)
        if not ok:
            print(f"ERROR: {why}. Nothing was recorded: do not submit the video job. Ask the user before raising "
                  f"the budget.", file=sys.stderr)
            return art_budget.EXIT_OVER_BUDGET
        print(f"video job for {args.video} recorded as {count} image(s)")
    print(led.status() + ("" if led.remaining() is None else f"; {led.remaining()} left"))
    return 0


def cmd_all(args) -> int:
    rc = cmd_gen(args)
    if rc == art_budget.EXIT_OVER_BUDGET:
        return rc                       # nothing was drawn: the budget refusal is the result
    rc |= cmd_process(argparse.Namespace(**{**vars(args), "only": None}))
    rc |= cmd_qa(argparse.Namespace(**{**vars(args), "only": None, "set": None}))
    cmd_review(args)
    return rc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["doctor", "init", "candidates", "style", "anchor", "gen", "process", "qa",
                                    "review", "feedback", "all", "budget", "sheet", "sizes", "slice", "waive"])
    ap.add_argument("spec", nargs="?", default="")
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--only", default=None)
    ap.add_argument("--set", default=None)
    ap.add_argument("--force", action="store_true", help="redraw even if a raw image exists")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--k", type=int, default=24, help="palette size for `style`")
    ap.add_argument("--file", default=None, help="feedback JSON for `feedback`")
    ap.add_argument("--subject", default=None, help="what the style candidates show")
    ap.add_argument("--n", type=int, default=3, help="number of style candidates")
    ap.add_argument("--originals", action="store_true",
                    help="anchor: pick the anchors among the kept original sprites (a modded game's own art)")
    ap.add_argument("--count", type=int, default=3, help="anchor --originals: how many sprites (default 3)")
    ap.add_argument("--trust-post", action="store_true",
                    help="process: approve fixes.json's @post script (this content, this workspace; stored in "
                         "~/.wowcube/trusted_post.json) and run it")
    ap.add_argument("--budget", type=int, default=None,
                    help="gen/candidates: lower the image cap for this run only (default: the profile's or the "
                         "tier's, art_budget.py); above the budget only together with --over-budget")
    ap.add_argument("--over-budget", action="store_true",
                    help="gen/candidates: draw past the image budget (only on the user's yes; marked in the ledger)")
    ap.add_argument("--video", default=None,
                    help="budget: record one animation video job for this animation (frames <video>_NN) before "
                         "it is submitted; it counts as the frames it replaces (references/ANIMATION_VIDEO.md)")
    ap.add_argument("--video-frames", type=int, default=None, help="budget --video: images it counts (default: the "
                                                            "spec's frames of that animation)")
    ap.add_argument("--credits", type=float, default=None, help="budget --video: the service's quoted credits "
                                                                "(noted in the ledger only)")
    ap.add_argument("--cols", type=int, default=None, help="sheet: columns (default: a square-ish grid)")
    ap.add_argument("--padding", type=int, default=2, help="sheet: transparent pixels between cells (default 2)")
    ap.add_argument("--name", default=None, help="sheet: file name without extension (default: the --set, else sheet)")
    ap.add_argument("--cell", default=None, help="slice: the cell size WxH")
    ap.add_argument("--grid", default=None, help="slice: COLSxROWS (the cell size follows from the sheet)")
    ap.add_argument("--atlas", default=None, help="slice: a JSON atlas with each sprite's x, y, w, h")
    ap.add_argument("--names", default=None, help="slice: names for the sprites, in reading order, comma-separated")
    ap.add_argument("--margin", type=int, default=0, help="slice: pixels around the whole grid")
    ap.add_argument("--out", default=None, help="slice: output folder (default: <sheet folder>/sliced)")
    ap.add_argument("--check", default=None, help="waive: check id(s), comma-separated (style, fill, set_centroid, "
                                                  "set_area, set_height, set_colour)")
    ap.add_argument("--reason", default=None, help="waive: one line - what the picture shows (why the number is wrong)")
    ap.add_argument("--drop", action="store_true", help="waive: remove the waiver instead")
    ap.add_argument("--no-codex", action="store_true",
                    help="doctor: the art is drawn in code or is the artist's own: Codex is not needed "
                         "(its lines become notes, not failures)")
    args = ap.parse_args(argv)
    if args.cmd not in ("doctor", "sizes") and not args.spec:
        ap.error("spec is required")
    cmd = {"doctor": cmd_doctor, "init": cmd_init, "candidates": cmd_candidates, "style": cmd_style,
           "anchor": cmd_anchor, "gen": cmd_gen, "process": cmd_process, "qa": cmd_qa, "review": cmd_review,
           "feedback": cmd_feedback, "all": cmd_all, "budget": cmd_budget, "sheet": cmd_sheet,
           "sizes": cmd_sizes, "slice": cmd_slice, "waive": cmd_waive}[args.cmd]
    try:
        return cmd(args)
    except art_budget.BudgetError as e:     # a refused --budget raise (4), a context that does not parse (2)
        print(f"ERROR: {e}", file=sys.stderr)
        return e.exit_code


if __name__ == "__main__":
    sys.exit(main())
