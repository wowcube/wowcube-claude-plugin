#!/usr/bin/env python3
"""Fork a working WowCube app into a NEW game: a copy with its own name, identity and version.

    python scripts/fork_app.py --source <path>/app_<old> --name <new> [--workspace <ws>] [--title "New Title"]
    (Windows: scripts/fork_app.ps1 -Source ... -Name ...; Linux/macOS: scripts/fork_app.sh --source ... --name ...)

What it does (the same rename rules scripts/new_app.ps1 / new_app.sh apply to the template):
  1. copies <source> to <ws>/app_<new> (default <ws>: the folder that holds the source), without build output
     (bin/, out/, build-sim/, x64/, .vs/, *.oct, *.log) and without the source's pack record
     (.pack_inputs.json names the source's workspace; the fork's first pack writes its own);
  2. renames every file whose name carries `app_<old>` (the .target marker, the game header, the ids headers);
  3. replaces `app_<old>` in every text file (.h .c .cpp .hpp .txt .json .md .cmake): the #include lines in
     src/app.h and the game header, APP_DIR, CMake names;
  4. gives the copy a new identity in src/app_metadata.h (or src/app.h in an older layout): a fresh random
     APP_GUID1, the new APP_TITLE and version 0.0.0, so the fork's first repack (scripts/repack_app.py bumps the
     minor) ships 0.1.0, its first version on any cube. A legacy integer `#define APP_VERSION <n>` (no
     major/minor/patch) becomes APP_VERSION_MAJOR/MINOR/PATCH 0.0.0 + OCT_APP_SEMVER (a new game has no installed
     predecessor whose counter it would have to exceed); the version comment of the source's app_metadata.h is
     brought to the template's current wording;
  5. when the source has a workspace next to it (assets_<old>/, plans/<old>_*), copies it as assets_<new>/ and
     plans/<new>_* (the manifest's "game" set to <new>), so the art, style lock and manifest carry over.
The source folder is never changed. The target must not exist (never overwrites an app folder).

Exit 0 = forked; prints the identity block for the context's `import` record (--json: as JSON).
Exit 1 = the source is not an app folder, the target exists, or a step failed (nothing half-done is left
behind: the new folders are removed again).

Test-hook macros (`<GAME>_DEBUG_AUTOPLAY`, ...) keep the source's prefix: they are local to the code and the
context records their names (`test_hooks`), so renaming them is an ordinary code change, not part of a fork.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import sys
from pathlib import Path

# files whose text may name the app: sources, build files and the build scripts (.cmd/.bat set APP_NAME=app_<old>)
TEXT_EXTS = {".h", ".c", ".cpp", ".hpp", ".txt", ".json", ".md", ".cmake",
             ".cmd", ".bat", ".ps1", ".psm1", ".sh", ".py", ".mk", ".ini", ".cfg", ".yml", ".yaml"}
SKIP_DIRS = {"bin", "out", "build-sim", "x64", ".vs", "__pycache__"}
SKIP_FILES = {".pack_inputs.json", "sim.exe", "sim.pdb", "sim_user.cfg"}
SKIP_EXTS = {".oct", ".log"}
APP_RE = re.compile(r"^app_[A-Za-z0-9_]+$")
FORK_VERSION = (0, 0, 0)       # the first repack bumps the minor: the fork ships 0.1.0
REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_METADATA = REPO_ROOT / "templates" / "app_ai_template" / "src" / "app_metadata.h"


def _app_name(app_dir: Path) -> str:
    targets = sorted(app_dir.glob("*.target"))
    if len(targets) != 1:
        raise ValueError(f"{app_dir} needs exactly one <app>.target marker, found {len(targets)}")
    return targets[0].stem


def _ignore(_dir: str, names: list[str]) -> set[str]:
    return {n for n in names
            if n in SKIP_DIRS or n in SKIP_FILES or Path(n).suffix.lower() in SKIP_EXTS}


def _read(p: Path) -> tuple[str, bool]:
    raw = p.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig"), bom


def _write(p: Path, text: str, bom: bool) -> None:
    p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))


def _read_any(p: Path) -> tuple[str, str]:
    """A text file in whatever encoding a build script uses: (text, codec to write it back with). UTF-8 (with or
    without BOM), UTF-16 with a BOM (Windows PowerShell), else latin-1, which round-trips any byte."""
    raw = p.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16"), "utf-16"
    try:
        return raw.decode("utf-8-sig"), ("utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1"), "latin-1"


def _write_any(p: Path, text: str, codec: str) -> None:
    p.write_bytes(text.encode(codec))


def token_re(old_app: str) -> re.Pattern[str]:
    """`app_<old>` as a name: also inside app_<old>_ids / app_<old>.h, never a longer word (app_<old>2)."""
    return re.compile(re.escape(old_app) + r"(?![A-Za-z0-9])")


def rename_tree(app_dir: Path, old_app: str, new_app: str) -> tuple[int, int]:
    """Steps 2-3: file names and text references. Returns (files renamed, files patched)."""
    tok = token_re(old_app)
    renamed = patched = 0
    for root, _dirs, files in os.walk(app_dir, topdown=False):
        for n in files:
            if tok.search(n):
                os.rename(os.path.join(root, n), os.path.join(root, tok.sub(new_app, n)))
                renamed += 1
    for root, _dirs, files in os.walk(app_dir):
        for n in files:
            p = Path(root) / n
            if p.suffix.lower() not in TEXT_EXTS:
                continue
            text, codec = _read_any(p)
            new = tok.sub(new_app, text)
            if new != text:
                _write_any(p, new, codec)
                patched += 1
    return renamed, patched


_GUID_RE = re.compile(r"(?m)^([ \t]*#[ \t]*define[ \t]+APP_GUID1[ \t]+)(0x[0-9A-Fa-f]+)([uUlL]*)")
_TITLE_RE = re.compile(r'(?m)^([ \t]*#[ \t]*define[ \t]+APP_TITLE[ \t]+)"[^"\r\n]*"')
_FIELD_RE = {k: re.compile(rf"(?m)^([ \t]*#[ \t]*define[ \t]+APP_VERSION_{k}[ \t]+)(\d+)")
             for k in ("MAJOR", "MINOR", "PATCH")}
_SEMVER_RE = re.compile(r"(?m)^([ \t]*#[ \t]*define[ \t]+APP_VERSION[ \t]+OCT_APP_SEMVER[ \t]*\()[^)]*(\))")
_LEGACY_RE = re.compile(r"(?m)^[ \t]*#[ \t]*define[ \t]+APP_VERSION[ \t]+\d+\b[^\r\n]*")
# the "// Version:" comment block of app_metadata.h (the run of // lines that starts with it)
_VERSION_COMMENT_RE = re.compile(r"(?m)^// Version:[^\r\n]*(?:\r?\n//[^\r\n]*)*")


def template_version_comment() -> str | None:
    """The template's current "// Version: ..." comment block (src/app_metadata.h)."""
    try:
        m = _VERSION_COMMENT_RE.search(TEMPLATE_METADATA.read_text(encoding="utf-8-sig").replace("\r\n", "\n"))
    except OSError:
        return None
    return m.group(0) if m else None


