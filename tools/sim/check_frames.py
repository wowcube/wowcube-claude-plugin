#!/usr/bin/env python3
"""Validate every PNG of a --frames run against its sim_summary.txt (run_hidden.ps1 / run_hidden.sh call it).

    python check_frames.py <frames_dir> <sim_summary.txt> [--expect N] [--allow-drops]

Every frame_*.png is decoded in full (signature, chunk CRCs, IHDR, the whole zlib stream inflated to exactly the size
IHDR promises, IEND), not only the last one: a truncated or corrupt file anywhere fails. Then the counts: the PNGs on
disk must equal the summary's `written`; without --allow-drops they must also equal `expected` (the strict schedule,
ceil(seconds*1000 / every_ms); --expect: the count the caller computed from its own --seconds / --every-ms, which
`expected` must match too) and the summary must report no `dropped` / `skipped` slot.

Exit 0 = all good | 1 = a PNG is corrupt or truncated | 2 = PNGs on disk != written | 3 = usage / no summary |
4 = the schedule is incomplete (a slot dropped or skipped, or fewer frames than expected).
Standard library only.
"""
from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

SIG = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def png_error(path: Path) -> str | None:
    """None when the PNG decodes completely, else what is wrong."""
    try:
        data = path.read_bytes()
    except OSError as e:
        return f"unreadable: {e}"
    if not data.startswith(SIG):
        return "no PNG signature"
    pos, ihdr, idat, seen_end = len(SIG), None, [], False
    while pos + 8 <= len(data):
        length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        crc = data[pos + 8 + length:pos + 12 + length]
        if len(body) != length or len(crc) != 4:
            return f"truncated in chunk {ctype!r}"
        if zlib.crc32(ctype + body) & 0xFFFFFFFF != struct.unpack(">I", crc)[0]:
            return f"bad CRC in chunk {ctype!r}"
        if ctype == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif ctype == b"IDAT":
            idat.append(body)
        elif ctype == b"IEND":
            seen_end = True
            break
        pos += 12 + length
    if ihdr is None:
        return "no IHDR"
    if not seen_end:
        return "truncated (no IEND)"
    w, h, depth, ctype_, _, _, interlace = ihdr
    if interlace != 0 or ctype_ not in CHANNELS or depth not in (8, 16):
        return None  # not what the simulator writes; the chunk checks above passed
    want = h * (1 + (w * CHANNELS[ctype_] * depth + 7) // 8)
    try:
        raw = zlib.decompress(b"".join(idat))
    except zlib.error as e:
        return f"pixel data does not inflate: {e}"
    if len(raw) != want:
        return f"pixel data is {len(raw)} bytes, {w}x{h} needs {want}"
    return None


def read_summary(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        k, sep, v = line.partition("=")
        if sep:
            out[k.strip()] = v.strip()
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("frames_dir")
    ap.add_argument("summary")
    ap.add_argument("--allow-drops", action="store_true")
    ap.add_argument("--expect", type=int, default=-1, help="frames the caller's seconds/every-ms owe")
    a = ap.parse_args(argv)
    summary = Path(a.summary)
    if not summary.is_file():
        print(f"check_frames: no summary: {summary}")
        return 3
    s = read_summary(summary)
    pngs = sorted(Path(a.frames_dir).glob("frame_*.png"))

    bad = [(p.name, err) for p in pngs if (err := png_error(p))]
    for name, err in bad[:20]:
        print(f"  corrupt frame: {name}: {err}")
    if bad:
        print(f"check_frames: {len(bad)} of {len(pngs)} PNG(s) do not decode")
        return 1

    def num(k: str) -> int:
        try:
            return int(s.get(k, ""))
        except ValueError:
            return -1

    if num("written") != len(pngs):
        print(f"  the summary reports {s.get('written')} frames written, the folder holds {len(pngs)}")
        return 2
    problems = []
    if not a.allow_drops:
        if num("dropped") != 0 or num("skipped") != 0:
            problems.append(f"schedule slots lost: dropped={s.get('dropped')} skipped={s.get('skipped')}")
        if a.expect >= 0 and num("expected") != a.expect:
            problems.append(f"the summary's schedule owes {s.get('expected')} frames, this run asked for {a.expect}")
        if num("expected") > 0 and len(pngs) != num("expected"):
            problems.append(f"{len(pngs)} frames, the schedule owes {s.get('expected')} "
                            f"({s.get('seconds')} s every {s.get('every_ms')} ms)")
    for p in problems:
        print(f"  {p}")
    if problems:
        return 4
    skew = num("skewed")
    print(f"check_frames: {len(pngs)} PNG(s) decode" + (f", expected {s.get('expected')}" if num("expected") > 0 else "")
          + (f"; {skew} skewed (some screens still under another topology, mid-twist or at start-up: slots {s.get('skewed_slots')})" if skew > 0 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
