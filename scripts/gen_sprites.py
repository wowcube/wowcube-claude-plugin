"""AI sprite generator for cube_asset-builder.

Two paths, picked by the resolved image provider
(`image_providers.resolve_provider()`):

- **codex** (when the user chose it: Codex CLI on their ChatGPT subscription, no key):
  `generate_codex()` hands the whole manifest to cube_art-director's art.py
  (`gen` + `process`): STYLE.md Prompt block and style anchors on every
  prompt, the sprite's `background` (flat chroma-key backdrop, keyed, or an
  opaque full-canvas picture), shared scale + centroid alignment per
  animation, subject references and colour lock from
  `<workspace>/fixes.json`. Final PNGs land in `<workspace>/art/`.
- **API key** (OpenRouter, OpenAI, xAI, Gemini, local SD; when chosen):
  `generate()` runs one `genimg.generate_image()` call per sprite, removes a
  flat backdrop by flood fill and resizes to the manifest size.

AI output is NOT deterministic across runs.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from PIL import Image

from manifest_schema import Manifest, Sprite, load_manifest
import genimg
import image_providers

# Frame-sequence suffix: mirrors pack_beta._seq_frame_groups' _RE_SEQ_FRAME
# (2 or more digits) so a sprite derives the same group here as it chains
# into at pack time. A single digit ("_5") is not a sequence suffix to the
# packer either, so it is left attached to the base name here too.
_RE_FRAME_SUFFIX = re.compile(r"^(.+)_(\d{2,})$")

# words that make a magenta backdrop unsafe (the subject would be keyed out)
_PINKISH = ("pink", "magenta", "fuchsia", "purple", "violet")


def _derived_group(s: Sprite) -> str:
    """Explicit group wins; otherwise strip a trailing 2+ digit _NN.. suffix."""
    if s.group:
        return s.group
    m = _RE_FRAME_SUFFIX.match(s.name)
    return m.group(1) if m else s.name


def _write_zero_png(out_dir: Path) -> None:
    """The packer expects a 1x1 transparent `0.png` sentinel."""
    out_dir.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(out_dir / "0.png", format="PNG")


def is_cutout(s: Sprite) -> bool:
    """True when the sprite is a cut-out (drawn on a flat backdrop that is
    keyed away), False for an opaque full-canvas picture. The manifest's
    explicit `background` ("key" | "opaque") wins; older manifests: backgrounds
    (`flags.bg`), fullsize art and full-colour art (no transparency) are
    pictures, everything else is a cut-out."""
    if s.background == "key":
        return True
    if s.background == "opaque":
        return False
    return not (s.flags.bg or s.flags.fullsize or s.color == "full")


def manifest_style(manifest_path) -> str | None:
    """The manifest's top-level `_style` string (the per-game style that also
    feeds assets_<game>/style/STYLE.md's Prompt block), or None. An unreadable
    manifest prints a warning (the sprites would be drawn without the style)
    instead of dropping it silently."""
    try:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        print(f"WARNING: cannot read _style from {manifest_path} ({e}): sprites are drawn WITHOUT the "
              f"game's style", file=sys.stderr)
        return None
    if not isinstance(data, dict):
        return None
    style = data.get("_style")
    return style.strip() if isinstance(style, str) and style.strip() else None


def api_prompt(s: Sprite, style: str | None = None) -> str:
    """The prompt sent to a paid-API provider for one sprite.

    On the Codex path art.py adds the style (STYLE.md Prompt block) and the
    backdrop sentence itself; the API path has neither, so the per-game
    `_style` goes in front (unless the gen_prompt already carries it) and a
    cut-out gets the flat chroma-key backdrop its flood-fill keyer relies on
    (green when the subject is pinkish, magenta otherwise)."""
    body = (s.gen_prompt or "").strip()
    parts = [style] if style and style not in body else []
    parts.append(body)
    low = body.lower()
    if is_cutout(s) and "#ff00ff" not in low and "#00ff00" not in low:
        key = "#00FF00 green" if any(w in low for w in _PINKISH) else "#FF00FF magenta"
        parts.append(f"Square canvas, one subject centred with a clear margin, on a flat uniform {key} "
                     "background (no gradient, no floor, no shadow); the subject never uses that colour.")
    return "\n\n".join(parts)


def image_ledger(game: str, workspace: Path, *, over_budget: bool = False):
    """cube_art-director's image budget ledger (art_budget.py) for this game's workspace, so the paid path
    is counted against the same budget as Codex; None when art.py is not around."""
    import importlib.util
    try:
        mod_path = image_providers.find_art_py().parent / "art_budget.py"
    except image_providers.ImageGenError:
        return None
    if not mod_path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("art_budget", mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    workspace = Path(workspace).resolve()
    return mod.for_workspace(workspace.parent, game, workspace, cube=True, override=over_budget)


def generate(manifest: Manifest, out_dir: Path, *, group: str | None = None,
             style: str | None = None, force: bool = False, provider=None,
             over_budget: bool = False) -> list[Path]:
    """Paid-API path: one AI PNG per sprite in `manifest` to `out_dir`.

    Every sprite must carry a non-empty `gen_prompt`. If `group` is given,
    only sprites whose derived/explicit group matches are drawn. A sprite
    whose PNG already exists is kept (every call is billed) unless `force`.
    `style` is the manifest `_style` string (see api_prompt). `provider` is a
    resolved ProviderConfig (default: genimg resolves one per call). `0.png`
    is always (re)written.

    A failed sprite does not stop the run: the others are still drawn, then
    ImageGenError names every failure (a rerun draws only what is missing).
    Raises ValueError, before anything is drawn, if a selected sprite has no
    `gen_prompt`. Returns the PNGs of the selected sprites (drawn or kept).
    Every HTTP attempt (a retry included) is one entry of the image budget ledger
    (art_budget.py), charged by the provider's retry loop before the request; a run
    that does not fit in what is left raises ImageGenError before anything is drawn,
    a run with nothing left to draw always passes (`over_budget` = the user's
    explicit yes to go past it).
    """
    out_dir = Path(out_dir)
    selected = [s for s in manifest.sprites if group is None or _derived_group(s) == group]
    for s in selected:
        if not (s.gen_prompt and s.gen_prompt.strip()):
            raise ValueError(
                f"sprite {s.name!r} has no gen_prompt — required for AI "
                f"generation. Add it to the manifest (technical_prompter "
                f"Step 4a) or regenerate the manifest."
            )
    _write_zero_png(out_dir)
    led = image_ledger(manifest.game, out_dir.parent, over_budget=over_budget)
    need = sum(1 for s in selected if force or not (out_dir / f"{s.name}.png").is_file())
    if led is not None and not led.can_afford(need):
        raise image_providers.ImageGenError(led.refusal(need))

    written: list[Path] = []
    kept: list[str] = []
    failed: list[str] = []
    for s in selected:
        target = out_dir / f"{s.name}.png"
        if target.is_file() and not force:
            kept.append(s.name)
            written.append(target)
            continue
        try:
            kw = {'provider': provider} if provider is not None else {}
            if led is not None:
                # one ledger entry per HTTP attempt, retries included (the provider's retry loop asks first)
                kw['gate'] = (lambda attempt, _n=s.name: led.charge(_n, "provider", attempt))
            genimg.generate_image(api_prompt(s, style), target, size=s.size, cutout=is_cutout(s), **kw)
        except image_providers.ImageGenError as e:
            failed.append(f"{s.name}: {e}")
            print(f"  ERR {s.name}: {e}", file=sys.stderr, flush=True)
            continue
        print(f"  ok  {s.name}", flush=True)
        written.append(target)
    if kept:
        print(f"  kept {len(kept)} existing PNG(s) (--force redraws them): {', '.join(kept)}")
    if led is not None:
        print(f"  {led.status()}")
    if failed:
        raise image_providers.ImageGenError(
            f"{len(failed)} of {len(selected)} sprite(s) failed (the others were drawn; a rerun draws only "
            f"the missing ones):\n  " + "\n  ".join(failed))
    return written


def seed_fixes(manifest: Manifest, workspace: Path) -> list[str]:
    """Give every later animation frame a subject reference to the first frame
    of its animation in <workspace>/fixes.json (created when missing), so all
    frames keep one design (each frame is otherwise drawn from scratch and
    drifts). Merges, never overwrites: an entry's text is kept, and an entry
    that already names a "ref" — `null` meaning "deliberately none" — is left
    alone, so rerunning is a no-op. Skipped while only a legacy
    prompt_overrides.json exists (art.py reads it only as long as fixes.json
    is absent). Colour lock (`@colour_lock`, `@colour_exempt`), refs for state
    variants (hurt, attack, shoot) and "no characters" lines for effects stay
    the reviewer's decisions. Returns the sprite names that got a ref."""
    ws = Path(workspace)
    path = ws / "fixes.json"
    if not path.exists() and (ws / "prompt_overrides.json").exists():
        return []
    try:
        fixes = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    except ValueError as e:
        raise ValueError(f"{path} is not valid JSON: {e}") from e
    first: dict[str, tuple[int, str]] = {}
    for s in manifest.sprites:
        if s.anim is not None and (s.anim not in first or s.frame < first[s.anim][0]):
            first[s.anim] = (s.frame, s.name)
    added: list[str] = []
    for s in manifest.sprites:
        if s.anim is None or first[s.anim][1] == s.name:
            continue
        cur = fixes.get(s.name)
        if isinstance(cur, dict) and "ref" in cur:
            continue
        entry = dict(cur) if isinstance(cur, dict) else {"text": cur if isinstance(cur, str) else ""}
        entry.setdefault("text", "")
        entry["ref"] = first[s.anim][1]
        fixes[s.name] = entry
        added.append(s.name)
    if added:
        ws.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(fixes, indent=1, ensure_ascii=False), encoding="utf-8")
    return added