def refresh_version_comment(text: str) -> str:
    """Bring a copied app_metadata.h's version comment to the template's wording (an older one still says
    "scripts/repack_app.py bumps APP_VERSION_PATCH"); line endings follow the file."""
    new = template_version_comment()
    m = _VERSION_COMMENT_RE.search(text)
    if not new or not m or m.group(0).replace("\r\n", "\n") == new:
        return text
    nl = "\r\n" if "\r\n" in m.group(0) else "\n"
    return text[:m.start()] + new.replace("\n", nl) + text[m.end():]


def legacy_to_semver(text: str, version: tuple[int, int, int]) -> str | None:
    """Replace a legacy integer `#define APP_VERSION <n>` with the semver fields (None when there is none)."""
    m = _LEGACY_RE.search(text)
    if not m:
        return None
    nl = "\r\n" if "\r\n" in text else "\n"
    block = nl.join([
        '#include "oct_app_version.h"   // OCT_APP_SEMVER (engine); fork_app replaced the legacy integer APP_VERSION',
        f"#define APP_VERSION_MAJOR {version[0]}",
        f"#define APP_VERSION_MINOR {version[1]}",
        f"#define APP_VERSION_PATCH {version[2]}",
        "#define APP_VERSION OCT_APP_SEMVER(APP_VERSION_MAJOR, APP_VERSION_MINOR, APP_VERSION_PATCH)"])
    return text[:m.start()] + block + text[m.end():]


