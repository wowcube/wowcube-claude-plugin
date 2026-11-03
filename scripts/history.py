#!/usr/bin/env python3
"""Snapshots before every change to a game, and "undo the last change" (cube_orchestrator, "History and undo").

    python history.py snapshot --workspace <ws> --game <game> --label "<what changes>" [--request "<user's words>"] [--assets]
    python history.py list     --workspace <ws> --game <game> [--json]
    python history.py restore  --workspace <ws> --game <game> [--n <snapshot number>]

`snapshot` runs BEFORE a change (a prompt's coder run, a mod, a tunable change). It copies the small things
that define the game into `<ws>/.history/<nnn>_<label>/`:
  - `app_<game>/src/` (the code, the tunables block, app_metadata.h);
  - `plans/<game>_gdd.md`, `plans/<game>_prompts.md`, `plans/<game>_assets.json` (when present);
  - the run-state fields of `context/<game>_context.json` that a change moves (prompt results, cuts, ...);
  - with `--assets` (a picture or sound change): `assets_<game>/art/`, `assets_<game>/raw/`,
    `assets_<game>/icon.png`, `app_<game>/art/icon.png` and `app_<game>/sound/`.
Never build output, packed files or check frames. It records the snapshot in the context's `history` list.

`restore` ("undo the last change") restores the latest change snapshot of the game that is not undone yet
(or `--n`). First it snapshots the current state (`pre_undo`, so the undo can itself be undone), then it
puts the snapshot's files back: folders are mirrored (files the change added are removed; they stay in the
`pre_undo` snapshot), plan files that did not exist then are removed. The version and APP_GUID1 are NOT
rolled back: the current values are written into the restored headers, so the next build still bumps the
minor version from the newest one (the cube compares versions exactly; an older number would not install).
After a restore the orchestrator rebuilds and checks as for any change (plugin build, the visual gate,
`build_pipeline.py pack` when `--assets` was restored, `repack_app.py` for the new device .oct).

Exit: 0 done; 1 bad arguments or nothing to restore; 2 a file could not be read or written.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shutil
import sys
from pathlib import Path

HISTORY_DIR = ".history"
CONTEXT_FIELDS = ("last_completed_prompt", "total_prompts", "prompts", "cuts", "accepted_majors",
                  "accepted_minors", "not_checked_visually", "balance_passes")
_IDENTITY_RES = [re.compile(r"^(\s*#\s*define\s+APP_VERSION_(?:MAJOR|MINOR|PATCH)\s+)(\d+)", re.M),
                 re.compile(r"^(\s*#\s*define\s+APP_VERSION\s+)(\d+)\b", re.M),
                 re.compile(r"^(\s*#\s*define\s+APP_VERSION\s+OCT_APP_SEMVER\s*\()([^)]*)(\))", re.M),
                 re.compile(r"^(\s*#\s*define\s+APP_GUID1\s+)(\S+)", re.M)]


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", text.strip().lower()).strip("_")
    return (s or "change")[:40]


class Paths:
    def __init__(self, ws: Path, game: str):
        self.ws, self.game = ws, game
        self.app = ws / f"app_{game}"
        self.assets = ws / f"assets_{game}"
        self.context = ws / "context" / f"{game}_context.json"
        self.history = ws / HISTORY_DIR

    def dirs(self, with_assets: bool) -> dict[str, Path]:
        d = {"src": self.app / "src"}
        if with_assets:
            d.update({"assets_art": self.assets / "art", "assets_raw": self.assets / "raw",
                      "app_sound": self.app / "sound"})
        return d

    def files(self, with_assets: bool) -> dict[str, Path]:
        f = {f"plans/{self.game}_{n}": self.ws / "plans" / f"{self.game}_{n}"
             for n in ("gdd.md", "prompts.md", "assets.json")}
        if with_assets:
            f.update({"assets_icon": self.assets / "icon.png", "app_icon": self.app / "art" / "icon.png"})
        return f


def _read_context(p: Paths) -> dict:
    if not p.context.is_file():
        return {}
    return json.loads(p.context.read_text(encoding="utf-8-sig"))


def _write_context(p: Paths, ctx: dict) -> None:
    p.context.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.context.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ctx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p.context)


def _snapshots(p: Paths) -> list[tuple[Path, dict]]:
    out = []
    if p.history.is_dir():
        for d in sorted(p.history.iterdir()):
            meta = d / "snapshot.json"
            if d.is_dir() and meta.is_file():
                data = json.loads(meta.read_text(encoding="utf-8"))
                if data.get("game") == p.game:
                    out.append((d, data))
    return out


def _next_number(p: Paths) -> int:
    nums = [int(m.group(1)) for d in (p.history.iterdir() if p.history.is_dir() else [])
            if (m := re.match(r"(\d+)_", d.name))]
    return max(nums, default=0) + 1


def snapshot(ws: Path, game: str, label: str, request: str | None = None, with_assets: bool = False,
             kind: str = "change", undoes: int | None = None) -> tuple[int, Path]:
    p = Paths(ws, game)
    if not (p.app / "src").is_dir():
        raise FileNotFoundError(f"{p.app / 'src'} does not exist")
    n = _next_number(p)
    dest = p.history / f"{n:03d}_{_slug(label)}"
    dest.mkdir(parents=True)
    copied_dirs, present, absent = {}, [], []
    for key, src in p.dirs(with_assets).items():
        if src.is_dir():
            shutil.copytree(src, dest / "dirs" / key)
            copied_dirs[key] = True
        else:
            copied_dirs[key] = False
    for key, src in p.files(with_assets).items():
        if src.is_file():
            target = dest / "files" / key.replace("/", "__")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            present.append(key)
        else:
            absent.append(key)
    ctx = _read_context(p)
    fields = {k: ctx[k] for k in CONTEXT_FIELDS if k in ctx}
    meta = {"n": n, "game": game, "label": label, "kind": kind, "date": _now(), "request": request,
            "assets": with_assets, "dirs": copied_dirs, "files_present": present, "files_absent": absent,
            "context_fields": fields, "context_absent": [k for k in CONTEXT_FIELDS if k not in ctx],
            "undone": None}
    if undoes is not None:
        meta["undoes"] = undoes
    (dest / "snapshot.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if p.context.is_file():
        ctx.setdefault("history", []).append({"n": n, "label": label, "kind": kind, "date": meta["date"],
                                              "dir": f"{HISTORY_DIR}/{dest.name}", "assets": with_assets,
                                              "request": request})
        _write_context(p, ctx)
    return n, dest


def _carry_identity(restored: str, current: str) -> str:
    """Write the current version numbers and APP_GUID1 into the restored header text."""
    for rx in _IDENTITY_RES:
        cur = [m.groups() for m in rx.finditer(current)]
        by_prefix = {g[0].strip(): g for g in cur}

        def sub(m, by_prefix=by_prefix):
            g = by_prefix.get(m.group(1).strip())
            if g is None:
                return m.group(0)
            return m.group(1) + g[1] + (g[2] if len(g) > 2 else "")
        restored = rx.sub(sub, restored)
    return restored


def _mirror(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def restore(ws: Path, game: str, n: int | None = None) -> dict:
    p = Paths(ws, game)
    snaps = _snapshots(p)
    if n is None:
        candidates = [(d, m) for d, m in snaps if m.get("kind") == "change" and not m.get("undone")]
    else:
        candidates = [(d, m) for d, m in snaps if m["n"] == n]
    if not candidates:
        raise LookupError("nothing to undo: no change snapshot of this game is left" if n is None
                          else f"no snapshot {n} for game {game}")
    d, meta = candidates[-1]
    with_assets = bool(meta.get("assets"))
    # the identity headers as they are now (version, GUID): carried into the restored code
    current_headers = {f.name: f.read_text(encoding="utf-8-sig") for f in (p.app / "src").glob("*.h")}
    pre_n, pre_dir = snapshot(ws, game, f"before undo of {meta['n']}", with_assets=with_assets, kind="pre_undo",
                              undoes=meta["n"])
    for key, target in p.dirs(with_assets).items():
        saved = d / "dirs" / key
        if meta["dirs"].get(key) and saved.is_dir():
            _mirror(saved, target)
        elif target.is_dir() and key != "src":
            shutil.rmtree(target)          # it did not exist then; the pre_undo snapshot keeps it
    for key, target in p.files(with_assets).items():
        saved = d / "files" / key.replace("/", "__")
        if key in meta.get("files_present", []) and saved.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(saved, target)
        elif key in meta.get("files_absent", []) and target.is_file():
            target.unlink()
    for name, cur in current_headers.items():
        f = p.app / "src" / name
        if f.is_file():
            text = f.read_text(encoding="utf-8-sig")
            new = _carry_identity(text, cur)
            if new != text:
                f.write_text(new, encoding="utf-8")
    ctx = _read_context(p)
    if ctx:
        for k, v in meta.get("context_fields", {}).items():
            ctx[k] = v
        for k in meta.get("context_absent", []):
            ctx.pop(k, None)
        for h in ctx.get("history", []):
            if h.get("n") == meta["n"]:
                h["undone"] = _now()
        ctx.setdefault("history", []).append({"n": None, "kind": "undo", "date": _now(), "restored": meta["n"],
                                              "label": meta["label"], "pre_undo": pre_n,
                                              "assets": with_assets})
        _write_context(p, ctx)
    meta["undone"] = _now()
    (d / "snapshot.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"restored": meta["n"], "label": meta["label"], "request": meta.get("request"), "assets": with_assets,
            "pre_undo": pre_n, "pre_undo_dir": str(pre_dir)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("snapshot", "list", "restore"):
        s = sub.add_parser(name)
        s.add_argument("--workspace", default=".")
        s.add_argument("--game", required=True)
        if name == "snapshot":
            s.add_argument("--label", required=True)
            s.add_argument("--request")
            s.add_argument("--assets", action="store_true")
        if name == "list":
            s.add_argument("--json", action="store_true")
        if name == "restore":
            s.add_argument("--n", type=int)
    a = ap.parse_args(argv)
    ws = Path(a.workspace)
    try:
        if a.cmd == "snapshot":
            n, dest = snapshot(ws, a.game, a.label, a.request, a.assets)
            print(f"snapshot {n}: {dest}")
        elif a.cmd == "list":
            rows = [m for _, m in _snapshots(Paths(ws, a.game))]
            if a.json:
                print(json.dumps([{k: m.get(k) for k in ("n", "label", "kind", "date", "request", "assets", "undone")}
                                  for m in rows]))
            else:
                for m in rows:
                    print(f"{m['n']:3d}  {m['kind']:8s}  {m['date']}  {m['label']}"
                          + ("  (undone)" if m.get("undone") else ""))
        else:
            r = restore(ws, a.game, a.n)
            print(f"restored snapshot {r['restored']} ({r['label']}); the state before the undo is snapshot "
                  f"{r['pre_undo']}. Version and APP_GUID1 kept; now rebuild and run the checks"
                  + (" (assets restored: pack first)" if r["assets"] else ""))
    except LookupError as e:
        print(str(e), file=sys.stderr)
        return 1
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