def generate_codex(manifest_path, workspace, *, manifest: Manifest | None = None,
                   group: str | None = None, force: bool = False,
                   jobs: int | None = None, over_budget: bool = False) -> list[Path]:
    """Codex path: draw the manifest through cube_art-director's art.py.

    `group` limits the run to the sprites of one derived group (art.py
    `--only`); `force` redraws sprites that already have a raw image;
    `jobs` = parallel Codex runs. Returns the final PNGs in
    <workspace>/art/ for the selected sprites. Raises
    image_providers.ImageGenError when a step failed."""
    manifest = manifest or load_manifest(manifest_path)
    workspace = Path(workspace)
    only = None
    if group is not None:
        only = [s.name for s in manifest.sprites if _derived_group(s) == group]
        if not only:
            return []
    seeded = seed_fixes(manifest, workspace)
    if seeded:
        print(f"  {workspace / 'fixes.json'}: {len(seeded)} later animation frame(s) now reference "
              f"their first frame ({', '.join(seeded)})")
    image_providers.codex_generate(manifest_path, workspace, only=only, force=force, jobs=jobs,
                                   **({"over_budget": True} if over_budget else {}))
    art = workspace / "art"
    names = only or [s.name for s in manifest.sprites]
    return [art / f"{n}.png" for n in names if (art / f"{n}.png").is_file()]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate AI sprite PNGs from an asset manifest.")
    p.add_argument("manifest", help="Path to plans/<game>_assets.json")
    p.add_argument("--out", default=None,
                   help="Art dir = <workspace>/art (default: assets_<game>/art next to plans/)")
    p.add_argument("--group", default=None, help="Regenerate only this group")
    p.add_argument("--force", action="store_true",
                   help="Redraw sprites that already have an image (Codex: a raw image; paid API: the PNG)")
    p.add_argument("--jobs", type=int, default=3, help="Codex: parallel runs (default 3)")
    p.add_argument("--allow-paid", action="store_true",
                   help="Opt in to the PAID image API the user chose (same as "
                        "WOWCUBE_ALLOW_PAID_IMAGES=1); only after the user agreed to pay per image")
    args = p.parse_args(argv)
    if args.allow_paid:
        import os
        os.environ[image_providers.ALLOW_PAID_ENV] = "1"      # this process only

    try:
        m = load_manifest(args.manifest)
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"ERROR: manifest unreadable: {args.manifest}: {e}", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else default_workspace(args.manifest, m.game) / "art"
    try:
        config = image_providers.resolve_provider(manifest=args.manifest)
        if config is not None and config.provider == image_providers.CODEX_PROVIDER:
            if out.name != "art":
                print("ERROR: with the codex provider --out must be <workspace>/art (art.py writes there)",
                      file=sys.stderr)
                return 2
            written = generate_codex(args.manifest, out.parent, manifest=m, group=args.group,
                                     force=args.force, jobs=args.jobs)
        else:
            written = generate(m, out, group=args.group, style=manifest_style(args.manifest), force=args.force,
                               provider=config)
    except (image_providers.ImageGenError, ValueError) as e:
        print(f"ERROR: sprite generation failed: {e}", file=sys.stderr)
        return 1
    print(f"gen_sprites: wrote {len(written)} PNG(s) to {out}")
    return 0


def default_workspace(manifest_path, game: str) -> Path:
    """assets_<game>/ at the project root (the folder that holds plans/) -
    the same folder cube_art-director's art.py uses for a WowCube manifest."""
    p = Path(manifest_path).resolve()
    root = p.parent.parent if p.parent.name == "plans" else p.parent
    return root / f"assets_{game}"


if __name__ == "__main__":
    sys.exit(main())
