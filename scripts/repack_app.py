"""One-command repack cycle for an existing app_<game> folder (spec §9, §10).

    python scripts/repack_app.py --app-dir <workspace>/app_<game>
                                 [--manifest <path>|auto] [--icon <path>|auto]
                                 [--skip-device] [--octavios <path>]
                                 [--out <path.oct>] [--builder auto|octpack|python]
                                 [--bump minor|patch] [--allow-asset-loss]

The "I replaced the assets — rebuild" cycle in one command:

  1. repack the beta container, using the app's CANONICAL pack invocation
     auto-detected from what exists on disk (see detect_pack_command below)
     — the user never has to remember flags. An app with art/octpack.json
     (PSD-authored, the official workflow) is repacked by the SDK's
     octpacker: `uv run --frozen --project <octavios>/octpacker octpack-pack
     <app> --engine <octavios>`; every other shape by our pack.py /
     build_pipeline.py pack;
  2. bump the version: by default the MINOR (+1, patch back to 0; the
     repository's release rule), `--bump patch` for the patch instead:
     APP_VERSION_MINOR / _PATCH in src/app_metadata.h (current app layout),
     else the literal OCT_APP_SEMVER(...) or legacy integer in src/app.h. The
     cube's catalog compares versions exactly on install, so an un-bumped
     rebuild may not apply over an already-installed app, and the .oct always
     carries exactly the version in the code (build_device verifies it);
  3. unless --skip-device: device build via scripts/build_device.(ps1|sh)
     (octpack-build when available, python builder as fallback, ARM-embed
     verification) into <workspace>/dist/<app>.oct. No simulator is started.

Before anything is written it refuses (exit 2) a repack whose sources cannot
produce every sprite packed today (an app delivered without its art sources:
only art/packed + index.bin), naming them and the scripts/extract_art.py
command that recovers them; --allow-asset-loss overrides.

Cross-platform single entry point; exits non-zero on any stage failure.
"""
from __future__ import annotations

import argparse
import codecs
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PACK_PY = SCRIPT_DIR / "pack.py"
BUILD_PIPELINE_PY = SCRIPT_DIR / "build_pipeline.py"

_VERSION_RE = re.compile(
    r"^(?P<pre>\s*#\s*define\s+APP_VERSION\s+)(?P<num>\d+)(?P<tail>.*)$",
    re.MULTILINE)


_PATCH_RE = re.compile(
    r"^(?P<pre>\s*#\s*define\s+APP_VERSION_PATCH\s+)(?P<num>\d+)(?P<tail>.*)$",
    re.MULTILINE)
_SEMVER_RE = re.compile(
    r"^(?P<pre>\s*#\s*define\s+APP_VERSION\s+OCT_APP_SEMVER\s*\(\s*(?P<ma>\d+)\s*,\s*(?P<mi>\d+)\s*,\s*)"
    r"(?P<num>\d+)(?P<tail>\s*\).*)$",
    re.MULTILINE)


def _rewrite(p: Path, text: str, has_bom: bool) -> None:
    p.write_bytes((codecs.BOM_UTF8 if has_bom else b"") + text.encode("utf-8"))


def bump_patch(app_h_path: str | Path) -> int:
    """+1 the app's patch version; return the new APP_VERSION value.

    Three layouts, newest first (the cube's catalog compares versions on
    install, so an un-bumped rebuild may not apply over an installed app):
      1. current layout: `#define APP_VERSION_PATCH <n>` in src/app_metadata.h
         (or app.h), APP_VERSION = OCT_APP_SEMVER(MAJOR, MINOR, PATCH);
      2. `#define APP_VERSION OCT_APP_SEMVER(<ma>, <mi>, <n>)` with literals;
      3. legacy `#define APP_VERSION <int>` (102 = v1.02): +1 on the integer.
    Semver fields are bytes: a patch of 255 cannot be bumped (raise; bump the
    minor by hand). Comment tails and the files' BOMs are preserved.
    """
    app_h = Path(app_h_path)
    for p in (app_h.parent / "app_metadata.h", app_h):
        if not p.is_file():
            continue
        raw = p.read_bytes()
        has_bom = raw.startswith(codecs.BOM_UTF8)
        text = raw.decode("utf-8-sig")
        m = _PATCH_RE.search(text)
        if m:
            patch = int(m.group("num")) + 1
            if patch > 255:
                raise ValueError(f"APP_VERSION_PATCH would exceed 255 in {p}: bump the minor version by hand")
            _rewrite(p, text[:m.start("num")] + str(patch) + text[m.end("num"):], has_bom)
            ma = re.search(r"^\s*#\s*define\s+APP_VERSION_MAJOR\s+(\d+)", text, re.M)
            mi = re.search(r"^\s*#\s*define\s+APP_VERSION_MINOR\s+(\d+)", text, re.M)
            return (1 << 24) | (int(ma.group(1)) if ma else 0) << 16 | (int(mi.group(1)) if mi else 0) << 8 | patch
        m = _SEMVER_RE.search(text)
        if m:
            patch = int(m.group("num")) + 1
            if patch > 255:
                raise ValueError(f"OCT_APP_SEMVER patch would exceed 255 in {p}: bump the minor version by hand")
            _rewrite(p, text[:m.start("num")] + str(patch) + text[m.end("num"):], has_bom)
            return (1 << 24) | int(m.group("ma")) << 16 | int(m.group("mi")) << 8 | patch
    p = app_h
    raw = p.read_bytes()
    has_bom = raw.startswith(codecs.BOM_UTF8)
    text = raw.decode("utf-8-sig")
    m = _VERSION_RE.search(text)
    if not m:
        raise ValueError(f"no APP_VERSION_PATCH, OCT_APP_SEMVER(...) or '#define APP_VERSION <int>' in {p}")
    new_version = int(m.group("num")) + 1
    _rewrite(p, text[:m.start("num")] + str(new_version) + text[m.end("num"):], has_bom)
    return new_version


