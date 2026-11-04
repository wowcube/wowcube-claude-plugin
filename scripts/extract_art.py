#!/usr/bin/env python3
"""Extract the art of a packed WowCube app back into editable PNGs.

A finished game often comes without its art sources: only the app folder
(`index.bin`, `art/packed/*.raw` + `*.pal`, `sound/assets/*.mp3`) or only the
device `.oct`. This tool reads the CURRENT packed format (beta octBmp_t sprites:
palette-coded, or raw (OCT_FLAG_RAW565) in every sub-format the engine draws -
RGB565 plain / RLE / SOFTKEY (keyed), ARGB6666 plain / RLE, MONO1; plain or
alpha-spread `.pal` palettes; `index.bin` = asset id order) and writes:

  <out>/art/<name>.png       one pixel-exact RGBA PNG per sprite: what the engine
                             draws (palette colours / RGB565 / ARGB6666 expanded to
                             8 bits, alpha5 expanded, keyed-out SOFTKEY texels and
                             palette index 0 transparent); the manifest pack
                             (build_pipeline.py pack) reads them here
  <out>/original/<name>.png  the same files, never edited: the reference a mod's
                             carried-through sprites (`"keep": true`) are copied from
                             and compared with
  <out>/original/packed/     every sprite, font glyph and palette record exactly as it
                             was packed (<name>.raw / <name>.pal): the manifest pack
                             writes the record of every sprite whose PNG and manifest
                             entry are unchanged back byte for byte (scripts/carry_art.py)
  <out>/icon.png             the launcher icon (the `ico_idle` sprite), when present: the ONE
                             source of the extracted game's launcher icon (edit or replace it to
                             change the icon); build_pipeline.py pack and repack_app.py take it,
                             never <app>/art/icon.png or a sprite named launcher_icon
  <out>/wav/assets/<n>.mp3   the sounds, only when reading an .oct (an app folder
                             already holds them in sound/assets/)
  <out>/extracted.json       the listing: every asset by id with kind, size, flags,
                             format, palette, pivot, rate, sequence link, the PNG path,
                             a digest of its pixels and its record; what was not
                             extracted (placement maps) and why

With --manifest PATH it also writes a manifest (plans/<game>_assets.json shape)
that covers every extracted sprite with `"keep": true` (carried through
unchanged: art.py process copies the original byte for byte and art.py qa only
checks its size and format), its size, colour tier, flags and background, plus
every sound and the launcher icon tier, and anchors up to three of the kept
sprites as the game's style reference (art.py anchor --originals: <out>/style/;
--no-anchor skips it). That manifest makes the app repackable
by the normal manifest pack without changing anything the mod does not touch:
untouched sprites, the icon and every palette are carried through byte for byte,
the asset ids stay where they were, and a game's own ids header is kept
(cube_orchestrator Mod mode). Only an edited (or added) sprite is encoded anew.

Font glyph sprites (`font_<n>_<5 digits>`) get no PNG: their records are kept and
carried through as they are while the font's `font_<n>.fnt` source (and atlas pages)
is what it was at extraction; the listing's `fonts` records, per font, whether the
pack held it and a digest of its source. An edited or newly added source rebuilds
that font's glyphs only; a font source the pack never held is not packed unless the
manifest names it (`"fonts": ["font_<n>"]`). Maps other than the launcher's `ico`/`ahover` (placement
maps from PSDs) are listed but cannot be rebuilt by the manifest pack. An
unknown raw sub-format is an error (exit 1), never a guessed picture.

    python scripts/extract_art.py --app-dir <ws>/app_<game> --out <ws>/assets_<game> \
        [--manifest <ws>/plans/<game>_assets.json] [--force]
    python scripts/extract_art.py --oct <file.oct> --out <dir> [--manifest <path>] [--game <game>]

Exit 0 = done; 1 = a payload could not be decoded; 2 = bad arguments or an
existing output that --force would overwrite.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pack_beta as pb  # noqa: E402

GLYPH_RE = re.compile(r"^font_[A-Za-z0-9_]*_\d{5}$")
# records the packer generates itself: never manifest sprites
GENERATED = {"zero", "ico_idle"}
LAUNCHER_ICON = "ico_idle"
# where the packed records are kept verbatim, relative to the listing (extracted.json)
RECORDS_SUBDIR = "original/packed"

# bit-stream run-length tables of the palette sprite codec (engine oct_consts.h,
# same tables as scripts/unpack.py)
_LEN_DECODE = [
    1, 15, 1, 3, 1, 2, 1, 5, 1, 15, 1, 4, 1, 2, 1, 7, 1, 15, 1, 3, 1, 2, 1, 6, 1, 15, 1, 4, 1, 2, 1, 11,
    1, 15, 1, 3, 1, 2, 1, 5, 1, 15, 1, 4, 1, 2, 1, 9, 1, 15, 1, 3, 1, 2, 1, 6, 1, 15, 1, 4, 1, 2, 1, 13,
    1, 15, 1, 3, 1, 2, 1, 5, 1, 15, 1, 4, 1, 2, 1, 8, 1, 15, 1, 3, 1, 2, 1, 6, 1, 15, 1, 4, 1, 2, 1, 12,
    1, 15, 1, 3, 1, 2, 1, 5, 1, 15, 1, 4, 1, 2, 1, 10, 1, 15, 1, 3, 1, 2, 1, 6, 1, 15, 1, 4, 1, 2, 1, 14,
]
_LEN_CONSUME = [1, 3, 1, 4, 1, 3, 1, 5, 1, 3, 1, 4, 1, 3, 1, 7] * 8


@dataclass
class Container:
    """One packed app: the index records (id order) and a payload reader."""
    records: list[tuple[int, str]]
    payloads: dict[int, bytes]          # asset id -> payload bytes
    source: str

    def payload(self, asset_id: int) -> bytes:
        return self.payloads[asset_id]


def load_app(app_dir: str | Path) -> Container:
    app_dir = Path(app_dir)
    index = app_dir / "index.bin"
    if not index.is_file():
        raise ValueError(f"{index} not found: not a packed app folder (pack it, or pass --oct)")
    records = pb.read_index_bin(index)
    payloads: dict[int, bytes] = {}
    for i, (kind, name) in enumerate(records):
        p = pb._asset_payload_path(app_dir, kind, name)
        if p.is_file():
            payloads[i] = p.read_bytes()
    return Container(records, payloads, str(app_dir))


def load_oct(oct_path: str | Path) -> Container:
    blob = Path(oct_path).read_bytes()
    header = pb.read_oct_header(blob)
    assets = pb.read_oct_assets(blob, header)
    kinds = {v: k for k, v in pb._KIND_NAMES.items()}
    records, payloads = [], {}
    for a in assets:
        kind = kinds.get(a["kind"], a["kind"])
        records.append((kind, a["name"]))
        o, n = a["offset"], a["size"]
        if 0 < o and o + n <= len(blob):
            payloads[a["id"]] = blob[o:o + n]
    return Container(records, payloads, str(oct_path))


# ── decoding ────────────────────────────────────────────────────────────────

def pal_rgba(words: list[int]) -> np.ndarray:
    """(N, 4) uint8 RGBA of one .pal: plain or alpha-spread (pack_beta.read_pal_rgba),
    8-bit expanded like the engine shows it; index 0 is transparent."""
    out = np.zeros((len(words), 4), dtype=np.uint8)
    spread = pb.pal_is_spread(words)
    for i, w in enumerate(words):
        if i == 0:
            continue
        if spread:
            a5 = (w >> pb.PAL_ALPHA5_SHIFT) & pb.PAL_ALPHA5_MASK
            r5, g6, b5 = (w >> 11) & 0x1F, (w >> 21) & 0x3F, w & 0x1F
            a8 = (a5 << 3) | (a5 >> 2)
        else:
            c = w & 0xFFFF
            r5, g6, b5 = (c >> 11) & 0x1F, (c >> 5) & 0x3F, c & 0x1F
            a8 = 255
        if a8 == 0:
            continue
        out[i] = ((r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2), a8)
    return out


def _words(blob: bytes) -> list[int]:
    n = len(blob) // 4
    return list(struct.unpack_from(f"<{n}I", blob, 0)) if n else []


def decode_palette_indices(blob: bytes) -> np.ndarray:
    """(h, w) palette indices of a palette-encoded sprite (bit-packed symbols with
    run-length codes, one trim byte per row = the row's length in bytes)."""
    w, h = struct.unpack_from("<hh", blob, 36)
    compression, = struct.unpack_from("<I", blob, 32)
    bits = compression & 0xFF
    if w <= 0 or h <= 0 or not bits:
        raise ValueError(f"not a palette sprite (w={w}, h={h}, symbol bits={bits})")
    trims = blob[pb.BMP_SIZE:pb.BMP_SIZE + h]
    data_start = pb.BMP_SIZE + ((h + 3) // 4) * 4
    stream = blob[data_start:] + b"\0" * 8
    nwords = len(stream) // 4
    words = struct.unpack_from(f"<{nwords}I", stream, 0)
    mask = (1 << bits) - 1
    out = np.zeros((h, w), dtype=np.uint16)
    line = 0
    for y in range(h):
        # read the row as one little-endian bit string from its byte offset
        bitpos = line * 8
        x = 0
        while x < w:
            wi, bi = divmod(bitpos, 32)
            chunk = words[wi] >> bi
            if bi:
                chunk |= (words[wi + 1] << (32 - bi)) if wi + 1 < nwords else 0
            chunk &= 0xFFFFFFFF
            sym = chunk & mask
            over = (chunk >> bits) & 0x7F
            run = _LEN_DECODE[over]
            out[y, x:min(w, x + run)] = sym
            x += run
            bitpos += bits + _LEN_CONSUME[over]
        if y < len(trims):
            line += trims[y]
    return out


# raw (OCT_FLAG_RAW565) sub-formats: the low byte of octBmp_t::Compression (engine oct_consts.h,
# OCT_RAW565_FORMAT); the upper bits carry a SOFTKEY key/threshold or a MONO1 scale
RAW_FORMATS = {0: "RGB565", 1: "RGB565 RLE", 2: "RGB565 SOFTKEY", 3: "ARGB6666", 4: "ARGB6666 RLE", 5: "MONO1"}
RAW_RUN = 0x80


def _rle_rows(body: bytes, w: int, h: int, texel_bytes: int) -> list[bytes]:
    """Decode the raw RLE stream (OCT_RENDER_raw565_row / OCT_RENDER_argb6666_row_rle): a u16 byte length per
    row, the table padded to 4 bytes, then per row control bytes: below 0x80 a literal run of control + 1
    texels, at or above it one texel repeated control - 0x80 + 2 times. Returns each row's texel bytes."""
    table = h * 2
    if len(body) < table:
        raise ValueError(f"RLE row table needs {table} bytes, payload has {len(body)}")
    lengths = struct.unpack_from(f"<{h}H", body, 0)
    cursor = (table + 3) & ~3
    rows = []
    for y in range(h):
        end = cursor + lengths[y]
        if end > len(body):
            raise ValueError(f"RLE row {y} runs past the payload end")
        out = bytearray()
        while cursor < end:
            control = body[cursor]
            cursor += 1
            if control < RAW_RUN:
                n = control + 1
                out += body[cursor:cursor + texel_bytes * n]
                cursor += texel_bytes * n
            else:
                out += body[cursor:cursor + texel_bytes] * (control - RAW_RUN + 2)
                cursor += texel_bytes
        if len(out) != w * texel_bytes:
            raise ValueError(f"RLE row {y} decodes to {len(out) // texel_bytes} texels, expected {w}")
        cursor = end
        rows.append(bytes(out))
    return rows


def _expand565(t: np.ndarray) -> np.ndarray:
    t = t.astype(np.uint32)
    r5, g6, b5 = (t >> 11) & 0x1F, (t >> 5) & 0x3F, t & 0x1F
    return np.stack([(r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2),
                     np.full_like(t, 255)], axis=-1).astype(np.uint8)


def decode_raw(blob: bytes, hdr) -> tuple[np.ndarray, str]:
    """(h, w, 4) RGBA of a raw (OCT_FLAG_RAW565) sprite in any of the engine's sub-formats, as the engine draws
    it (the engine's OCT_RENDER_raw565); raises ValueError on an unknown sub-format rather than guessing."""
    w, h = hdr.w, hdr.h
    fmt = hdr.compression & 0xFF
    body = blob[pb.BMP_SIZE:]
    n = w * h
    if fmt not in RAW_FORMATS:
        raise ValueError(f"unknown raw sprite format {fmt} (Compression 0x{hdr.compression:08X}); known: "
                         + ", ".join(f"{k} {v}" for k, v in RAW_FORMATS.items()))
    if fmt == 0:
        if len(body) < 2 * n:
            raise ValueError(f"RGB565 payload holds {len(body) // 2} of {n} texels")
        return _expand565(np.frombuffer(body[:2 * n], dtype="<u2").reshape(h, w)), RAW_FORMATS[fmt]
    if fmt in (1, 2):
        t = np.frombuffer(b"".join(_rle_rows(body, w, h, 2)), dtype="<u2").reshape(h, w)
        rgba = _expand565(t)
        if fmt == 2:
            # OCT_RENDER_raw565_keyed_out: a texel within `threshold` of the key (green twice the slack) is not drawn
            key, thr = (hdr.compression >> 8) & 0xFFFF, (hdr.compression >> 24) & 0xFF
            tt = t.astype(np.int32)
            dr = np.abs(((tt >> 11) & 0x1F) - ((key >> 11) & 0x1F))
            dg = np.abs(((tt >> 5) & 0x3F) - ((key >> 5) & 0x3F))
            db = np.abs((tt & 0x1F) - (key & 0x1F))
            rgba[(dr <= thr) & (dg <= 2 * thr) & (db <= thr)] = 0
        return rgba, RAW_FORMATS[fmt]
    if fmt in (3, 4):
        if fmt == 3:
            if len(body) < 3 * n:
                raise ValueError(f"ARGB6666 payload holds {len(body) // 3} of {n} texels")
            raw = body[:3 * n]
        else:
            raw = b"".join(_rle_rows(body, w, h, 3))
        b3 = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3).astype(np.uint32)
        v = b3[..., 0] | (b3[..., 1] << 8) | (b3[..., 2] << 16)
        six = lambda x: ((x << 2) | (x >> 4)).astype(np.uint8)          # noqa: E731
        a6, r6, g6, b6 = (v >> 18) & 0x3F, (v >> 12) & 0x3F, (v >> 6) & 0x3F, v & 0x3F
        # the engine blends with 5 bits of alpha (texel >> 19): that is what the PNG shows
        a5 = a6 >> 1
        rgba = np.stack([six(r6), six(g6), six(b6), ((a5 << 3) | (a5 >> 2)).astype(np.uint8)], axis=-1)
        rgba[a5 == 0] = 0
        return rgba, RAW_FORMATS[fmt]
    # MONO1: two RGB565 inks, then H/scale rows of (W/scale + 7)/8 bytes, module x at bit (x & 7) of byte x >> 3
    scale = (hdr.compression >> 8) & 0xFF
    if scale == 0 or w % scale or h % scale:
        raise ValueError(f"MONO1 scale {scale} does not divide {w}x{h}")
    mw, mh = w // scale, h // scale
    stride = (mw + 7) // 8
    if len(body) < 4 + mh * stride:
        raise ValueError(f"MONO1 payload is {len(body)} bytes, needs {4 + mh * stride}")
    ink = np.frombuffer(body[:4], dtype="<u2")
    rows = np.frombuffer(body[4:4 + mh * stride], dtype=np.uint8).reshape(mh, stride)
    xs = np.arange(mw)
    bits = (rows[:, xs >> 3] >> (xs & 7)) & 1
    modules = _expand565(ink[bits])
    return np.repeat(np.repeat(modules, scale, axis=0), scale, axis=1), RAW_FORMATS[fmt]


def decode_sprite(blob: bytes, palettes: dict[int, np.ndarray]) -> tuple[Image.Image, dict]:
    """One sprite payload -> (RGBA image at its stored size, info)."""
    if len(blob) < pb.BMP_SIZE:
        raise ValueError(f"sprite payload is {len(blob)} bytes, shorter than the {pb.BMP_SIZE}-byte header")
    h = pb.parse_bmp_header(blob)
    info = {"w": h.w, "h": h.h, "flags": h.flags, "pidx": h.pidx, "seq": h.seq, "rate": h.rate,
            "pivot": [h.pivot_x, h.pivot_y], "compression": h.compression}
    if h.w <= 0 or h.h <= 0:
        raise ValueError(f"sprite size {h.w}x{h.h}")
    if h.flags & pb.OCT_FLAG_RAW565:
        rgba, fmt = decode_raw(blob, h)
        info["color"] = "full"
        info["format"] = fmt
        return Image.fromarray(rgba, "RGBA"), info
    pal = palettes.get(h.pidx)
    if pal is None:
        raise ValueError(f"palette asset id {h.pidx} is missing")
    idx = decode_palette_indices(blob)
    if int(idx.max(initial=0)) >= len(pal):
        raise ValueError(f"index {int(idx.max())} past the end of palette {h.pidx} ({len(pal)} colours)")
    info["color"] = "palette"
    info["format"] = "palette"
    return Image.fromarray(pal[idx], "RGBA"), info


def pixel_digest(image) -> str:
    """sha1 of an image's pixels as the engine sees them (RGBA, a fully transparent pixel has no colour) plus
    its size: equal digests = the same sprite whatever PNG encoder wrote the file."""
    if isinstance(image, (str, Path)):
        with Image.open(image) as im:
            a = np.asarray(im.convert("RGBA")).copy()
    elif isinstance(image, Image.Image):
        a = np.asarray(image.convert("RGBA")).copy()
    else:
        a = np.asarray(image).copy()
    a[a[..., 3] == 0] = 0
    import hashlib
    return hashlib.sha1(f"{a.shape[1]}x{a.shape[0]}:".encode() + a.tobytes()).hexdigest()


# ── extraction ──────────────────────────────────────────────────────────────

def manifest_pivot(info: dict) -> list[int] | None:
    """The manifest pivot that packs back to this header pivot (build_pipeline
    _center_pivots: on-screen = p*k - 0.5, k = 1 fullsize else 2); None = centred."""
    w, h = info["w"], info["h"]
    full = bool(info["flags"] & pb.OCT_FLAG_FULLSIZE)
    px, py = info["pivot"]
    centred = ((w - 1) / 2.0, (h - 1) / 2.0) if full else (w - 0.5, h - 0.5)
    if (abs(px - centred[0]) < 1e-3 and abs(py - centred[1]) < 1e-3):
        return None
    k = 1.0 if full else 2.0
    return [int(round((px + 0.5) / k)), int(round((py + 0.5) / k))]


def _rel(path: Path, base: Path) -> str:
    """`path` relative to `base` (posix): the listing and the manifest never name this machine's folders."""
    try:
        return Path(os.path.relpath(Path(path).resolve(), Path(base).resolve())).as_posix()
    except ValueError:                  # another drive on Windows
        return path.as_posix()


def glyph_font(name: str) -> str | None:
    """`font_1` for the glyph sprite `font_1_00065`, None for any other name."""
    return name.rsplit("_", 1)[0] if GLYPH_RE.match(name) else None


def font_digest(fnt: str | Path) -> str:
    """sha256 of a BMFont source as the packer reads it: the .fnt and its atlas pages (<stem>_<n>.png next to it,
    the convention build_pipeline mirrors into <workspace>/fonts). The same font in app_<game>/art and in
    <workspace>/fonts gives the same digest."""
    import hashlib
    fnt = Path(fnt)
    h = hashlib.sha256(fnt.read_bytes())
    page_re = re.compile(rf"^{re.escape(fnt.stem)}_\d+\.png$", re.IGNORECASE)
    for page in sorted(p for p in fnt.parent.iterdir() if p.is_file() and page_re.match(p.name)):
        h.update(b"\0" + page.name.lower().encode("utf-8") + b"\0" + page.read_bytes())
    return h.hexdigest()


def font_listing(listing: dict, app_dir: str | Path | None) -> dict:
    """Every font the extraction saw: the fonts with glyph records in the pack and the BMFont sources in
    app_<game>/art (font_*.fnt, what build_pipeline mirrors into <workspace>/fonts). Per font: `packed` (its
    glyphs are in the pack), `glyphs` (how many), `digest` (font_digest of the source present at extraction,
    None without one). The carry plan (scripts/carry_art.py) keeps a packed font's glyph records while its
    source is unchanged and packs no font the original pack did not hold, unless the manifest asks for it."""
    fonts: dict[str, dict] = {}
    for a in listing["assets"]:
        if a.get("glyph"):
            f = fonts.setdefault(a["font"], {"packed": True, "glyphs": 0, "digest": None})
            f["glyphs"] += 1
    if app_dir is not None:
        for fnt in sorted((Path(app_dir) / "art").glob("font_*.fnt")):
            f = fonts.setdefault(fnt.stem, {"packed": False, "glyphs": 0, "digest": None})
            f["digest"] = font_digest(fnt)
    return fonts


def extract(container: Container, out: str | Path) -> dict:
    """Decode every sprite into <out>/art and <out>/original; keep every packed sprite and palette record
    verbatim in <out>/original/packed (what the pack carries through byte for byte); return the listing."""
    out = Path(out)
    art, orig = out / "art", out / "original"
    records_dir = out / RECORDS_SUBDIR
    for d in (art, orig, records_dir):
        d.mkdir(parents=True, exist_ok=True)
    for stale in [*records_dir.glob("*.raw"), *records_dir.glob("*.pal")]:
        stale.unlink()                  # a re-extraction (--force) never mixes in another app's records
    palettes: dict[int, np.ndarray] = {}
    for i, (kind, _name) in enumerate(container.records):
        if kind == pb.KIND_PAL and i in container.payloads:
            palettes[i] = pal_rgba(_words(container.payloads[i]))
    listing = {"source": container.source, "records": RECORDS_SUBDIR, "assets": [], "skipped": [], "errors": []}
    names_by_id = {i: n for i, (_k, n) in enumerate(container.records)}
    for i, (kind, name) in enumerate(container.records):
        entry = {"id": i, "name": name, "kind": pb._KIND_NAMES.get(kind, kind)}
        if kind == pb.KIND_PAL:
            entry["colours"] = len(palettes.get(i, []))
            entry["alpha"] = bool(i in container.payloads and pb.pal_is_spread(_words(container.payloads[i])))
            if i in container.payloads:
                (records_dir / f"{name}.pal").write_bytes(container.payloads[i])
                entry["record"] = f"{RECORDS_SUBDIR}/{name}.pal"
            listing["assets"].append(entry)
            continue
        if kind == pb.KIND_SOUND:
            blob = container.payloads.get(i)
            entry["bytes"] = len(blob) if blob is not None else None
            listing["assets"].append(entry)
            continue
        if kind == pb.KIND_MAP:
            entry["note"] = ("launcher map, rebuilt by the pack from the icon" if name in pb.RESERVED_LAUNCHER_MAPS
                             else "placement map: the manifest pack cannot rebuild it")
            listing["assets"].append(entry)
            if name not in pb.RESERVED_LAUNCHER_MAPS:
                listing["skipped"].append({"name": name, "why": entry["note"]})
            continue
        if name == "zero":
            continue
        blob = container.payloads.get(i)
        if blob is None:
            listing["errors"].append(f"{name}: no payload")
            continue
        if GLYPH_RE.match(name):
            # a font glyph is no manifest sprite: its record is carried through as it is (with its palette)
            # while its font's source is unchanged (font_listing / carry_art.font_plan)
            if len(blob) < pb.BMP_SIZE:
                listing["errors"].append(f"{name}: glyph payload is {len(blob)} bytes")
                continue
            hdr = pb.parse_bmp_header(blob)
            (records_dir / f"{name}.raw").write_bytes(blob)
            raw = bool(hdr.flags & pb.OCT_FLAG_RAW565)
            entry.update({"glyph": True, "font": glyph_font(name), "record": f"{RECORDS_SUBDIR}/{name}.raw",
                          "palette": None if raw else names_by_id.get(hdr.pidx),
                          "next_frame": names_by_id.get(hdr.seq) if hdr.seq else None, "rate": hdr.rate})
            listing["assets"].append(entry)
            continue
        try:
            img, info = decode_sprite(blob, palettes)
        except (ValueError, IndexError, struct.error) as exc:
            listing["errors"].append(f"{name}: {exc}")
            continue
        (records_dir / f"{name}.raw").write_bytes(blob)
        target = out / "icon.png" if name == LAUNCHER_ICON else art / f"{name}.png"
        img.save(target)
        shutil.copyfile(target, orig / f"{name}.png")
        f = info["flags"]
        rgba = np.asarray(img)
        entry.update({
            "png": _rel(target, out), "size": [info["w"], info["h"]], "color": info["color"],
            "format": info["format"],
            "flags": {"alpha": bool(f & pb.OCT_FLAG_ALPHA), "fullsize": bool(f & pb.OCT_FLAG_FULLSIZE),
                      "additive": bool(f & pb.OCT_FLAG_ADDITIVE), "bg": bool(f & pb.OCT_FLAG_BG)},
            "palette": names_by_id.get(info["pidx"]) if info["color"] == "palette" else None,
            "next_frame": names_by_id.get(info["seq"]) if info["seq"] else None,
            "rate": info["rate"], "header_pivot": info["pivot"],
            "semi_transparent": bool(((rgba[..., 3] > 0) & (rgba[..., 3] < 255)).any()),
            "transparent": bool((rgba[..., 3] == 0).any()),
            "record": f"{RECORDS_SUBDIR}/{name}.raw", "pixels": pixel_digest(img),
        })
        listing["assets"].append(entry)
    return listing


def manifest_sprite(a: dict) -> dict:
    """The manifest entry that repacks one extracted sprite (listing entry `a`) as it is: `keep`, its size,
    colour tier, flags, background and pivot. scripts/carry_art.py compares a manifest entry with this to
    decide whether the original record can be carried through."""
    fl = a["flags"]
    full = a["color"] == "full"
    if full and a.get("format") not in (None, "RGB565", "RGB565 RLE") and a.get("transparent"):
        # a keyed or translucent raw sprite (SOFTKEY, ARGB6666): the manifest pack writes no such format, so an
        # edited copy is re-encoded as a palette sprite with alpha, which keeps its transparency
        full = False
        fl = dict(fl, alpha=True)
    desc = "original sprite of the game, extracted from its packed art (carried through unchanged)"
    if a["name"] == "launcher_icon":
        desc += ("; an in-game sprite record named launcher_icon, NOT the launcher icon: the cube's launcher shows "
                 "<workspace>/icon.png (ico_idle)")
    s = {"name": a["name"], "size": a["size"],
         "description": desc,
         "keep": True, "color": "full" if full else "palette",
         "background": "opaque" if (full or fl["bg"]) else "key",
         "flags": {"alpha": False if full else fl["alpha"], "fullsize": fl["fullsize"],
                   "additive": fl["additive"], "bg": fl["bg"]}}
    if a.get("semi_transparent") and not full and s["flags"]["alpha"]:
        s["alpha"] = "soft"
    piv = manifest_pivot({"w": a["size"][0], "h": a["size"][1],
                          "flags": (2 if fl["fullsize"] else 0), "pivot": a["header_pivot"]})
    if piv is not None:
        s["pivot"] = piv
    return s


def manifest_icon(a: dict) -> dict:
    """The manifest `icon` tier that repacks the extracted launcher icon (listing entry `a`)."""
    side = max(a["size"])
    if a["color"] == "palette" and side in (120, 240):
        return {"color": "palette", "side": side}
    return {"color": "full", "side": side}


def build_manifest(listing: dict, game: str, out: Path, manifest_path: Path) -> dict:
    """A manifest that repacks exactly the extracted set: every sprite `keep`."""
    sprites = []
    icon = None
    for a in listing["assets"]:
        if a["kind"] != "SPRITE" or "png" not in a:
            continue
        if a["name"] == LAUNCHER_ICON:
            icon = manifest_icon(a)
            continue
        sprites.append(manifest_sprite(a))
    sounds = [{"name": a["name"], "description": "original sound of the game (carried through unchanged)",
               "keep": True} for a in listing["assets"] if a["kind"] == "SOUND"]
    data = {"game": game, "schema_version": 1,
            "_origin": {"extracted_from": _rel(out / listing["source"], manifest_path.parent),
                        "listing": _rel(out / "extracted.json", manifest_path.parent),
                        "originals": _rel(out / "original", manifest_path.parent)},
            "sprites": sprites, "sounds": sounds}
    if icon is not None:
        data["icon"] = icon
    return data


ART_PY = Path(__file__).resolve().parent.parent / "skills" / "cube_art-director" / "scripts" / "art.py"


def anchor_originals(manifest: Path, out: Path) -> bool:
    """The extracted game's own sprites are its style: anchor a few kept ones (art.py anchor --originals), so new
    or edited sprites are scored against them (art.py qa) and the reviewer has a style reference."""
    cmd = [sys.executable, str(ART_PY), "anchor", str(manifest), "--workspace", str(out), "--originals"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:
        r = None
        why = str(exc)
    if r is not None and r.returncode == 0:
        picked = next((ln.split(":", 1)[1].strip() for ln in r.stdout.splitlines()
                       if ln.startswith("style reference")), "")
        print(f"  style reference -> {out / 'style'} (anchors: {picked}; art.py qa scores new sprites against them)")
        return True
    if r is not None:
        why = (r.stderr or r.stdout).strip().splitlines()[-1:] or [f"exit {r.returncode}"]
        why = why[0]
    print(f"  NOTE: no style reference anchored ({why}); run: python {ART_PY} anchor {manifest} --workspace {out} "
          f"--originals", file=sys.stderr)
    return False


def _game_of(app_dir: Path | None, oct_path: Path | None, game: str | None) -> str:
    if game:
        return game[4:] if game.startswith("app_") else game
    if app_dir is not None:
        name = pb.app_name_of(app_dir)
        return name[4:] if name.startswith("app_") else name
    stem = oct_path.stem if oct_path else "game"
    return stem[4:] if stem.startswith("app_") else stem


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--app-dir", type=Path, help="packed app folder (index.bin + art/packed)")
    src.add_argument("--oct", type=Path, help="a device .oct")
    ap.add_argument("--out", type=Path, required=True, help="output folder, normally <ws>/assets_<game>")
    ap.add_argument("--manifest", type=Path, default=None,
                    help="also write a manifest covering every extracted sprite and sound (keep: true)")
    ap.add_argument("--game", default=None, help="game name for the manifest (default: from the .target marker)")
    ap.add_argument("--force", action="store_true", help="overwrite existing PNGs / the manifest")
    ap.add_argument("--no-anchor", action="store_true",
                    help="with --manifest: do not anchor kept sprites as the style reference (art.py anchor --originals)")
    args = ap.parse_args(argv)

    try:
        container = load_app(args.app_dir) if args.app_dir else load_oct(args.oct)
    except (OSError, ValueError, struct.error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    out = args.out
    if not args.force:
        clash = [p for p in ((out / "art").glob("*.png") if (out / "art").is_dir() else [])
                 if p.stem != "0"]
        if clash:
            print(f"ERROR: {out / 'art'} already holds {len(clash)} PNG(s) (edited art?); pass --force to "
                  f"overwrite them with the packed originals", file=sys.stderr)
            return 2
        if args.manifest is not None and args.manifest.exists():
            print(f"ERROR: {args.manifest} exists; pass --force to replace it", file=sys.stderr)
            return 2

    listing = extract(container, out)
    listing["source"] = _rel(Path(container.source), out)      # relative to the listing's own folder
    listing["fonts"] = font_listing(listing, args.app_dir)
    if args.oct is not None:
        snd = out / "wav" / "assets"
        for i, (kind, name) in enumerate(container.records):
            if kind == pb.KIND_SOUND and i in container.payloads:
                snd.mkdir(parents=True, exist_ok=True)
                (snd / f"{name}.mp3").write_bytes(container.payloads[i])
    # the packer's slot-0 placeholder, as art.py process writes it
    Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(out / "art" / "0.png")
    (out / "extracted.json").write_text(json.dumps(listing, indent=1), encoding="utf-8")

    sprites = [a for a in listing["assets"] if a["kind"] == "SPRITE" and "png" in a]
    print(f"extracted {len(sprites)} sprite(s) from {container.source} -> {out / 'art'} "
          f"(originals in {out / 'original'})")
    if any(a["name"] == LAUNCHER_ICON for a in sprites):
        print(f"  launcher icon -> {out / 'icon.png'} (the one source of this game's launcher icon from now on)")
        stale = Path(args.app_dir) / "art" / "icon.png" if args.app_dir else None
        if stale is not None and stale.is_file():
            print(f"  NOTE: {stale} is not used for this game any more: repack_app.py and the pack take "
                  f"{out / 'icon.png'} (what the cube shows today, carried through byte for byte while unchanged)")
    glyphs = [a for a in listing["assets"] if a.get("glyph")]
    if glyphs:
        fonts = sorted({a["font"] for a in glyphs})
        print(f"  {len(glyphs)} font glyph(s) of {', '.join(fonts)} kept as packed records (the pack carries them "
              f"through unchanged while that font's font_<n>.fnt source is unchanged; an edited or new source "
              f"rebuilds only that font's glyphs)")
    unpacked = sorted(n for n, f in listing["fonts"].items() if not f["packed"])
    if unpacked:
        print(f"  NOTE: {', '.join(unpacked)}: font source(s) in the app's art/ that the pack never held: not packed "
              f"(add \"fonts\": [\"<name>\"] to the manifest to pack one)")
    for s in listing["skipped"]:
        print(f"  NOTE: {s['name']}: {s['why']}")
    if args.manifest is not None:
        game = _game_of(args.app_dir, args.oct, args.game)
        data = build_manifest(listing, game, out, args.manifest)
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(data, indent=1), encoding="utf-8")
        print(f"  manifest -> {args.manifest} ({len(data['sprites'])} sprite(s) and {len(data['sounds'])} "
              f"sound(s), every one `keep`)")
        if not args.no_anchor:
            anchor_originals(args.manifest, out)
    print(f"  listing -> {out / 'extracted.json'}")
    for e in listing["errors"]:
        print(f"ERROR: {e}", file=sys.stderr)
    return 1 if listing["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