def new_identity(app_dir: Path, title: str, old_guid: int | None = None) -> dict:
    """Step 4: a fresh APP_GUID1, the title and version 0.0.0 (the first repack ships 0.1.0), in the file that
    defines them; a legacy integer APP_VERSION becomes the semver fields; the version comment is refreshed."""
    src = app_dir / "src"
    files = [p for p in (src / "app_metadata.h", src / "app.h") if p.is_file()]
    guid_file = next((p for p in files if _GUID_RE.search(_read(p)[0])), None)
    if guid_file is None:
        raise ValueError(f"no '#define APP_GUID1 0x...' in {', '.join(str(p) for p in files) or src}")
    guid = 0
    while guid == 0 or guid == old_guid:
        guid = secrets.randbits(64)
    text, bom = _read(guid_file)
    text = _GUID_RE.sub(lambda m: f"{m.group(1)}0x{guid:016X}{m.group(3)}", text, count=1)
    if _TITLE_RE.search(text):
        text = _TITLE_RE.sub(lambda m: f'{m.group(1)}"{title}"', text, count=1)
    else:
        text = text.rstrip() + f'\n#define APP_TITLE "{title}"\n'
    version_set = False
    legacy = False
    if all(r.search(text) for r in _FIELD_RE.values()):
        for k, v in zip(("MAJOR", "MINOR", "PATCH"), FORK_VERSION):
            text = _FIELD_RE[k].sub(lambda m, v=v: f"{m.group(1)}{v}", text, count=1)
        version_set = True
    elif _SEMVER_RE.search(text):
        text = _SEMVER_RE.sub(lambda m: f"{m.group(1)}{', '.join(map(str, FORK_VERSION))}{m.group(2)}", text, count=1)
        version_set = True
    else:
        converted = legacy_to_semver(text, FORK_VERSION)
        if converted is not None:
            text, version_set, legacy = converted, True, True
    if guid_file.name == "app_metadata.h":
        text = refresh_version_comment(text)
    _write(guid_file, text, bom)
    if not version_set:
        # the version may sit in the other file (app.h) of an older layout
        for p in files:
            if p == guid_file:
                continue
            t, b = _read(p)
            if all(r.search(t) for r in _FIELD_RE.values()):
                for k, v in zip(("MAJOR", "MINOR", "PATCH"), FORK_VERSION):
                    t = _FIELD_RE[k].sub(lambda m, v=v: f"{m.group(1)}{v}", t, count=1)
                version_set = True
            elif _SEMVER_RE.search(t):
                t = _SEMVER_RE.sub(lambda m: f"{m.group(1)}{', '.join(map(str, FORK_VERSION))}{m.group(2)}", t, count=1)
                version_set = True
            else:
                converted = legacy_to_semver(t, FORK_VERSION)
                if converted is not None:
                    t, version_set, legacy = converted, True, True
            if version_set:
                if p.name == "app_metadata.h":
                    t = refresh_version_comment(t)
                _write(p, t, b)
                break
    return {"guid1": f"0x{guid:016X}", "title": title,
            "version": ".".join(map(str, FORK_VERSION)) if version_set else None,
            "version_converted": legacy,
            "file": guid_file.relative_to(app_dir).as_posix()}


def read_guid(app_dir: Path) -> int | None:
    for p in (app_dir / "src" / "app_metadata.h", app_dir / "src" / "app.h"):
        if p.is_file():
            m = _GUID_RE.search(_read(p)[0])
            if m:
                return int(m.group(2), 16)
    return None


def copy_workspace(src_root: Path, dst_root: Path, old_game: str, new_game: str) -> list[str]:
    """Step 5: assets_<old>/ -> assets_<new>/ and plans/<old>_* -> plans/<new>_* when they exist and the
    targets do not. Returns what was copied (relative to dst_root)."""
    done = []
    ws_src, ws_dst = src_root / f"assets_{old_game}", dst_root / f"assets_{new_game}"
    if ws_src.is_dir() and not ws_dst.exists():
        shutil.copytree(ws_src, ws_dst, ignore=shutil.ignore_patterns("__pycache__"))
        done.append(ws_dst.name + "/")
    plans_src, plans_dst = src_root / "plans", dst_root / "plans"
    if plans_src.is_dir():
        for p in sorted(plans_src.glob(f"{old_game}_*")):
            if not p.is_file():
                continue
            q = plans_dst / (new_game + p.name[len(old_game):])
            if q.exists():
                continue
            plans_dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, q)
            if q.name == f"{new_game}_assets.json":
                try:
                    data = json.loads(q.read_text(encoding="utf-8-sig"))
                    data["game"] = new_game
                    q.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
                except (OSError, ValueError):
                    pass
            done.append(f"plans/{q.name}")
    return done