_MINOR_RE = re.compile(
    r"^(?P<pre>\s*#\s*define\s+APP_VERSION_MINOR\s+)(?P<num>\d+)(?P<tail>.*)$",
    re.MULTILINE)


def bump_minor(app_h_path: str | Path) -> int:
    """+1 the app's MINOR version and reset the patch to 0; return the new APP_VERSION value.

    The repository's release rule (every shipped rebuild bumps the minor; the .oct carries exactly the code's
    version). Same three layouts as bump_patch: APP_VERSION_MINOR + APP_VERSION_PATCH in src/app_metadata.h
    (or app.h); a literal OCT_APP_SEMVER(<ma>, <mi>, <pa>); a legacy `#define APP_VERSION <int>` (+1, it has no
    minor). A minor of 255 cannot be bumped (raise; bump the major by hand). Comment tails and BOMs are kept."""
    app_h = Path(app_h_path)
    for p in (app_h.parent / "app_metadata.h", app_h):
        if not p.is_file():
            continue
        raw = p.read_bytes()
        has_bom = raw.startswith(codecs.BOM_UTF8)
        text = raw.decode("utf-8-sig")
        mi = _MINOR_RE.search(text)
        if mi and _PATCH_RE.search(text):
            minor = int(mi.group("num")) + 1
            if minor > 255:
                raise ValueError(f"APP_VERSION_MINOR would exceed 255 in {p}: bump the major version by hand")
            text = text[:mi.start("num")] + str(minor) + text[mi.end("num"):]
            pa = _PATCH_RE.search(text)
            text = text[:pa.start("num")] + "0" + text[pa.end("num"):]
            _rewrite(p, text, has_bom)
            ma = re.search(r"^\s*#\s*define\s+APP_VERSION_MAJOR\s+(\d+)", text, re.M)
            return (1 << 24) | (int(ma.group(1)) if ma else 0) << 16 | minor << 8
        m = _SEMVER_RE.search(text)
        if m:
            minor = int(m.group("mi")) + 1
            if minor > 255:
                raise ValueError(f"OCT_APP_SEMVER minor would exceed 255 in {p}: bump the major version by hand")
            text = text[:m.start("mi")] + str(minor) + text[m.end("mi"):m.start("num")] + "0" + text[m.end("num"):]
            _rewrite(p, text, has_bom)
            return (1 << 24) | int(m.group("ma")) << 16 | minor << 8
    # legacy integer counter: no minor field, +1 like bump_patch
    return bump_patch(app_h)


def bump_version(app_h_path: str | Path, part: str = "minor") -> int:
    """bump_minor (default, the release rule) or bump_patch."""
    if part == "patch":
        return bump_patch(app_h_path)
    if part != "minor":
        raise ValueError(f"unknown version part {part!r} (minor or patch)")
    return bump_minor(app_h_path)


def _version_str(value: int) -> str:
    """'1.2.3' for an OCT_APP_SEMVER value (scheme byte 1), the plain number for a legacy counter."""
    if (value >> 24) & 0xFF == 1:
        return f"{(value >> 16) & 0xFF}.{(value >> 8) & 0xFF}.{value & 0xFF}"
    return str(value)


