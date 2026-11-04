"""Pipeline driver for cube_asset-builder.

Subcommands:
  validate    — provider-free manifest check (schema, names, tiers,
                `background`, `launcher_icon`, the Codex prompt rules a regex
                can check, `_panoramas`). Exit 0 ok, 2 errors. Never
                generates, never starts a provider, never touches the
                network: gates and smoke checks use THIS, not `generate`.
  generate    — validate manifest, generate the sprite PNGs and placeholder
                sounds into the per-game workspace (default assets_<game>/
                next to plans/). Sprites: with the default provider (a Codex
                CLI logged in with ChatGPT) the whole manifest is delegated to
                cube_art-director's art.py (`gen` + `process`: style lock,
                chroma-key backdrop, shared scale per set, colour lock); with
                a paid API key, one genimg call per sprite. Sounds:
                synthesised placeholders for every sound that has no sourced
                mp3 yet.
  pack        — build assets.psd then run pack.py to produce packed/ and
                _ids.h. With --manifest it first refuses an incomplete set
                (every sprite needs <ws>/art/<name>.png, with --app-dir every
                sound an mp3 in <ws>/wav/assets or <app>/sound/assets) before
                writing anything; it always clears the intermediate
                <ws>/packed and <ws>/exported first, syncs changed app fonts
                into <ws>/fonts and, with --app-dir, records the sha1 of every
                input in <app>/.pack_inputs.json.
  pack-status — exit 0 when <app>/.pack_inputs.json matches the current
                inputs (and every pack output - index.bin, the ids header,
                art/packed/*, sound/assets/*.mp3 - is still the one it
                wrote), 1 when stale or missing; prints what changed. An app
                with art/octpack.json (PSD-authored, packed by the SDK's
                octpacker) is judged by its own backend instead: fresh when
                <app>/index.bin is newer than octpack.json, !pack.txt and
                every input file or folder octpack.json names.

Designed to work identically in the dev repo layout and inside a packaged
copy of the skills (where build_psd.py/pack.py are copied next to this
file). `find_script()` checks the scripts dir then walks up the ancestors.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from manifest_schema import ValidationError, check_manifest_file, load_manifest, validate
import gen_sprites
import gen_sounds
import image_providers

SCRIPT_DIR = Path(__file__).resolve().parent


def find_script(name: str) -> Path:
    """Return absolute path to `name` in the package scripts/ dir or an ancestor.

    Package mode: scripts/<name> lives next to this file.
    Dev mode: <name> lives at the repo root somewhere above this file. The repo
    may be nested at any depth, so we walk every ancestor and return the first
    `<ancestor>/<name>` that exists.
    """
    local = SCRIPT_DIR / name
    if local.exists():
        return local
    for ancestor in SCRIPT_DIR.parents:
        for candidate in (ancestor / name, ancestor / "scripts" / name):
            if candidate.exists():
                return candidate
    raise FileNotFoundError(
        f"{name} not found near {SCRIPT_DIR} (checked {local}) "
        f"or in any ancestor directory (or its scripts/ subdir)"
    )


GENERATE_PY_DEPS = ("PIL", "numpy", "requests")
PACK_PY_DEPS = ("PIL", "numpy", "pytoshop", "psd_tools")


def _resolve_image_provider(manifest=None):
    """(ProviderConfig, None) or (None, error message) for the generate stage.
    The provider the user chose (WOWCUBE_IMAGE_PROVIDER, wowcube.project.json
    near the manifest, ~/.wowcube/config.json, or the pipeline's own IMAGE_API /
    ~/.wowcube/image_api.json); nothing chosen -> drawn in code (the
    procedural style). A paid key only with the opt-in
    (WOWCUBE_ALLOW_PAID_IMAGES=1 or `generate --allow-paid`)."""
    try:
        provider = image_providers.resolve_provider(manifest=manifest)
    except (image_providers.PaidProviderNotAllowed, image_providers.DataPolicyBlocked) as e:
        return None, str(e)
    except image_providers.ImageGenError as e:
        return None, f"image provider config is invalid: {e}"
    if provider is None:
        return None, f"image provider - {image_providers.NO_CHOICE_HINT}"
    return provider, None


def _check_deps(stage: str, manifest=None) -> list[str]:
    """Return list of missing dependency messages. Empty = everything installed.

    `stage` is 'generate' or 'pack'. Generate needs PIL+numpy+requests and an
    image provider the user chose (image_providers.resolve_provider: a profile
    choice, or IMAGE_API env / ~/.wowcube/image_api.json; nothing else);
    pack needs PIL+numpy+pytoshop+psd_tools.
    """
    required = PACK_PY_DEPS if stage == "pack" else GENERATE_PY_DEPS
    missing: list[str] = []
    for mod in required:
        try:
            __import__(mod)
        except ImportError:
            pip_name = {"PIL": "Pillow", "psd_tools": "psd-tools"}.get(mod, mod)
            missing.append(f"python module {mod!r} - install with: pip install {pip_name}")
    if stage == "generate":
        _, err = _resolve_image_provider(manifest)
        if err:
            missing.append(err)
    return missing


def _run(cmd: list[str], *, cwd: Path | None = None) -> int:
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    proc = subprocess.run(cmd, cwd=cwd, text=True)
    return proc.returncode


def _drawn(workspace: Path | None, name: str) -> bool:
    """Has this sprite been drawn already (a PNG in the workspace's raw/ or art/)?"""
    return workspace is not None and any((workspace / d / f"{name}.png").is_file() for d in ("raw", "art"))


def image_cost(manifest_path: Path, manifest, workspace: Path | None = None) -> tuple[int, int]:
    """(images the draw of this manifest still requests, sprites already drawn). One image per sprite
    with no PNG in `<workspace>/raw/` or `art/` yet (what `art.py gen` / `generate` would draw), except
    panorama pieces: one picture per `_panoramas` entry that still has an undrawn piece. Without a
    workspace every sprite counts (the first full draw)."""
    try:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        data = {}
    panos = data.get("_panoramas") if isinstance(data.get("_panoramas"), dict) else {}
    panos = {k: v for k, v in panos.items() if isinstance(v, dict)}
    pieces = {p for v in panos.values() for p in (v.get("pieces") or [])}
    drawn = sum(1 for s in manifest.sprites if _drawn(workspace, s.name))
    # a `keep` sprite (the game's own art carried through, Mod mode) is never drawn
    cost = sum(1 for s in manifest.sprites
               if s.name not in pieces and not getattr(s, "keep", False) and not _drawn(workspace, s.name))
    cost += sum(1 for v in panos.values()
                if not v.get("pieces") or not all(_drawn(workspace, p) for p in v.get("pieces")))
    return cost, drawn


def budget_findings(manifest_path: Path, manifest) -> tuple[list[str], list[str], str]:
    """(errors, warnings, info line) for the images the manifest still needs drawn against the image
    budget (cube_art-director art_budget.py: context, profile or tier). Sprites that already have a PNG
    in assets_<game>/raw/ or art/ cost nothing, so a Mod-mode edit of a drawn game only counts its new
    sprites (and any whose PNG was removed for a redraw). The draw may use at most FIRST_DRAW_SHARE of
    the budget (style frames, retries and the QA loop's redraws need the rest) and never more than what
    is left.
    Art that costs no images (art.source own / procedural / placeholder, or original without
    art.new codex) is not checked."""
    path = Path(manifest_path).resolve()
    root = path.parent.parent if path.parent.name == "plans" else path.parent
    project = {}
    try:
        project = json.loads((root / "wowcube.project.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        pass
    source = ((project.get("art") or {}) if isinstance(project, dict) else {}).get("source")
    art_new = ((project.get("art") or {}) if isinstance(project, dict) else {}).get("new")
    if source in ("own", "procedural", "placeholder") or (source == "original" and art_new != "codex"):
        return [], [], f"image budget: not used (art.source: {source})"
    workspace = root / f"assets_{manifest.game}"
    try:
        led = gen_sprites.image_ledger(manifest.game, workspace)
    except ValueError as e:                 # art_budget.UnreadableFile: a context that does not parse
        return [f"image budget: {e}"], [], "image budget: unreadable"
    if led is None or led.budget is None:
        return [], [], "image budget: unknown (cube_art-director art_budget.py not found)"
    (cost, drawn), budget = image_cost(path, manifest, workspace), led.budget
    left = max(0, budget - led.spent)
    what = "the first draw" if not drawn else f"the draw still needed ({drawn} sprite(s) already drawn)"
    info = f"image budget: {what} needs {cost} image(s) of {budget} [{led.source}]; {led.spent} already spent"
    share = int(budget * FIRST_DRAW_SHARE)
    if cost > budget:
        return [f"image budget: {what} alone needs {cost} images, more than the whole budget of {budget} "
                f"[{led.source}]: cut sprites (fewer frames, shared pictures, panoramas instead of per-screen "
                f"art) or raise budget.images with the user (technical_prompter, 'Image budget')"], [], info
    if cost > left:
        return [f"image budget: {what} needs {cost} images but only {left} of {budget} are left ({led.spent} "
                f"spent) [{led.source}]: cut sprites or ask the user to raise budget.images "
                f"(technical_prompter, 'Image budget')"], [], info
    if cost > share:
        return [], [f"image budget: {what} needs {cost} of {budget} images; keep it at or below {share} "
                     f"({int(FIRST_DRAW_SHARE * 100)}%) so style frames, retries and QA redraws fit "
                     f"(technical_prompter, 'Image budget')"], info
    return [], [], info


FIRST_DRAW_SHARE = 0.6


def do_validate(args: argparse.Namespace) -> int:
    """Provider-free manifest gate: reads the JSON file (and the local profile files for the image budget)
    and nothing else."""
    path = Path(args.manifest)
    errors, warnings, manifest = check_manifest_file(path)
    info = ""
    if manifest is not None and not getattr(args, "no_budget", False):
        e, w, info = budget_findings(path, manifest)
        errors, warnings = errors + e, warnings + w
    print(f"validate: {path}")
    for e in errors:
        print(f"  ERROR: {e}")
    for w in warnings:
        print(f"  WARNING: {w}")
    counts = (f"{len(manifest.sprites)} sprite(s), {len(manifest.sounds)} sound(s)"
              if manifest is not None else "not parsed")
    if info:
        print(f"  {info}")
    if errors:
        print(f"INVALID: {len(errors)} error(s), {len(warnings)} warning(s) ({counts}) - fix the manifest "
              f"(Stage 2) before generating or packing")
        return 2
    print(f"OK: manifest valid ({counts}{f', {len(warnings)} warning(s)' if warnings else ''})")
    return 0


def do_generate(args: argparse.Namespace) -> int:
    """`--allow-paid` is the opt-in for a paid image API, for this run only
    (it sets WOWCUBE_ALLOW_PAID_IMAGES while generating, then restores it)."""
    if getattr(args, "allow_paid", False) and not image_providers.paid_allowed():
        os.environ[image_providers.ALLOW_PAID_ENV] = "1"
        try:
            return _do_generate(args)
        finally:
            os.environ.pop(image_providers.ALLOW_PAID_ENV, None)
    return _do_generate(args)


def _do_generate(args: argparse.Namespace) -> int:
    deps = _check_deps("generate", args.manifest)
    if deps:
        print("ERROR: missing dependencies:", file=sys.stderr)
        for d in deps:
            print(f"  - {d}", file=sys.stderr)
        return 3

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"ERROR: manifest not found: {manifest_path}", file=sys.stderr)
        return 2

    try:
        manifest = load_manifest(manifest_path)
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"ERROR: manifest unreadable: {manifest_path}: {e}", file=sys.stderr)
        return 2
    errors = validate(manifest)
    if errors:
        print(f"ERROR: manifest validation failed ({len(errors)} issue(s)):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 2

    provider, err = _resolve_image_provider(manifest_path)
    if provider is None:          # resolved a moment ago in _check_deps; be safe anyway
        print(f"ERROR: {err}", file=sys.stderr)
        return 3

    workspace = (Path(args.workspace) if args.workspace
                 else gen_sprites.default_workspace(manifest_path, manifest.game))
    art_dir = workspace / "art"
    wav_dir = workspace / "wav"
    codex = provider.provider == image_providers.CODEX_PROVIDER

    try:
        if codex:
            print(f"Generating sprites with Codex (cube_art-director art.py) -> {art_dir}")
            png_paths = gen_sprites.generate_codex(manifest_path, workspace, manifest=manifest,
                                                   group=args.group, force=args.force, jobs=args.jobs,
                                                   over_budget=getattr(args, "over_budget", False))
        elif image_providers.is_free_local(provider):
            kind = "Stable Diffusion" if provider.provider == "sd_a1111" else "OpenAI-compatible server"
            print(f"Generating AI sprites with the local {kind} at {provider.base_url} "
                  f"(this machine, no paid opt-in needed) -> {art_dir}")
            png_paths = gen_sprites.generate(manifest, art_dir, group=args.group, force=args.force,
                                             style=gen_sprites.manifest_style(manifest_path),
                                             provider=provider, over_budget=getattr(args, "over_budget", False))
        else:
            print(f"Generating AI sprites with the PAID {provider.provider} API (opted in: "
                  f"{image_providers.ALLOW_PAID_ENV}=1 / --allow-paid) -> {art_dir}")
            png_paths = gen_sprites.generate(manifest, art_dir, group=args.group, force=args.force,
                                             style=gen_sprites.manifest_style(manifest_path),
                                             provider=provider, over_budget=getattr(args, "over_budget", False))
    except (image_providers.ImageGenError, ValueError) as e:
        print(f"ERROR: sprite generation failed: {e}", file=sys.stderr)
        return 6

    # beta mp3s (22050 Hz mono CBR 32k) are what the beta simulator actually
    # loads; encode them whenever ffmpeg is around, or unconditionally when
    # --mp3 forces it (then a missing ffmpeg is a hard error, not a skip)
    want_mp3 = args.mp3 or shutil.which("ffmpeg") is not None
    mp3_note = f" (+ mp3 -> {wav_dir / 'assets'})" if want_mp3 else ""
    print(f"Placeholder sounds    -> {wav_dir}{mp3_note}")
    kept: list[str] = []
    unverified: list[str] = []
    try:
        wav_paths = gen_sounds.generate(manifest, wav_dir, group=args.group,
                                        encode_mp3=want_mp3, kept=kept, unverified=unverified)
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as e:
        # RuntimeError = ffmpeg missing; CalledProcessError = ffmpeg present
        # but the mp3 encode itself failed; ValueError = two manifest sound
        # names collide once normalised to SND_ ids. Same exit either way.
        print(f"ERROR: sound encoding failed: {e}", file=sys.stderr)
        return 7

    groups: set[str] = set()
    for s in manifest.sprites:
        groups.add(s.group or gen_sprites._derived_group(s))
    for snd in manifest.sounds:
        groups.add(snd.group or snd.name)

    print("=" * 60)
    print(f"  {len(png_paths)} PNG(s) ({'codex via art.py' if codex else provider.provider}), "
          f"{len(wav_paths)} placeholder WAV(s), {len(kept)} sourced sound(s) kept")
    if unverified:
        print("  " + gen_sounds.unverified_warning(wav_dir, unverified))
    print(f"  workspace: {workspace}")
    print(f"  groups: {sorted(groups)}")
    if codex:
        print(f"  next: strict QA loop -> python skills/cube_art-director/scripts/art.py qa "
              f"{manifest_path} --workspace {workspace}")
    print("=" * 60)
    return 0


REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_ICON = REPO_ROOT / "templates" / "app_ai_template" / "art" / "icon.png"


def _warn_icon_shape(icon: Path) -> None:
    """A WARNING when the launcher icon is not in the launcher's standard hexagon (scripts/icon_badge.py)."""
    if not icon.is_file():
        return
    try:
        from PIL import Image
        import icon_badge
        problems = icon_badge.check(Image.open(icon))
    except Exception:          # a check that cannot run never blocks a pack
        return
    for p in problems:
        print(f"WARNING: launcher icon {icon}: {p}", file=sys.stderr)


def _sync_fonts(app_dir: Path, workspace: Path) -> tuple[int, int, list[str]]:
    """BMFont glyphs are packed only when font_*.fnt + their atlas PNGs sit in
    <workspace>/fonts. A scaffolded app keeps them in app_<game>/art, so
    mirror them over; without them every OCT_label_set silently draws
    nothing. A font that changed in the app (new .fnt, re-exported atlas) is
    copied again, and atlas pages the app no longer has
    (<stem>_<page>.png) are removed, so a stale page can never be packed.

    Returns (files copied, stale pages removed, workspace-only fonts). Fonts
    that exist only in <workspace>/fonts are left alone (reported)."""
    fonts = sorted((app_dir / "art").glob("font_*.fnt"))
    if not fonts:
        return 0, 0, []
    dst = workspace / "fonts"
    dst.mkdir(parents=True, exist_ok=True)
    copied = removed = 0
    for f in fonts:
        pages = sorted(f.parent.glob(f"{f.stem}_*.png"))
        for src in [f, *pages]:
            target = dst / src.name
            if not target.is_file() or target.read_bytes() != src.read_bytes():
                shutil.copy2(src, target)
                copied += 1
        keep = {p.name for p in pages}
        page_re = re.compile(rf"^{re.escape(f.stem)}_\d+\.png$")
        for old in sorted(dst.glob(f"{f.stem}_*.png")):
            if old.name not in keep and page_re.match(old.name):
                old.unlink()
                removed += 1
    app_stems = {f.stem for f in fonts}
    extra = sorted(p.name for p in dst.glob("*.fnt") if p.stem not in app_stems)
    return copied, removed, extra


def _copy_fonts(app_dir: Path, workspace: Path) -> int:
    """Kept for callers of the old name: syncs and returns the files copied."""
    return _sync_fonts(app_dir, workspace)[0]


def _clear_intermediate(d: Path) -> int:
    """Empty one intermediate build folder (<ws>/packed or <ws>/exported):
    pack.py emits EVERY PNG left in the packed-output folder, so a retired
    frame from an earlier run would otherwise come back indexed and chained.
    Returns the number of entries removed."""
    if not d.is_dir():
        return 0
    n = 0
    for p in sorted(d.iterdir()):
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p)
        else:
            p.unlink()
        n += 1
    return n


PACK_INPUTS_FILE = ".pack_inputs.json"


def _rel_to_app(path: Path | None, app_dir: Path) -> str | None:
    """A path for the pack record, relative to the app folder (posix), so the record says nothing about the
    machine it was packed on and still resolves after the workspace is copied or handed to someone else. Only a
    path on another drive (no relative form) stays absolute."""
    if path is None:
        return None
    try:
        return Path(os.path.relpath(Path(path).resolve(), Path(app_dir).resolve())).as_posix()
    except ValueError:
        return Path(path).resolve().as_posix()


def _recorded_path(value, app_dir: Path) -> Path | None:
    """A path read back from a pack record: relative ones resolve against the app folder; an absolute one that
    does not exist here (written on another machine by an older pack) is ignored."""
    if not value:
        return None
    p = Path(value)
    if not p.is_absolute():
        return Path(app_dir) / p
    return p if p.exists() else None
# 2: "outputs" lists every pack output file (art/packed/*, sound/assets/*.mp3), not only index.bin + ids header
PACK_INPUTS_VERSION = 2


def _sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def _auto_icon(workspace: Path, app_dir: Path) -> Path | None:
    """The icon pack.py picks when no --icon is given (same order)."""
    for cand in (workspace / "icon.png", app_dir / "icon.png", app_dir / "art" / "icon.png"):
        if cand.is_file():
            return cand
    return None


def pack_inputs(workspace: Path, app_dir: Path, manifest: Path | None, icon: Path | None) -> dict[str, str]:
    """sha1 of every file a pack reads: the manifest, every PNG in <ws>/art
    (and <ws>/overrides), the sounds (<ws>/wav/assets and <app>/sound/assets),
    the fonts (<app>/art/font_* and the <ws>/fonts mirror) and the launcher
    icon. Keys are stable labels (ws/..., app/...), so a moved workspace
    still compares."""
    files: dict[str, str] = {}
    if manifest is not None and Path(manifest).is_file():
        files["manifest"] = _sha1(Path(manifest))
    groups = (
        ("ws/art", workspace / "art", ("*.png",)),
        ("ws/overrides", workspace / "overrides", ("*.png",)),
        ("ws/wav/assets", workspace / "wav" / "assets", ("*.mp3",)),
        ("ws/fonts", workspace / "fonts", ("*.fnt", "*.png")),
        ("app/sound/assets", app_dir / "sound" / "assets", ("*.mp3",)),
        ("app/art", app_dir / "art", ("font_*.fnt", "font_*.png")),
    )
    for label, folder, patterns in groups:
        if not folder.is_dir():
            continue
        for pattern in patterns:
            for p in sorted(folder.glob(pattern)):
                if p.is_file():
                    files[f"{label}/{p.name}"] = _sha1(p)
    if icon is not None and Path(icon).is_file():
        files["icon"] = _sha1(Path(icon))
    return files


def pack_outputs(app_dir: Path, game: str) -> dict[str, str]:
    """sha1 of the outputs the pack-status record vouches for: index.bin, the
    ids header and every file of the beta container the simulator and the
    .oct read (art/packed/* and sound/assets/*.mp3), so a deleted or touched
    .raw/.pal/.mp3 makes the pack stale too."""
    out: dict[str, str] = {}
    for rel in ("index.bin", f"src/app_{game}_ids.h"):
        p = app_dir / rel
        if p.is_file():
            out[rel] = _sha1(p)
    for rel, pattern in (("art/packed", "*"), ("sound/assets", "*.mp3")):
        folder = app_dir / rel
        if folder.is_dir():
            for p in sorted(folder.glob(pattern)):
                if p.is_file():
                    out[f"{rel}/{p.name}"] = _sha1(p)
    return out


def _compare(label: str, recorded: dict, current: dict) -> list[str]:
    lines = []
    for k in sorted(set(recorded) | set(current)):
        if k not in current:
            lines.append(f"  removed{label}: {k}")
        elif k not in recorded:
            lines.append(f"  added{label}:   {k}")
        elif recorded[k] != current[k]:
            lines.append(f"  changed{label}: {k}")
    return lines


def _octpack_inputs(app_dir: Path) -> list[Path]:
    """octpack.json, !pack.txt and every existing file a string in
    octpack.json names (relative to art/, else to the app; a folder counts
    with every file in it)."""
    art = app_dir / "art"
    cfg = art / "octpack.json"
    found: list[Path] = [cfg]
    if (art / "!pack.txt").is_file():
        found.append(art / "!pack.txt")
    try:
        data = json.loads(cfg.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return found

    def strings(v):
        if isinstance(v, str):
            yield v
        elif isinstance(v, dict):
            for x in v.values():
                yield from strings(x)
        elif isinstance(v, list):
            for x in v:
                yield from strings(x)

    for rel in strings(data):
        for base in (art, app_dir):
            p = base / rel
            if p.is_file():
                found.append(p)
                break
            if p.is_dir():
                found += [f for f in sorted(p.rglob("*")) if f.is_file()]
                break
    return found


def octpack_status(app_dir: Path) -> tuple[bool, list[str]]:
    """(fresh, report lines) for an app packed by the SDK's octpacker
    (art/octpack.json): index.bin newer than every input."""
    index = Path(app_dir) / "index.bin"
    if not index.is_file():
        return False, [f"no {index}: never packed (octpack-pack / repack_app.py)"]
    built = index.stat().st_mtime
    newer = [p for p in _octpack_inputs(Path(app_dir)) if p.stat().st_mtime > built]
    return not newer, [f"  newer than index.bin: {p.relative_to(app_dir).as_posix()}" for p in newer]


def pack_status(game: str, workspace: Path, app_dir: Path, manifest: Path | None,
                icon: Path | None = None) -> tuple[bool, list[str]]:
    """(fresh, report lines) for <app>/.pack_inputs.json against the current
    inputs; an octpacker app (art/octpack.json) goes to octpack_status()."""
    if (Path(app_dir) / "art" / "octpack.json").is_file():
        return octpack_status(Path(app_dir))
    rec_path = Path(app_dir) / PACK_INPUTS_FILE
    if not rec_path.is_file():
        return False, [f"no {rec_path}: never packed by `build_pipeline.py pack --app-dir`, or the last pack "
                       f"failed"]
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        recorded_in, recorded_out = dict(rec["inputs"]), dict(rec.get("outputs", {}))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return False, [f"{rec_path} unreadable ({exc})"]
    if not isinstance(rec.get("version"), int) or rec["version"] < 2:
        # an older record only vouched for index.bin + the ids header: a lost .raw/.pal/.mp3 went unnoticed
        return False, [f"{rec_path}: record predates output tracking - pack again to record every output"]
    if manifest is not None and not Path(manifest).is_file():
        return False, [f"manifest not found: {manifest}"]
    if icon is None and rec.get("icon_arg"):
        # the explicit --icon of the recorded pack (a foreign absolute path from another machine is ignored)
        icon = _recorded_path(rec["icon_arg"], Path(app_dir))
    if icon is None:
        icon = _auto_icon(Path(workspace), Path(app_dir))
    current_in = pack_inputs(Path(workspace), Path(app_dir), manifest, icon)
    lines = _compare("", recorded_in, current_in)
    lines += _compare(" output", recorded_out, pack_outputs(Path(app_dir), game))
    if rec.get("game") not in (None, game):
        lines.append(f"  game: recorded {rec.get('game')!r}, asked {game!r}")
    return not lines, lines


def _center_pivots(manifest, app_dir: Path, skip: set[str] = frozenset()) -> int:
    """Write utils.exe-style on-screen pivots into every manifest sprite's
    packed header (offset 4: PivotX/PivotY floats; offset 36: w, h). A regular
    sprite is drawn x2, so its authored pivot p maps to 2p - 0.5 on screen; a
    fullsize sprite (1:1) to p - 0.5. The PNG/PSD route otherwise leaves some
    animation frames and full-color sprites off centre. `skip`: carried-through
    records (scripts/carry_art.py) keep their original pivot exactly."""
    import struct
    fixed = 0
    for s in manifest.sprites:
        if s.name in skip:
            continue
        raw = app_dir / "art" / "packed" / f"{s.name}.raw"
        if not raw.is_file():
            continue
        b = bytearray(raw.read_bytes())
        w, h = struct.unpack_from("<hh", b, 36)
        k = 1.0 if s.flags.fullsize else 2.0
        aw, ah = s.size
        if tuple(s.pivot) == (aw // 2, ah // 2):       # default = centred, exact for odd sizes too
            px, py = ((w - 1) / 2.0, (h - 1) / 2.0) if s.flags.fullsize else (w - 0.5, h - 0.5)
        else:
            px, py = s.pivot[0] * k - 0.5, s.pivot[1] * k - 0.5
        if struct.unpack_from("<ff", b, 4) != (px, py):
            struct.pack_into("<ff", b, 4, px, py)
            raw.write_bytes(bytes(b))
            fixed += 1
    return fixed


def do_pack(args: argparse.Namespace) -> int:
    deps = _check_deps("pack")
    if deps:
        print("ERROR: missing dependencies:", file=sys.stderr)
        for d in deps:
            print(f"  - {d}", file=sys.stderr)
        return 3

    workspace = Path(args.workspace)
    src_dir = Path(args.src_dir)

    art_dir = workspace / "art"
    psd_path = workspace / "assets.psd"
    exported_dir = workspace / "exported"
    packed_dir = workspace / "packed"
    ids_path = workspace / f"app_{args.game}_ids.h"
    app_dir = Path(args.app_dir) if args.app_dir else None

    # ── refuse an incomplete set BEFORE anything is written ─────────────────
    manifest = None
    if args.manifest:
        if not Path(args.manifest).is_file():
            print(f"ERROR: manifest not found: {args.manifest}", file=sys.stderr)
            return 2
        try:
            manifest = load_manifest(args.manifest)
        except (OSError, ValueError, KeyError, TypeError) as e:
            print(f"ERROR: manifest unreadable: {args.manifest}: {e!r}", file=sys.stderr)
            return 2

    if not art_dir.exists() or not any(art_dir.glob("*.png")):
        print(f"ERROR: no PNGs found in {art_dir}. Run 'generate' first.",
              file=sys.stderr)
        return 4

    missing: list[str] = []
    if manifest is not None:
        for s in manifest.sprites:
            if not (art_dir / f"{s.name}.png").is_file():
                missing.append(f"sprite {s.name!r}: no {art_dir / (s.name + '.png')}")
        if app_dir is not None:
            for snd in manifest.sounds:
                ws_mp3 = workspace / "wav" / "assets" / f"{snd.name}.mp3"
                app_mp3 = app_dir / "sound" / "assets" / f"{snd.name}.mp3"
                if not (ws_mp3.is_file() or app_mp3.is_file()):
                    missing.append(f"sound {snd.name!r}: no {ws_mp3} or {app_mp3}")
    if args.icon and not Path(args.icon).is_file():
        missing.append(f"launcher icon: --icon {args.icon} not found")
    if missing:
        print(f"ERROR: incomplete asset set - {len(missing)} input(s) missing; nothing was packed or written "
              f"(a partial set is never packed):", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 4
    if manifest is not None:
        extra = sorted(p.stem for p in art_dir.glob("*.png")
                       if p.stem not in {s.name for s in manifest.sprites} and p.stem != "0")
        if extra:
            print(f"WARNING: {len(extra)} PNG(s) in {art_dir} are not manifest sprites and will be packed too: "
                  f"{', '.join(extra[:8])}{' ...' if len(extra) > 8 else ''} (delete retired ones)",
                  file=sys.stderr)

    carry = None
    build_psd_py = find_script("build_psd.py")
    pack_py = find_script("pack.py")

    src_dir.mkdir(parents=True, exist_ok=True)
    if app_dir is not None:
        # a pack in progress vouches for nothing: pack-status says "stale" until this run succeeds
        (app_dir / PACK_INPUTS_FILE).unlink(missing_ok=True)

    # ── clean intermediates: every output below is rebuilt from the inputs ─
    for d in (packed_dir, exported_dir):
        if app_dir is not None and d.resolve() == (app_dir / "art" / "packed").resolve():
            print(f"  NOTE: {d} is the app's own art/packed - not cleared")
            continue
        n = _clear_intermediate(d)
        if n:
            print(f"  cleared {n} stale entr{'y' if n == 1 else 'ies'} from {d}")

    print("=== Stage: build_psd ===")
    rc = _run([
        sys.executable, str(build_psd_py),
        str(art_dir), str(psd_path),
        "--padding", "2",
        "--bg-color", "#FF00FF",
    ])
    if rc != 0:
        return rc

    print("=== Stage: pack ===")
    pack_cmd = [
        sys.executable, str(pack_py),
        "--export",
        "--build-palette",
        "--build-ids",
        "--emit-raw",
        "--art-dir", str(workspace),
        "--exported-dir", str(exported_dir),
        "--packed-dir", str(packed_dir),
        "--output-dir", str(packed_dir),
        "--raw-dir", str(packed_dir),
        "--ids-output", str(ids_path),
        "--assets", "assets",
    ]
    if app_dir is not None:
        n_fonts, n_stale, ws_only = _sync_fonts(app_dir, workspace)
        if n_fonts:
            print(f"  copied {n_fonts} new/changed font file(s) -> {workspace / 'fonts'}")
        if n_stale:
            print(f"  removed {n_stale} stale font atlas page(s) from {workspace / 'fonts'}")
        if ws_only:
            print(f"  NOTE: {', '.join(ws_only)} exist only in {workspace / 'fonts'} (not in the app's art/): "
                  f"still packed")
        if not args.icon:
            icon = app_dir / "art" / "icon.png"
            if icon.is_file() and TEMPLATE_ICON.is_file() and icon.read_bytes() == TEMPLATE_ICON.read_bytes():
                print("WARNING: app_<game>/art/icon.png is still the TEMPLATE icon - make the game's "
                      "launcher icon (scripts/icon_badge.py make <picture> --out app_<game>/art/icon.png) and "
                      "pass --icon", file=sys.stderr)
        _warn_icon_shape(Path(args.icon) if args.icon else app_dir / "art" / "icon.png")
        # the beta simulator loads sounds ONLY from <app_dir>/sound/assets/;
        # the generate stage encodes its beta mp3s into <workspace>/wav/assets/
        # (it doesn't know the app dir), so carry them over BEFORE pack.py
        # scans the app dir for KIND_SOUND records
        wav_assets = workspace / "wav" / "assets"
        mp3s = sorted(wav_assets.glob("*.mp3")) if wav_assets.is_dir() else []
        if mp3s:
            snd_assets = app_dir / "sound" / "assets"
            snd_assets.mkdir(parents=True, exist_ok=True)
            for mp3 in mp3s:
                shutil.copy2(mp3, snd_assets / mp3.name)
            print(f"  copied {len(mp3s)} beta mp3(s) -> {snd_assets}")
        if manifest is not None:
            # ship exactly the manifest's sounds: the scaffold copies the template's demo mp3s into
            # sound/assets and every packer packs whatever lies there. sound/unused/ is read by no packer
            # (pack.py and octpack-link read sound/assets, octpack's converter only sound/'s own files).
            wanted = {snd.name for snd in manifest.sounds}
            snd_assets = app_dir / "sound" / "assets"
            extra_mp3 = sorted(p for p in snd_assets.glob("*.mp3") if p.stem not in wanted) \
                if snd_assets.is_dir() else []
            if extra_mp3:
                unused = app_dir / "sound" / "unused"
                unused.mkdir(parents=True, exist_ok=True)
                for p in extra_mp3:
                    shutil.move(str(p), str(unused / p.name))
                print(f"WARNING: moved {len(extra_mp3)} mp3(s) not in the manifest out of {snd_assets} -> "
                      f"{unused} (they would ship): {', '.join(p.stem for p in extra_mp3)}", file=sys.stderr)
        # beta container: index.bin + art/packed + kind-aware
        # src/app_<game>_ids.h, emitted into the app dir by pack.py
        pack_cmd += [
            "--beta-app-dir", str(app_dir),
            "--app-name", f"app_{args.game}",
        ]
        if args.manifest:
            pack_cmd += ["--manifest", str(args.manifest)]
        if args.icon:
            pack_cmd += ["--icon", str(args.icon)]
        # an extracted game (manifest _origin): every record nobody changed is carried through byte for byte
        if args.manifest:
            import carry_art
            icon_for_plan = Path(args.icon) if args.icon else _auto_icon(workspace, app_dir)
            carry = carry_art.build_plan(args.manifest, workspace, icon_for_plan, workspace / "fonts")
            if carry is not None:
                packed_dir.mkdir(parents=True, exist_ok=True)
                plan_path = packed_dir / "carry.json"
                plan_path.write_text(json.dumps(carry, indent=1), encoding="utf-8")
                # only edited / added sprites are encoded: give them a palette of up to 255 colours (the
                # default pre-reduces any sprite over 127 colours, too lossy for a game's own edited art)
                pack_cmd += ["--carry", str(plan_path), "--pre-reduce", "255"]
                for n, why in sorted(carry["reencoded"].items()):
                    print(f"  re-encoded from its PNG: {n} ({why})")
                for line in carry_art.font_lines(carry):
                    print(line)
    rc = _run(pack_cmd)
    if rc != 0:
        return rc

    pal_png = packed_dir / "pal.png"
    needs_palette = manifest is None or any(sp.color != "full" for sp in manifest.sprites)
    if needs_palette and not pal_png.exists():
        print(f"ERROR: expected {pal_png} was not produced.", file=sys.stderr)
        return 5
    if not ids_path.exists() or ids_path.stat().st_size == 0:
        print(f"ERROR: {ids_path} missing or empty.", file=sys.stderr)
        return 5

    if args.app_dir and manifest is not None:
        fixed = _center_pivots(manifest, Path(args.app_dir), skip=set(carry["sprites"]) if carry else set())
        if fixed:
            print(f"  pivots centred on {fixed} sprite(s)")
        # a font the carry plan keeps out (carried records, or never in the extracted game's pack) needs none
        not_built = set(carry.get("font_skip", [])) if carry else set()
        fonts = [f for f in (Path(args.app_dir) / "art").glob("font_*.fnt") if f.stem not in not_built]
        beta_hdr = Path(args.app_dir) / "src" / ids_path.name
        if fonts and beta_hdr.is_file() and "font_" not in beta_hdr.read_text(encoding="utf-8").lower():
            print(f"ERROR: {len(fonts)} BMFont(s) in app art/ but no font_ glyphs in {beta_hdr.name}: "
                  f"labels would draw nothing", file=sys.stderr)
            return 5

    dest_ids = src_dir / ids_path.name
    if args.app_dir:
        # Beta mode: pack.py already emitted the canonical kind-aware header
        # (record index == asset id, SND_/MAP_ enums) into <app_dir>/src/.
        # The legacy workspace header uses a different numbering and has no
        # sound enum, so copying it over src/ would clobber the real one.
        beta_ids = Path(args.app_dir) / "src" / ids_path.name
        if not beta_ids.is_file() or beta_ids.stat().st_size == 0:
            print(f"ERROR: beta ids header missing or empty: {beta_ids}",
                  file=sys.stderr)
            return 5
        if dest_ids.resolve() != beta_ids.resolve():
            shutil.copy2(beta_ids, dest_ids)
        header = beta_ids.read_text(encoding="utf-8")
    else:
        shutil.copy2(ids_path, dest_ids)
        header = ids_path.read_text(encoding="utf-8")
    bmp_count = header.count("BMP_") - header.count("BMP_none") \
                - header.count("BMP_last") - header.count("BMP_0")

    raw_count = len(list(packed_dir.glob("*.raw")))

    if args.app_dir:
        # Beta mode: these *.raw live in the legacy workspace copy only; the
        # sim actually loads <app_dir>/art/packed/*.raw (copied there by
        # pack.py's --beta-app-dir handling above), not this workspace path.
        raw_label = "legacy workspace copies; the sim loads <app_dir>/art/packed"
    else:
        raw_label = "sim/.oct assets"
    print("=" * 60)
    print(f"  packed/pal.png       : ok")
    print(f"  packed/*.raw         : {raw_count} file(s) ({raw_label})")
    print(f"  {ids_path.name:<20}: {bmp_count} BMP_* constants")
    print(f"  {dest_ids}: copied")
    if app_dir is not None:
        manifest_path = Path(args.manifest) if args.manifest else None
        icon_used = Path(args.icon) if args.icon else _auto_icon(workspace, app_dir)
        record = {
            "version": PACK_INPUTS_VERSION,
            "packer": "build_pipeline.py pack",
            "packed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "game": args.game,
            # paths relative to the app folder: the record ships with the app and never names this machine
            "paths": "relative to the app folder",
            "workspace": _rel_to_app(workspace, app_dir),
            "app_dir": ".",
            "manifest": _rel_to_app(manifest_path, app_dir),
            "icon": _rel_to_app(icon_used, app_dir),
            "icon_arg": _rel_to_app(Path(args.icon), app_dir) if args.icon else None,
            "inputs": pack_inputs(workspace, app_dir, manifest_path, icon_used),
            "outputs": pack_outputs(app_dir, args.game),
        }
        (app_dir / PACK_INPUTS_FILE).write_text(json.dumps(record, indent=1, sort_keys=True), encoding="utf-8")
        print(f"  {PACK_INPUTS_FILE:<20}: {len(record['inputs'])} input(s) recorded (pack-status compares them)")
    print("=" * 60)
    return 0


def do_pack_status(args: argparse.Namespace) -> int:
    fresh, lines = pack_status(args.game, Path(args.workspace), Path(args.app_dir),
                               Path(args.manifest) if args.manifest else None,
                               Path(args.icon) if args.icon else None)
    octpack = (Path(args.app_dir) / "art" / "octpack.json").is_file()
    rec = Path(args.app_dir) / ("index.bin" if octpack else PACK_INPUTS_FILE)
    if fresh:
        what = "is newer than every octpack.json input" if octpack else "matches the current inputs and outputs"
        print(f"pack-status: FRESH - {rec} {what}")
        return 0
    how = "repack_app.py / octpack-pack" if octpack else "build_pipeline.py pack ..."
    print(f"pack-status: STALE - repack ({how}); {len(lines)} difference(s):")
    for line in lines:
        print(line if line.startswith("  ") else f"  {line}")
    return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="build_pipeline",
        description="cube_asset-builder pipeline driver")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="Provider-free manifest check (schema, names, tiers, background, "
                                        "launcher_icon, Codex prompt rules); exit 0 ok, 2 errors. Never "
                                        "generates, never touches the network")
    v.add_argument("--manifest", required=True, help="Path to plans/<game>_assets.json")
    v.add_argument("--no-budget", action="store_true",
                   help="Skip the image-budget check (images still to draw vs the profile's or tier's "
                        "budget.images); sprites already drawn never count, so a mod does not need it")
    v.set_defaults(func=do_validate)

    g = sub.add_parser("generate", help="Generate sprites (Codex via art.py, or a paid API) + "
                                        "placeholder sounds from the manifest")
    g.add_argument("--manifest", required=True, help="Path to plans/<game>_assets.json")
    g.add_argument("--workspace", default=None,
                   help="Per-game workspace (default: assets_<game>/ next to plans/, the folder "
                        "cube_art-director uses). PNGs -> <ws>/art, sounds -> <ws>/wav.")
    g.add_argument("--group", default=None,
                   help="Only regenerate one group (sprites + sounds)")
    g.add_argument("--force", action="store_true",
                   help="Redraw sprites that already have an image (Codex: a raw image; paid API: the "
                        "PNG in <ws>/art). Default: draw only what is missing")
    g.add_argument("--jobs", type=int, default=3,
                   help="Codex: parallel Codex runs (default 3)")
    g.add_argument("--mp3", action="store_true",
                   help="Require beta mp3 encoding (fail if ffmpeg is missing; "
                        "without this flag mp3s are encoded only when ffmpeg "
                        "is on PATH)")
    g.add_argument("--allow-paid", action="store_true",
                   help="Opt in to the PAID image API the user chose (setup profile, WOWCUBE_IMAGE_PROVIDER, IMAGE_API "
                        "or ~/.wowcube/image_api.json) - only after the user agreed to pay per image. Same as "
                        "WOWCUBE_ALLOW_PAID_IMAGES=1. Without it an inherited key is never used")
    g.add_argument("--over-budget", action="store_true",
                   help="Draw past the image budget (every request is counted in the ledger, cube_art-director "
                        "art_budget.py) - only on the user's explicit yes")
    g.set_defaults(func=do_generate)

    k = sub.add_parser("pack", help="Build PSD + run pack.py + copy ids to src/")
    k.add_argument("--game", required=True, help="Game name (used in _ids.h filename)")
    k.add_argument("--workspace", default="assets", help="Workspace root (default: assets)")
    k.add_argument("--src-dir", default="src", help="Target dir for the ids header")
    k.add_argument("--app-dir", default=None,
                   help="Beta app root (app_<game>/). When set, pack.py also "
                        "emits the beta container there: index.bin, "
                        "art/packed/*.{raw,pal}, launcher icon maps, and a "
                        "kind-aware src/app_<game>_ids.h")
    k.add_argument("--manifest", default=None,
                   help="Path to plans/<game>_assets.json, so color=='full' "
                        "sprites are RAW565-encoded in the beta container")
    k.add_argument("--icon", default=None,
                   help="Launcher icon PNG forwarded to pack.py's beta emit "
                        "(default: pack.py auto-detects <app-dir>/art/icon.png)")
    k.set_defaults(func=do_pack)

    s = sub.add_parser("pack-status", help="Exit 0 when <app>/.pack_inputs.json matches the current inputs "
                                           "(manifest, PNGs, mp3s, fonts, icon) and outputs, 1 when stale or "
                                           "missing; prints what changed")
    s.add_argument("--game", required=True, help="Game name (the ids header is src/app_<game>_ids.h)")
    s.add_argument("--workspace", required=True, help="The workspace the pack used (assets_<game>)")
    s.add_argument("--app-dir", required=True, help="The app the pack wrote (app_<game>)")
    s.add_argument("--manifest", default=None, help="The manifest the pack used (plans/<game>_assets.json)")
    s.add_argument("--icon", default=None,
                   help="The launcher icon (default: the --icon of the recorded pack, else the auto-detected one)")
    s.set_defaults(func=do_pack_status)

    return p


def _cli(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def main() -> int:
    return _cli(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