def fork(source: Path, name: str, workspace: Path | None = None, title: str | None = None) -> dict:
    source = Path(source).resolve()
    if not source.is_dir():
        raise ValueError(f"source app folder not found: {source}")
    old_app = _app_name(source)
    new_app = name if name.startswith("app_") else f"app_{name}"
    if not APP_RE.match(new_app):
        raise ValueError(f"invalid app name {new_app!r} (expected app_<letters, digits, _>)")
    if new_app == old_app:
        raise ValueError(f"the fork needs a new name: {new_app} is the source's own")
    ws = Path(workspace).resolve() if workspace else source.parent
    dest = ws / new_app
    if dest.exists():
        raise ValueError(f"{dest} already exists - a fork never overwrites an app folder; pick another name")
    old_game, new_game = old_app[4:], new_app[4:]
    title = title or " ".join(w[:1].upper() + w[1:] for w in new_game.split("_") if w)
    if len(title.encode("utf-8")) > 79 or '"' in title or "\\" in title:
        raise ValueError("the title must be <= 79 bytes, without quotes or backslashes")
    old_guid = read_guid(source)
    created: list[Path] = []
    new_ws = ws / f"assets_{new_game}"
    if not new_ws.exists():
        created.append(new_ws)              # removed again if the fork fails after copying it
    try:
        ws.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, dest, ignore=_ignore)
        created.append(dest)
        renamed, patched = rename_tree(dest, old_app, new_app)
        ident = new_identity(dest, title, old_guid)
        left = [str(p.relative_to(dest)) for p in dest.rglob("*")
                if p.is_file() and p.suffix.lower() in TEXT_EXTS and token_re(old_app).search(_read_any(p)[0])]
        if left:
            raise ValueError(f"{old_app} is still named in: {', '.join(left[:5])}")
        _app_name(dest)                       # exactly one marker, with the new name
        copied = copy_workspace(source.parent, ws, old_game, new_game)
    except Exception:
        for p in created:
            shutil.rmtree(p, ignore_errors=True)
        raise
    return {
        "app_dir": dest.as_posix(), "app": new_app, "files_renamed": renamed, "files_patched": patched,
        "version_converted": ident["version_converted"],
        "identity": {"guid1": ident["guid1"], "title": ident["title"], "version": ident["version"],
                     "fork_of": {"app_dir": source.as_posix(), "app": old_app,
                                 "guid1": f"0x{old_guid:016X}" if old_guid is not None else None}},
        "metadata_file": ident["file"], "workspace_copied": copied,
    }


NO_VERSION_NOTE = ("NOT SET (no APP_VERSION define found: add APP_VERSION_MAJOR/MINOR/PATCH 0 0 0 and "
                   "APP_VERSION OCT_APP_SEMVER(...) as in templates/app_ai_template/src/app_metadata.h)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, type=Path, help="the working app folder to fork (app_<old>)")
    ap.add_argument("--name", required=True, help="the new game's name: <new> or app_<new>")
    ap.add_argument("--workspace", type=Path, default=None, help="where app_<new> goes (default: next to the source)")
    ap.add_argument("--title", default=None, help="APP_TITLE of the fork (default: from the name)")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    args = ap.parse_args(argv)
    try:
        r = fork(args.source, args.name, args.workspace, args.title)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(r, indent=1))
        return 0
    i = r["identity"]
    print(f"FORKED {i['fork_of']['app']} -> {r['app_dir']}")
    print(f"  files renamed {r['files_renamed']}, text files patched {r['files_patched']}")
    print(f"  APP_GUID1 {i['guid1']} (source {i['fork_of']['guid1']}), APP_TITLE \"{i['title']}\", "
          f"version {i['version'] or NO_VERSION_NOTE} in {r['metadata_file']}")
    if r["version_converted"]:
        print("  the legacy integer APP_VERSION became APP_VERSION_MAJOR/MINOR/PATCH + OCT_APP_SEMVER")
    if i["version"]:
        ma, mi, _pa = (int(x) for x in i["version"].split("."))
        print(f"  the first repack (scripts/repack_app.py bumps the minor) ships {ma}.{mi + 1}.0")
    if r["workspace_copied"]:
        print(f"  workspace copied: {', '.join(r['workspace_copied'])}")
    print("  next: write the context's import record with this identity, rebuild the plugin "
          "(tools/sim/build_game) and repack (scripts/repack_app.py) before the first run")
    print("  import record identity: " + json.dumps(i))
    return 0


if __name__ == "__main__":
    sys.exit(main())