def _app_name(app_dir: Path) -> str:
    """App name from the *.target marker (same rule as build_device);
    fall back to the folder name when no marker exists."""
    targets = sorted(app_dir.glob("*.target"))
    if targets:
        return targets[0].stem
    return app_dir.name


def _manifest_has_palette_sprites(manifest_path: Path) -> bool:
    """True when at least one sprite is palette-encoded (color != 'full').

    Plain JSON read on purpose: detection must not fail on schema details —
    pack.py itself validates the manifest properly right after.
    """
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return True     # unreadable manifest: keep the palette build, let pack.py complain
    sprites = data.get("sprites") or []
    return any(s.get("color") != "full" for s in sprites)


def _have(exe: str) -> bool:
    return shutil.which(exe) is not None


def packaged_python() -> bool:
    """True when this interpreter runs inside a Microsoft Store (MSIX) package,
    e.g. the Store's Python 3.12. Every process it starts - grandchildren
    included - sees the package's private copy of AppData: uv then cannot find
    its managed Python, "ignores" the octpacker environment and rebuilds it
    (observed: it deleted a working offline venv). So uv is never started from
    such an interpreter; build_device runs with -NoUv instead."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        length = ctypes.c_uint32(0)
        # APPMODEL_ERROR_NO_PACKAGE (15700) = an ordinary desktop process
        return ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), None) != 15700
    except (AttributeError, OSError):
        return False


STORE_PYTHON_NOTE = ("this python is the Microsoft Store build: programs it starts see a private copy of AppData, so "
                     "uv cannot find its managed Python and would rebuild the octpacker environment")


def default_octavios(app_dir: str | Path) -> Path:
    """The tree used when --octavios is not given: this plugin's public game API (api/: include + apps), the same
    default as build_device. It has no octpacker, so a PSD-authored app (art/octpack.json) needs an internal SDK
    checkout: passed with --octavios, or an octavios/ with octpacker/ next to the app folder (a WowCube developer's
    layout); octpack_pack_command says so when there is none."""
    sibling = Path(app_dir).resolve().parent / "octavios"
    if (sibling / "octpacker" / "pyproject.toml").is_file():
        return sibling
    return Path(__file__).resolve().parent.parent / "api"


def octpack_pack_command(app_dir: str | Path, octavios: str | Path | None = None) -> list[str]:
    """The official PSD-workflow repack of an app that has art/octpack.json:
    `uv run --frozen --project <octavios>/octpacker octpack-pack <app> --engine <octavios>`
    (the engine's dev-tooling notes, §2.3/2.5: sound conversion, PSD/font export, link
    -> art/packed, index.bin, src/<app>_ids.h). --frozen: never rewrite the
    SDK's uv.lock. Raises ValueError when the SDK or uv is missing."""
    app_dir = Path(app_dir).resolve()
    sdk = Path(octavios).resolve() if octavios else default_octavios(app_dir)
    project = sdk / "octpacker"
    if not (project / "pyproject.toml").is_file():
        raise ValueError(
            f"{app_dir / 'art' / 'octpack.json'} marks a PSD-authored app: it is packed by the official octpacker "
            f"(octpack-pack), internal SDK only: it needs an SDK checkout with {project / 'pyproject.toml'} - pass "
            f"--octavios <dir>. Without the SDK, export the PSD layers to PNG and use the manifest path")
    if not _have("uv"):
        raise ValueError("the official octpacker runs through uv, which is not on PATH (install it with the "
                         "user's approval: scripts/check_env.ps1 -Install / check_env.sh)")
    cmd = ["uv", "run", "--frozen", "--project", str(project), "octpack-pack", str(app_dir), "--engine", str(sdk)]
    if packaged_python():
        raise ValueError(f"{STORE_PYTHON_NOTE}. Run the official packer from a normal PowerShell instead: "
                         f"{' '.join(cmd)} - then build the device .oct there too (scripts\\build_device.ps1 "
                         f"-AppDir {app_dir}), or run this script with a python.org / uv-managed Python")
    return cmd


def auto_icon(app_dir: str | Path) -> Path | None:
    """The launcher icon a repack uses when --icon is not given. One source per kind of game:
    an extracted game (assets_<game>/extracted.json next to the app, scripts/extract_art.py) ->
    assets_<game>/icon.png, the packed ico_idle carried through byte for byte while unchanged (the app's own
    art/icon.png, if any, is not used for it); every other game -> app_<game>/art/icon.png; else None."""
    app_dir = Path(app_dir).resolve()
    app = _app_name(app_dir)
    game = app[4:] if app.startswith("app_") else app
    ws = app_dir.parent / f"assets_{game}"
    if (ws / "extracted.json").is_file() and (ws / "icon.png").is_file():
        return ws / "icon.png"
    icon = app_dir / "art" / "icon.png"
    return icon if icon.is_file() else None


def detect_pack_command(app_dir: str | Path,
                        manifest: str | Path = "auto",
                        icon: str | Path = "auto",
                        octavios: str | Path | None = None,
                        ) -> tuple[list[str], Path]:
    """Assemble the app's canonical pack invocation from what's on disk.

    Returns (command, cwd). Checked first: **`art/octpack.json`** = an app
    authored in Photoshop for the official octpacker (STAGE3_ASSETS "PSD
    workflow"): repack with `octpack-pack` (octpack_pack_command; `octavios`
    defaults to an SDK in <app>/../octavios, else the plugin's api/, which has no octpacker), never with our pack.py - the two paths
    must not be mixed. --manifest/--icon do not apply to it. Otherwise three
    on-disk shapes exist:

    **Per-game workspace** (the current asset stage, cube_asset-builder) —
    `<root>/assets_<game>/art/*.png` next to `app_<game>/` (root = the app's
    parent, which also holds `plans/<game>_assets.json`): re-run the same
    `build_pipeline.py pack --game <game> --workspace assets_<game> ...` from
    <root>, so the art is re-atlased from the workspace PNGs.

    **Pipeline shape** — `assets/art/*.png` present: the app's art was built
    by the asset-builder pipeline (AI-generated or agent-drawn placeholder
    PNGs in the `assets/` workspace, atlased into `assets/assets.psd` by
    build_pipeline.py pack). The canonical invocation is that same
    `build_pipeline.py pack` command (re-atlases the workspace PNGs, then
    drives pack.py) — NOT the scaffold pack.py call, which would `--export`
    the template's untouched `art/assets.psd` over the real art and fail on
    any manifest full-color sprite.

    **Scaffold/legacy shape** — everything else mirrors the scaffold-time
    invocation (scripts/new_app.ps1 step 5) with these detection rules:

      *.target marker          -> --app-name (fallback: folder name)
      plans/*_assets.json      -> --manifest (exactly one match; several ->
                                  error asking for an explicit --manifest)
      icon                     -> --icon (auto_icon: assets_<game>/icon.png of an
                                  extracted game, else art/icon.png)
      art/*assets*.psd         -> --export (PSD workflow; PNG-only apps keep
                                  their art/exported PNGs untouched)
      palette sprites present  -> --build-palette (any manifest sprite with
                                  color != 'full', or no manifest at all —
                                  the legacy/scaffold shape; all-full apps
                                  like photo frames skip the palette build)

    Manifest and icon detection are shared by both shapes.
    """
    app_dir = Path(app_dir).resolve()
    app = _app_name(app_dir)
    game = app[4:] if app.startswith("app_") else app
    root = app_dir.parent

    # Official PSD workflow first: octpack.json decides, our packer never touches such an app
    if (app_dir / "art" / "octpack.json").is_file():
        return octpack_pack_command(app_dir, octavios), app_dir

    # --manifest: explicit path, or single <app>/plans/*_assets.json, or
    # <root>/plans/<game>_assets.json (the pipeline keeps plans/ next to the app), or omitted
    if str(manifest) == "auto":
        found = sorted((app_dir / "plans").glob("*_assets.json"))
        if len(found) > 1:
            names = ", ".join(p.name for p in found)
            raise ValueError(
                f"several manifests in {app_dir / 'plans'} ({names}) - "
                f"pass an explicit --manifest")
        if not found and (root / "plans" / f"{game}_assets.json").is_file():
            found = [root / "plans" / f"{game}_assets.json"]
        manifest_path = found[0] if found else None
    else:
        manifest_path = Path(manifest)
        if not manifest_path.is_file():
            raise ValueError(f"manifest not found: {manifest_path}")

    # --icon: explicit path, or auto: an extracted game's assets_<game>/icon.png (its one launcher icon source,
    # STAGE3_ASSETS.md section 5), else art/icon.png, else omitted
    if str(icon) == "auto":
        icon_path = auto_icon(app_dir)
    else:
        icon_path = Path(icon)
        if not icon_path.is_file():
            raise ValueError(f"icon not found: {icon_path}")

    # Per-game workspace next to the app (cube_asset-builder's canonical
    # command, run from <root>).
    workspace = root / f"assets_{game}"
    if sorted((workspace / "art").glob("*.png")):
        cmd = [sys.executable, str(BUILD_PIPELINE_PY), "pack",
               "--game", game,
               "--workspace", str(workspace),
               "--src-dir", str(app_dir / "src"),
               "--app-dir", str(app_dir)]
        if manifest_path is not None:
            cmd += ["--manifest", str(manifest_path)]
        if icon_path is not None:
            cmd += ["--icon", str(icon_path)]
        return cmd, root

    # Pipeline shape: sprite PNGs in the assets/ workspace -> re-run the
    # canonical build_pipeline.py pack invocation from the app dir.
    if sorted((app_dir / "assets" / "art").glob("*.png")):
        cmd = [sys.executable, str(BUILD_PIPELINE_PY), "pack",
               "--game", game,
               "--workspace", "assets",
               "--src-dir", "src",
               "--app-dir", str(app_dir)]
        if manifest_path is not None:
            cmd += ["--manifest", str(manifest_path)]
        if icon_path is not None:
            cmd += ["--icon", str(icon_path)]
        return cmd, app_dir

    cmd: list[str] = [sys.executable, str(PACK_PY)]
    if sorted((app_dir / "art").glob("*assets*.psd")):
        cmd.append("--export")
    if manifest_path is None or _manifest_has_palette_sprites(manifest_path):
        cmd.append("--build-palette")
    cmd += [
        "--build-ids",
        "--art-dir", "art",
        "--exported-dir", str(Path("art") / "exported"),
        "--packed-dir", str(Path("art") / "packed"),
        "--output-dir", str(Path("art") / "packed"),
        "--ids-output", str(Path("src") / f"{app}_ids.h"),
        "--assets", "assets",
        "--beta-app-dir", str(app_dir),
        "--app-name", app,
    ]
    if manifest_path is not None:
        cmd += ["--manifest", str(manifest_path)]
    if icon_path is not None:
        cmd += ["--icon", str(icon_path)]
    return cmd, app_dir


_GLYPH_RE = re.compile(r"^font_[A-Za-z0-9_]*_\d{5}$")
# sprite records the packers generate themselves (slot 0, the launcher icon)
_GENERATED_SPRITES = {"zero", "ico_idle", "0"}


def packed_sprite_names(app_dir: str | Path) -> set[str]:
    """Sprite names in the app's index.bin that come from art or fonts (not the packer's own slot-0 /
    launcher icon records). BMFont glyphs (font_<n>_<5 digits>) count: lost_sprites decides whether a font
    source or a carried record covers them. Empty when there is no index."""
    index = Path(app_dir) / "index.bin"
    if not index.is_file():
        return set()
    sys.path.insert(0, str(SCRIPT_DIR))
    import pack_beta
    try:
        records = pack_beta.read_index_bin(index)
    except (OSError, ValueError):
        return set()
    return {n for k, n in records if k == pack_beta.KIND_SPRITE and n not in _GENERATED_SPRITES}


def font_sources(app_dir: str | Path, workspace: str | Path | None = None) -> set[str]:
    """Font names (`font_1`) a pack rebuilds glyphs from: <app>/art/font_*.fnt, <app>/art/fonts/*.fnt and,
    for the manifest pack, <workspace>/fonts/*.fnt."""
    dirs = [Path(app_dir) / "art", Path(app_dir) / "art" / "fonts"]
    if workspace is not None:
        dirs.append(Path(workspace) / "fonts")
    return {p.stem for d in dirs if d.is_dir() for p in d.glob("*.fnt")}


def carried_glyphs(workspace: str | Path | None) -> set[str]:
    """Glyph records an extraction kept (<workspace>/extracted.json, scripts/extract_art.py): the manifest
    pack carries them through unchanged when their font has no source."""
    if workspace is None:
        return set()
    listing = Path(workspace) / "extracted.json"
    try:
        data = json.loads(listing.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return set()
    return {a["name"] for a in data.get("assets", [])
            if a.get("glyph") and a.get("record") and (Path(workspace) / a["record"]).is_file()}


def _old_extraction_hint(lost: list[str], ws: Path | None) -> str:
    """The re-extract hint, only when it applies: glyphs would be lost and the workspace holds an extraction
    (extracted.json) that kept no glyph records (made by an extract_art.py older than glyph carrying)."""
    if ws is None or not any(_GLYPH_RE.match(n) for n in lost) or not (Path(ws) / "extracted.json").is_file():
        return ""
    if carried_glyphs(ws):
        return ""
    return (f"The extraction in {ws} kept no font glyph records (an older extract_art.py): re-run it with "
            f"--force, after saving any PNG you edited there.\n")


def _workspace_of(cmd: list[str], cwd: str | Path) -> Path | None:
    if str(BUILD_PIPELINE_PY) not in cmd or "--workspace" not in cmd:
        return None
    ws = Path(cmd[cmd.index("--workspace") + 1])
    return ws if ws.is_absolute() else Path(cwd) / ws


def _psd_sprite_names(psd: Path) -> set[str] | None:
    """The sprite PNG names an assets PSD exports (pack_psd.export_psd_file_python's rule); None when the PSD
    cannot be read here."""
    try:
        from psd_tools import PSDImage
        sys.path.insert(0, str(SCRIPT_DIR))
        from pack_psd import LayerName, is_name_declaration
        doc = PSDImage.open(psd)
    except Exception:       # noqa: BLE001 - no psd-tools, a damaged file: the caller says "cannot tell"
        return None
    names = set()
    for layer in doc:
        if layer.name.startswith("~") or not layer.is_visible() or not layer.name.isascii():
            continue
        parsed = LayerName.parse(layer.name)
        if parsed.is_marker or is_name_declaration(parsed.png_name) or layer.width <= 0 or layer.height <= 0:
            continue
        names.add(parsed.png_name)
    return names


def art_source_names(app_dir: str | Path, cmd: list[str], cwd: str | Path) -> set[str] | None:
    """The sprite names the pack command `cmd` (detect_pack_command) can produce from the sources on disk;
    None when that cannot be told (the SDK's octpack-pack, an unreadable PSD)."""
    app_dir = Path(app_dir)
    if "octpack-pack" in cmd:
        return None
    if str(BUILD_PIPELINE_PY) in cmd:
        ws = Path(cmd[cmd.index("--workspace") + 1])
        ws = ws if ws.is_absolute() else Path(cwd) / ws
        return {p.stem for p in (ws / "art").glob("*.png")}
    if "--export" in cmd:
        names: set[str] = set()
        for psd in sorted((app_dir / "art").glob("*assets*.psd")):
            got = _psd_sprite_names(psd)
            if got is None:
                return None
            names |= got
        return names
    return {p.stem for p in (app_dir / "art" / "exported").glob("*.png")}


def lost_sprites(app_dir: str | Path, cmd: list[str], cwd: str | Path) -> list[str]:
    """Sprites packed in the app today that the repack's sources cannot produce: the repack would drop them
    (an app delivered without its art sources: only art/packed + index.bin; the scaffold shape would re-export
    the template's art/assets.psd over the real art)."""
    sources = art_source_names(app_dir, cmd, cwd)
    if sources is None:
        return []
    ws = _workspace_of(cmd, cwd)
    fonts = font_sources(app_dir, ws)
    # the manifest pack carries an extraction's glyph records; the other packers only rebuild from a .fnt
    carried = carried_glyphs(ws)
    lost = []
    for n in packed_sprite_names(app_dir) - sources:
        if _GLYPH_RE.match(n) and (n.rsplit("_", 1)[0] in fonts or n in carried):
            continue
        lost.append(n)
    return sorted(lost)


def ensure_art_fonts(app_dir: str | Path) -> int:
    """pack.py exports BMFont glyphs only from <art-dir>/fonts/; scaffolded apps keep font_*.fnt and their
    atlas PNGs in art/. Copy them over (like build_pipeline does for assets_<game>/fonts) so a direct
    pack.py repack keeps the glyphs - without them every OCT_label_set draws nothing. Returns files copied."""
    art = Path(app_dir) / "art"
    files = sorted(p for p in art.glob("font_*") if p.is_file() and p.suffix.lower() in (".fnt", ".png"))
    if not files:
        return 0
    dst = art / "fonts"
    dst.mkdir(exist_ok=True)
    n = 0
    for p in files:
        target = dst / p.name
        if not target.is_file() or target.read_bytes() != p.read_bytes():
            shutil.copy2(p, target)
            n += 1
    return n


def default_oct_path(app_dir: str | Path) -> Path:
    """Where build_device writes the deliverable: <workspace>/dist/<app>.oct
    (never <app>/<app>.oct: the standalone simulator writes none, an older baked-in one rewrote it on every launch)."""
    app_dir = Path(app_dir).resolve()
    return app_dir.parent / "dist" / f"{_app_name(app_dir)}.oct"


def build_device_command(app_dir: Path, octavios: str | None = None,
                         out: str | Path | None = None,
                         builder: str = "auto", no_uv: bool = False) -> list[str]:
    """Platform-specific invocation of scripts/build_device.(ps1|sh).

    The device stage deliberately INVOKES the build_device script instead of
    reimplementing it: that script is the single source of truth for the
    octpack-build / python-builder choice, the ARM build and the .oct
    verification — duplicating that logic here would inevitably drift.
    `no_uv` (-NoUv / --no-uv): never start uv (python builder + the local
    header check) - set when this interpreter is a Store Python.
    """
    if os.name == "nt":
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
               "-File", str(SCRIPT_DIR / "build_device.ps1"),
               "-AppDir", str(app_dir)]
        if octavios:
            cmd += ["-OctaviOS", octavios]
        if out:
            cmd += ["-Out", str(out)]
        if builder != "auto":
            cmd += ["-Builder", builder]
        if no_uv:
            cmd += ["-NoUv"]
    else:
        cmd = ["bash", str(SCRIPT_DIR / "build_device.sh"),
               "--app-dir", str(app_dir)]
        if octavios:
            cmd += ["--octavios", octavios]
        if out:
            cmd += ["--out", str(out)]
        if builder != "auto":
            cmd += ["--builder", builder]
        if no_uv:
            cmd += ["--no-uv"]
    return cmd


def uv_env_for(app_dir: str | Path) -> str:
    """octpacker's environment for uv: UV_PROJECT_ENVIRONMENT when set, else <workspace>/.uv_octpack_venv - never
    the SDK tree (uv would create octavios/octpacker/.venv). build_device.ps1/.sh use the same default."""
    return os.environ.get("UV_PROJECT_ENVIRONMENT") or str(Path(app_dir).resolve().parent / ".uv_octpack_venv")


def _run(cmd: list[str], *, cwd: Path | None = None) -> int:
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    # our own lines first: the child writes straight to the same console/pipe, and a block-buffered stdout (a pipe,
    # an agent's log) would otherwise print this stage's header after the child's output
    sys.stdout.flush()
    sys.stderr.flush()
    return subprocess.run(cmd, cwd=cwd, text=True).returncode


def _cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="repack_app",
        description="Repack an app's beta container, bump the version (the minor by "
                    "default, patch reset to 0; --bump patch for the patch), and rebuild "
                    "the device .oct - in one command.")
    parser.add_argument("--app-dir", required=True,
                        help="app_<game> folder to repack")
    parser.add_argument("--manifest", default="auto",
                        help="path to plans/<game>_assets.json "
                             "(default: auto-detect plans/*_assets.json)")
    parser.add_argument("--icon", default="auto",
                        help="launcher icon PNG (default: an extracted game's assets_<game>/icon.png, else "
                             "art/icon.png)")
    parser.add_argument("--skip-device", action="store_true",
                        help="stop after repack + version bump (no ARM build, "
                             "no new .oct)")
    parser.add_argument("--octavios", default=None,
                        help="optional octavios SDK checkout: forwarded to build_device (default there: the "
                             "plugin's public game API, no checkout needed) and used for octpack-pack, which only "
                             "apps with art/octpack.json need (internal SDK only; the plugin's api/ has no octpacker)")
    parser.add_argument("--out", default=None,
                        help="device .oct path (default: <app-dir>/../dist/<app>.oct)")
    parser.add_argument("--bump", choices=("minor", "patch"), default="minor",
                        help="which version field to bump (default minor, patch reset to 0: the release rule; the "
                             ".oct always carries exactly the code's version)")
    parser.add_argument("--allow-asset-loss", action="store_true",
                        help="repack even when the sources on disk cannot produce every sprite packed today (those "
                             "sprites disappear from the game); without it such a repack is refused")
    parser.add_argument("--builder", default="auto",
                        choices=("auto", "octpack", "python"),
                        help="forwarded to build_device (default: octpack-build "
                             "when available, else the python builder)")
    args = parser.parse_args(argv)

    app_dir = Path(args.app_dir)
    if not app_dir.is_dir():
        print(f"ERROR: app folder not found: {app_dir}", file=sys.stderr)
        return 2
    app_dir = app_dir.resolve()

    # --- 1. repack the beta container (canonical invocation from disk) -----
    try:
        pack_cmd, cwd = detect_pack_command(app_dir, args.manifest, args.icon, args.octavios)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    lost = lost_sprites(app_dir, pack_cmd, cwd)
    if lost and not args.allow_asset_loss:
        app = _app_name(app_dir)
        game = app[4:] if app.startswith("app_") else app
        root = app_dir.parent
        shown = ", ".join(lost[:10]) + (f" ... (+{len(lost) - 10})" if len(lost) > 10 else "")
        template = (" (it would re-export the template's art/assets.psd over the real art)"
                    if "--export" in pack_cmd else "")
        print(f"ERROR: nothing repacked - {len(lost)} sprite(s) packed in this app have no art source here and "
              f"would disappear: {shown}. The app holds only its packed art{template}. Extract it first, then "
              f"repack (the manifest pack then rebuilds every sprite from the extracted PNGs):\n"
              f"  python {SCRIPT_DIR / 'extract_art.py'} --app-dir {app_dir} --out {root / ('assets_' + game)} "
              f"--manifest {root / 'plans' / (game + '_assets.json')}\n"
              f"  python {SCRIPT_DIR / 'repack_app.py'} --app-dir {app_dir}\n"
              f"{_old_extraction_hint(lost, _workspace_of(pack_cmd, cwd))}"
              f"(--allow-asset-loss repacks anyway and drops them)", file=sys.stderr)
        return 2
    if lost:
        print(f"WARNING: --allow-asset-loss: {len(lost)} packed sprite(s) have no source and are dropped: "
              f"{', '.join(lost[:10])}", file=sys.stderr)
    official = "octpack-pack" in pack_cmd
    os.environ["UV_PROJECT_ENVIRONMENT"] = uv_env_for(app_dir)   # inherited by octpack-pack and build_device
    packer = "octpack-pack (official PSD workflow, art/octpack.json)" if official else (
        Path(pack_cmd[1]).name if len(pack_cmd) > 1 else "packer")
    if official and (args.manifest != "auto" or args.icon != "auto"):
        print("NOTE: --manifest/--icon are ignored: art/octpack.json and its PSDs/!pack.txt define this app's pack")
    if packer == "pack.py" and ensure_art_fonts(app_dir):
        print("==> Staged art/font_* into art/fonts/ (pack.py exports glyphs from there)")
    if not official:
        icon_used = pack_cmd[pack_cmd.index("--icon") + 1] if "--icon" in pack_cmd else None
        print(f"==> Launcher icon: {icon_used or 'none given (the packer picks or keeps its default)'}")
    print(f"==> Repacking beta container ({packer})")
    rc = _run(pack_cmd, cwd=cwd)
    if rc != 0:
        print(f"ERROR: asset repack failed ({packer} exit {rc})", file=sys.stderr)
        return rc or 1

    # --- 2. version bump (minor by default: every new device .oct gets a new, exact version) ------
    app_h = app_dir / "src" / "app.h"
    try:
        new_version = bump_version(app_h, args.bump)
    except (OSError, ValueError) as e:
        print(f"ERROR: version bump failed: {e}", file=sys.stderr)
        return 2
    print(f"==> APP_VERSION bumped to {_version_str(new_version)} "
          f"({'src/app_metadata.h' if (app_h.parent / 'app_metadata.h').is_file() else app_h})")
    if (new_version >> 24) & 0xFF != 1:
        print(f"NOTE: this app keeps a legacy integer APP_VERSION (a plain counter, no major.minor.patch): it went "
              f"+1 to {new_version}, the cube's update check still sees a new version. Moving it to "
              f"APP_VERSION_MAJOR/MINOR/PATCH + OCT_APP_SEMVER is a structural change (ask first); a fork "
              f"(scripts/fork_app) converts it")

    # --- 3. device build (octpack-build or python builder + verification) ---
    oct_path = Path(args.out).resolve() if args.out else default_oct_path(app_dir)
    if args.skip_device:
        print()
        print("REPACK DONE (device build skipped):")
        print(f"  APP_VERSION = {_version_str(new_version)}")
        print(f"  no new .oct was built - any existing {oct_path} is STALE; "
              f"re-run without --skip-device to ship.")
        return 0

    no_uv = packaged_python()
    if no_uv:
        if args.builder == "octpack":
            print(f"ERROR: --builder octpack runs through uv, but {STORE_PYTHON_NOTE}. Build from a normal "
                  f"PowerShell: scripts\\build_device.ps1 -AppDir {app_dir} -Builder octpack", file=sys.stderr)
            return 2
        print(f"NOTE: {STORE_PYTHON_NOTE}: the device build runs without uv (-NoUv: python builder + local "
              f".oct header check)")
    print("==> Device build (scripts/build_device)")
    rc = _run(build_device_command(app_dir, args.octavios, oct_path, args.builder, no_uv=no_uv))
    if rc != 0:
        print(f"ERROR: device build failed (exit {rc})", file=sys.stderr)
        return rc or 1

    print()
    print("REPACK COMPLETE:")
    print(f"  {oct_path}")
    print(f"  APP_VERSION = {_version_str(new_version)}")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)     # stages print in order when piped into a log
        except (AttributeError, ValueError):
            pass
    return _cli(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
