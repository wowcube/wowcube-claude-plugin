#!/usr/bin/env python3
"""Cut a short animation video into keyed sprite frames (the "animation from video" art route).

An image-to-video service animates one approved picture of a character on a flat key colour
(cube_art-director/references/ANIMATION_VIDEO.md). This tool turns the clip into frames the
art pipeline takes like any other drawing:

  1. ffmpeg decodes every frame of the clip (or of --start/--end) into a temporary folder;
  2. N frames are picked evenly; a loop (the default) leaves out the clip's last frame, which
     repeats the first;
  3. the flat background is keyed out: its colour is the median of the four corners over all
     frames (--key auto) or the colour given; alpha ramps from 0 to 1 over the colour distance
     --key-range LO:HI (default 40:80);
  4. despill: the outline's half-transparent pixels (and a --ring of edge pixels) take the colour
     of the nearest solid pixels inside the character, so no key-coloured fringe shows on a dark
     background; what has no solid neighbour is un-mixed from the key colour;
  5. one crop box over all frames (the union of the solid pixels), so the motion stays as filmed;
     scaled to fit the target size and placed on a canvas of exactly that size (--align);
  6. writes one PNG per frame, a sprite sheet + JSON atlas (the format `art.py sheet` writes), a
     preview GIF on a dark background at the cube's x2 display scale, and prints the loop seam:
     the mean difference (0-255) between the first frame and the clip's last frame, next to the
     typical step between two picked frames, and the wrap (the jump from the last picked frame
     back to the first when the animation restarts).

The frames are drawings: with --spec they go where the pipeline reads them (a WowCube manifest:
<workspace>/raw/<name>.png, then `art.py process`; an art.json project: <project>/drawn/, used as
"source": "drawn/<name>.png") and the size, the frame names and the count come from the spec.

    python scripts/video_to_frames.py <clip.mp4> --name hero_idle --frames 8 --size 40x40 --out <dir>
    python scripts/video_to_frames.py <clip.mp4> --name hero_idle --spec plans/<game>_assets.json
    python scripts/video_to_frames.py <clip.mp4> --name hero_idle --spec <project>/art.json --frames 8

Frame names: <name>_00, <name>_01, ... (the pipeline's animation naming, manifest_schema.py); with
--spec, the names of the spec's frames of that animation, in order. Existing frames are only
overwritten with --force.

The first frame: the video animates the approved still of frame 0, so an existing <name>_00 (with
--spec: its final, raw or drawn image; else the file in --out) is KEPT by default and only the other
frames are written (`art.py budget --video` counts only those). --no-keep-first replaces it with the
clip's first frame (needs --force when it exists); --keep-first insists on keeping it.

Exit 0 = done; 1 = the clip could not be read or nothing was found in it; 2 = bad arguments;
3 = ffmpeg / ffprobe not found.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ART_SCRIPTS = HERE.parent / "skills" / "cube_art-director" / "scripts"

KEY_NAMES = {"magenta": (255, 0, 255), "green": (0, 255, 0)}
GIF_BG = (32, 32, 40)                 # dark: shows a key-coloured fringe at once
MIN_FRAME_MS = 50                     # 20 fps is the cube's cap
_FRAME_RE = r"^{base}_(\d{{2,}})$"


# --------------------------------------------------------------------------- arguments
def parse_size(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d+)\s*(?:[xX*,]\s*(\d+))?\s*", text or "")
    if not m:
        raise ValueError(f"--size {text!r}: write it as WxH (40x40) or one number for a square")
    w = int(m.group(1))
    h = int(m.group(2)) if m.group(2) else w
    if w < 1 or h < 1:
        raise ValueError(f"--size {text!r}: must be at least 1x1")
    return w, h


def parse_key(text: str):
    """'auto' -> None; 'magenta' / 'green' / '#RRGGBB' / 'R,G,B' -> an (r, g, b) tuple."""
    t = (text or "auto").strip().lower()
    if t == "auto":
        return None
    if t in KEY_NAMES:
        return KEY_NAMES[t]
    m = re.fullmatch(r"#?([0-9a-f]{6})", t)
    if m:
        v = m.group(1)
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r"(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", t)
    if m and all(int(x) <= 255 for x in m.groups()):
        return tuple(int(x) for x in m.groups())
    raise ValueError(f"--key {text!r}: auto, magenta, green, #RRGGBB or R,G,B")


def parse_range(text: str) -> tuple[float, float]:
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[:,-]\s*(\d+(?:\.\d+)?)\s*", text or "")
    if not m or float(m.group(1)) >= float(m.group(2)):
        raise ValueError(f"--key-range {text!r}: LO:HI with LO < HI, e.g. 40:80")
    return float(m.group(1)), float(m.group(2))


def frames_from_spec(spec: Path, base: str, workspace=None):
    """(frame names in order, (w, h), frames folder, sheet folder, kind, the approved frame 0 or None) for the
    animation `base` of an art.json project or a WowCube manifest."""
    sys.path.insert(0, str(ART_SCRIPTS))
    from art import approved_first_frame       # noqa: E402  (the same rule as `art.py budget --video`)
    from art_spec import load_project          # noqa: E402  (cube_art-director's spec reader)
    p = load_project(spec, workspace)
    rx = re.compile(_FRAME_RE.format(base=re.escape(base)))
    found = sorted(((int(m.group(1)), a) for a in p.assets for m in [rx.match(a.name)] if m), key=lambda t: t[0])
    if not found:
        raise ValueError(f"{spec}: no frames named {base}_00, {base}_01, ... (the animation's frames must be "
                         f"in the spec first)")
    sizes = {tuple(a.size) for _, a in found}
    if len(sizes) != 1:
        raise ValueError(f"{spec}: the frames of {base} have different sizes {sorted(sizes)}")
    if p.kind == "cube-manifest":
        frames_dir, sheet_dir = p.workspace / "raw", p.workspace / "video"
    else:
        frames_dir, sheet_dir = p.root / "drawn", p.workspace / "video"
    return [a.name for _, a in found], sizes.pop(), frames_dir, sheet_dir, p.kind, approved_first_frame(p, base)


# --------------------------------------------------------------------------- decoding
def tool(name: str) -> str:
    exe = shutil.which(name)
    if not exe:
        raise FileNotFoundError(name)
    return exe


def decode_cmd(video: Path, folder: Path, start: float | None, end: float | None) -> list[str]:
    """The ffmpeg command line: -ss before the input (a fast, accurate seek), the stop as an output duration
    -t (end - start). `-to` as an input option needs ffmpeg 5.1+; -t works on every version."""
    cmd = [tool("ffmpeg"), "-v", "error", "-y"]
    if start is not None:
        cmd += ["-ss", f"{start}"]
    cmd += ["-i", str(video)]
    if end is not None:
        cmd += ["-t", f"{end - (start or 0.0)}"]
    return cmd + [str(folder / "f%05d.png")]


def decode(video: Path, folder: Path, start: float | None, end: float | None) -> list[Path]:
    """Every frame of the clip (or of start..end seconds) as PNGs in `folder`, in order."""
    cmd = decode_cmd(video, folder, start, end)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg could not read {video}: {r.stderr.strip()[-400:]}")
    return sorted(folder.glob("f*.png"))


def duration(video: Path) -> float | None:
    try:
        out = subprocess.run([tool("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of",
                              "csv=p=0", str(video)], capture_output=True, text=True, check=True).stdout
        return float(out.strip())
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
        return None


def pick_indices(total: int, n: int, loop: bool) -> list[int]:
    """n frame indices spread evenly over `total`; a loop leaves out the last frame (it repeats the first)."""
    if n > total:
        raise ValueError(f"the clip has {total} frame(s); cannot pick {n}")
    if n == 1:
        return [0]
    if loop:
        span = total - 1 if total > n else total     # the last frame closes the loop: never picked
        return [int(i * span / n) for i in range(n)]
    return [round(i * (total - 1) / (n - 1)) for i in range(n)]


# --------------------------------------------------------------------------- keying
def corner_colour(rgbs: list[np.ndarray], patch: int = 8) -> np.ndarray:
    """The median colour of the four corner patches over all frames (the flat background)."""
    parts = []
    for a in rgbs:
        p = max(1, min(patch, a.shape[0] // 4, a.shape[1] // 4))
        parts += [a[:p, :p], a[:p, -p:], a[-p:, :p], a[-p:, -p:]]
    return np.median(np.concatenate([x.reshape(-1, 3) for x in parts]), axis=0)


def key_alpha(rgb: np.ndarray, key, lo: float, hi: float) -> np.ndarray:
    """Alpha 0..1 from the colour distance to the key: 0 below `lo`, 1 above `hi`, a ramp between."""
    d = np.sqrt(((rgb.astype(np.float32) - np.asarray(key, np.float32)) ** 2).sum(-1))
    return np.clip((d - lo) / (hi - lo), 0.0, 1.0)


def _box3(x: np.ndarray) -> np.ndarray:
    """Sum over each pixel's 3x3 neighbourhood (zero outside the image)."""
    pad = [(1, 1), (1, 1)] + [(0, 0)] * (x.ndim - 2)
    xp = np.pad(x, pad)
    h, w = x.shape[:2]
    return sum(xp[dy:dy + h, dx:dx + w] for dy in range(3) for dx in range(3))


def despill(rgb: np.ndarray, alpha: np.ndarray, key, ring: int = 1, reach: int = 8) -> np.ndarray:
    """The edge pixels' colour without the key: half-transparent pixels and `ring` pixels of the solid
    edge take the mean colour of the nearest solid pixels further inside (grown outwards up to `reach`
    steps); a pixel with no solid pixel in reach is un-mixed from the key, c = a*fg + (1-a)*key."""
    rgb = rgb.astype(np.float32)
    solid = alpha >= 0.999
    for _ in range(max(0, ring)):
        solid = solid & (_box3(solid.astype(np.float32)) >= 9)
    fix = (alpha > 0) & ~solid
    if not fix.any():
        return rgb
    col = np.where(solid[..., None], rgb, 0.0)
    wgt = solid.astype(np.float32)
    have = solid.copy()
    for _ in range(max(1, reach)):
        todo = fix & ~have
        if not todo.any():
            break
        s, w = _box3(col), _box3(wgt)
        new = todo & (w > 0)
        col[new] = s[new] / w[new][:, None]
        wgt[new] = 1.0
        have |= new
    out = rgb.copy()
    filled = fix & have
    out[filled] = col[filled]
    rest = fix & ~have
    if rest.any():
        a = np.maximum(alpha[rest], 0.05)[:, None]
        out[rest] = (rgb[rest] - (1 - a) * np.asarray(key, np.float32)) / a
    return np.clip(out, 0, 255)


# --------------------------------------------------------------------------- the cut
def cut(rgbs: list[np.ndarray], size: tuple[int, int], key=None, key_range=(40.0, 80.0), ring: int = 1,
        align: str = "center", supersample: int = 1):
    """Keyed, despilled RGBA frames at `size` * `supersample` on one shared crop. Returns (frames, info)."""
    key_rgb = np.asarray(key, np.float32) if key is not None else corner_colour(rgbs)
    lo, hi = key_range
    keyed = []
    for a in rgbs:
        al = key_alpha(a, key_rgb, lo, hi)
        col = despill(a, al, key_rgb, ring=ring)
        keyed.append(np.dstack([col, al * 255]).round().astype(np.uint8))
    box = None
    for k in keyed:
        ys, xs = np.nonzero(k[..., 3] > 128)
        if len(xs) == 0:
            continue
        b = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    if box is None:
        raise ValueError("nothing but background in the clip: check the key colour (--key) and --key-range")
    W, H = size[0] * supersample, size[1] * supersample
    bw, bh = box[2] - box[0], box[3] - box[1]
    scale = min(W / bw, H / bh)
    tw, th = max(1, round(bw * scale)), max(1, round(bh * scale))
    x0 = (W - tw) // 2
    y0 = H - th if align == "bottom" else (H - th) // 2
    frames = []
    for k in keyed:
        im = Image.fromarray(k, "RGBA").crop(box).resize((tw, th), Image.LANCZOS)
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        canvas.paste(im, (x0, y0))
        frames.append(canvas)
    info = {"key": "#%02X%02X%02X" % tuple(int(round(v)) for v in key_rgb), "key_range": [lo, hi],
            "crop": list(box), "scale": round(scale, 5), "source_size": [int(rgbs[0].shape[1]), int(rgbs[0].shape[0])]}
    return frames, info


def mean_diff(a: Image.Image, b: Image.Image) -> float:
    """Mean difference (0-255) of what is seen: colours weighted by alpha, plus alpha itself (the colour of a
    fully transparent pixel does not count)."""
    def seen(im):
        x = np.asarray(im.convert("RGBA"), np.float32)
        return np.dstack([x[..., :3] * x[..., 3:4] / 255.0, x[..., 3:4]])
    return float(np.abs(seen(a) - seen(b)).mean())


def seam_report(frames: list[Image.Image], closing: Image.Image | None) -> dict:
    """Loop seam (first frame vs the clip's closing frame) next to the typical step between picked frames."""
    steps = [mean_diff(frames[i], frames[i + 1]) for i in range(len(frames) - 1)]
    out = {"step_median": round(float(np.median(steps)), 2) if steps else 0.0}
    if closing is not None:
        out["seam"] = round(mean_diff(frames[0], closing), 2)
    if len(frames) > 1:
        out["wrap"] = round(mean_diff(frames[-1], frames[0]), 2)     # the jump the loop makes when it restarts
    return out


def _build_sheet():
    sys.path.insert(0, str(ART_SCRIPTS))
    from art import build_sheet                 # noqa: E402  (the same sheet + atlas as `art.py sheet`)
    return build_sheet


def clip_seconds(video: Path, start: float | None, end: float | None) -> float | None:
    """How long the part of the clip that was cut lasts; None when it is not known (no ffprobe answer and no
    --end): the preview then uses its default pace."""
    total = duration(video)
    stop = end if end is not None else total
    if stop is None:
        return None
    if total is not None:
        stop = min(stop, total)
    span = stop - (start or 0.0)
    return span if span > 0 else None


def run(video: Path, names: list[str], size: tuple[int, int], frames_dir: Path, sheet_dir: Path, *, key=None,
        key_range=(40.0, 80.0), ring: int = 1, align: str = "center", supersample: int = 1, loop: bool = True,
        start: float | None = None, end: float | None = None, fps: float | None = None, sheet_name: str,
        force: bool = False, keep_first: bool | None = None, approved_first: Path | None = None) -> dict:
    """Cut the clip into `names`. `keep_first`: None = keep an existing first frame (the approved still the video
    was made from: `approved_first`, else the file in `frames_dir`), True = keep it, False = replace it."""
    targets = [frames_dir / f"{n}.png" for n in names]
    first = approved_first if approved_first is not None else (targets[0] if targets[0].exists() else None)
    keep = (first is not None) if keep_first is None else bool(keep_first)
    if keep and first is None:
        raise ValueError(f"--keep-first: there is no {names[0]} to keep (approve the first frame first, or leave "
                         f"--keep-first out)")
    if keep and len(names) < 2:
        raise ValueError(f"{names[0]} is the only frame and it is already approved: nothing for the clip to replace")
    write = targets[1:] if keep else targets
    existing = [t.name for t in write if t.exists()]
    if existing and not force:
        raise FileExistsError(f"{frames_dir} already has {', '.join(existing[:4])}"
                              f"{' ...' if len(existing) > 4 else ''}: pass --force to replace them")
    with tempfile.TemporaryDirectory(prefix="v2f_") as td:
        files = decode(video, Path(td), start, end)
        if not files:
            raise RuntimeError(f"no frames decoded from {video}"
                               + (f" (is --start {start} past the end of the clip?)" if start else ""))
        idx = pick_indices(len(files), len(names), loop)
        picked = [files[i] for i in idx]
        closing = files[-1] if loop and len(files) > len(names) else None
        rgbs = []
        for f in picked + ([closing] if closing is not None else []):
            with Image.open(f) as im:
                rgbs.append(np.asarray(im.convert("RGB")))
        total = len(files)
    frames, info = cut(rgbs, size, key, key_range, ring, align, supersample)
    closing_frame = frames.pop() if closing is not None else None
    finals = [f if supersample == 1 else f.resize(size, Image.LANCZOS) for f in frames]
    frames_dir.mkdir(parents=True, exist_ok=True)
    for f, t in zip(frames, targets):
        if t in write:
            f.save(t)
    seam = seam_report(finals, None if closing_frame is None else
                       (closing_frame if supersample == 1 else closing_frame.resize(size, Image.LANCZOS)))
    # sheet + atlas (art.py sheet's format) and the preview GIF
    sheet_dir.mkdir(parents=True, exist_ok=True)
    base = re.sub(r"_\d+$", "", names[0]) or names[0]
    sheet, atlas = _build_sheet()([(n, f, base) for n, f in zip(names, finals)], None, 2)
    clip_s = clip_seconds(video, start, end)
    ms = int(round(1000.0 / fps)) if fps else (int(round(clip_s * 1000 / len(names))) if clip_s else 100)
    ms = max(MIN_FRAME_MS, ms)
    atlas["meta"]["image"] = f"{sheet_name}.png"
    atlas["meta"]["video"] = {"source": video.name, "frames_in_clip": total, "picked": idx, "loop": loop,
                              "frame_ms": ms, "kept_first": str(first) if keep else None, **info, **seam}
    sheet.save(sheet_dir / f"{sheet_name}.png")
    (sheet_dir / f"{sheet_name}.json").write_text(json.dumps(atlas, indent=1), encoding="utf-8")
    gif = [Image.alpha_composite(Image.new("RGBA", f.size, GIF_BG + (255,)), f).convert("RGB")
           .resize((f.width * 2, f.height * 2), Image.NEAREST) for f in finals]
    gif[0].save(sheet_dir / f"{sheet_name}_preview.gif", save_all=True, append_images=gif[1:], duration=ms, loop=0)
    return {"frames": [str(t) for t in write], "kept_first": str(first) if keep else None,
            "sheet": str(sheet_dir / f"{sheet_name}.png"),
            "atlas": str(sheet_dir / f"{sheet_name}.json"), "gif": str(sheet_dir / f"{sheet_name}_preview.gif"),
            "frame_ms": ms, "picked": idx, "frames_in_clip": total, **info, **seam}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", help="the clip (mp4, webm, mov, gif ...)")
    ap.add_argument("--name", required=True, help="the animation's base name: frames are <name>_00, <name>_01, ...")
    ap.add_argument("--frames", type=int, default=None, help="how many frames (default: the spec's count)")
    ap.add_argument("--size", default=None, help="final frame size WxH (default: the spec's size)")
    ap.add_argument("--spec", default=None, help="a WowCube manifest or an art.json project: size, names, folders")
    ap.add_argument("--workspace", default=None, help="with --spec: the art workspace (as art.py --workspace)")
    ap.add_argument("--out", default=None, help="frames folder (default with --spec: where the pipeline reads them)")
    ap.add_argument("--sheet-dir", default=None, help="sheet, atlas and GIF folder (default: <workspace>/video "
                                                      "with --spec, else the frames folder)")
    ap.add_argument("--key", default="auto", help="background colour: auto (the corners), magenta, green, #RRGGBB")
    ap.add_argument("--key-range", default="40:80", help="colour distance LO:HI over which alpha ramps 0 -> 1")
    ap.add_argument("--ring", type=int, default=1, help="despill: solid edge pixels also recoloured (default 1)")
    ap.add_argument("--align", choices=["center", "bottom"], default="center",
                    help="where the shared crop sits on the canvas (bottom: feet on the frame's bottom edge)")
    ap.add_argument("--supersample", type=int, default=1,
                    help="write the frame PNGs at K x the size (art.py process scales them down); sheet and GIF "
                         "stay at the size")
    ap.add_argument("--once", action="store_true", help="not a loop: the clip's first and last frames are both kept")
    ap.add_argument("--start", type=float, default=None, help="seconds into the clip to start")
    ap.add_argument("--end", type=float, default=None, help="seconds into the clip to stop")
    ap.add_argument("--fps", type=float, default=None, help="preview speed (default: the clip's own pace; max 20)")
    ap.add_argument("--force", action="store_true", help="replace frames that already exist")
    ap.add_argument("--keep-first", action=argparse.BooleanOptionalAction, default=None,
                    help="keep the approved first frame <name>_00 and write only the others (the default when it "
                         "exists); --no-keep-first replaces it with the clip's first frame")
    args = ap.parse_args(argv)

    video = Path(args.video)
    if not video.is_file():
        print(f"ERROR: no clip {video}", file=sys.stderr)
        return 2
    if not re.fullmatch(r"[a-z][a-z0-9_]*", args.name):
        print(f"ERROR: --name {args.name!r}: lower-case letters, digits and '_', starting with a letter",
              file=sys.stderr)
        return 2
    try:
        key = parse_key(args.key)
        key_range = parse_range(args.key_range)
        kind, approved_first = None, None
        if args.start is not None and args.start < 0:
            raise ValueError(f"--start {args.start}: seconds from the clip's start, 0 or more")
        if args.end is not None and args.end <= (args.start or 0.0):
            raise ValueError(f"--end {args.end} must be after --start {args.start or 0}")
        if args.spec:
            names, size, frames_dir, sheet_dir, kind, approved_first = frames_from_spec(
                Path(args.spec), args.name, args.workspace)
            if args.frames is not None and args.frames != len(names):
                raise ValueError(f"--frames {args.frames}, but the spec has {len(names)} frame(s) of {args.name}: "
                                 f"change the spec first, or leave --frames out")
            if args.size and parse_size(args.size) != tuple(size):
                raise ValueError(f"--size {args.size}, but the spec says {size[0]}x{size[1]}: leave --size out")
        else:
            if not args.frames or not args.size or not args.out:
                raise ValueError("without --spec, give --frames, --size and --out")
            names = [f"{args.name}_{i:02d}" for i in range(args.frames)]
            size, frames_dir, sheet_dir = parse_size(args.size), None, None
        if len(names) < 1 or args.supersample < 1:
            raise ValueError("--frames and --supersample must be at least 1")
        if args.out:
            frames_dir, approved_first = Path(args.out), None
        sheet_dir = Path(args.sheet_dir) if args.sheet_dir else (sheet_dir or frames_dir)
    except (ValueError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except SystemExit as e:                        # art_spec.read_json: a spec that is not valid JSON
        print(e, file=sys.stderr)
        return 2
    try:
        res = run(video, names, tuple(size), frames_dir, sheet_dir, key=key, key_range=key_range, ring=args.ring,
                  align=args.align, supersample=args.supersample, loop=not args.once, start=args.start,
                  end=args.end, fps=args.fps, sheet_name=args.name, force=args.force, keep_first=args.keep_first,
                  approved_first=approved_first)
    except FileNotFoundError as e:
        print(f"ERROR: {e} not found: install ffmpeg (it brings ffprobe) and run again", file=sys.stderr)
        return 3
    except FileExistsError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except (RuntimeError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    w, h = size
    print(f"{len(names)} frame(s) {w}x{h} from {res['frames_in_clip']} in the clip (picked {res['picked']}), "
          f"key {res['key']}, crop {res['crop']}")
    if res["kept_first"]:
        print(f"frames: {frames_dir} ({names[1]} .. {names[-1]}); {names[0]} kept: {res['kept_first']} (the approved "
              f"first frame; --no-keep-first replaces it)")
    else:
        print(f"frames: {frames_dir} ({names[0]} .. {names[-1]})")
    print(f"sheet: {res['sheet']}\natlas: {res['atlas']}\npreview: {res['gif']} ({res['frame_ms']} ms per frame)")
    if "seam" in res:
        verdict = "seamless" if res["seam"] <= max(2.0, res["step_median"]) else \
            "VISIBLE JUMP: the clip does not return to its start pose"
        print(f"loop seam {res['seam']:.1f} (typical step {res['step_median']:.1f}): {verdict}")
    else:
        print(f"no loop seam measured (--once, or the clip has no frame to spare); typical step "
              f"{res['step_median']:.1f}")
    if "wrap" in res:
        print(f"loop wrap (last frame back to the first) {res['wrap']:.1f}"
              + ("" if args.once else " - compare with the typical step: much larger = a visible restart"))
    if kind == "cube-manifest":
        print(f'next: art.py process <manifest> --only {",".join(names)}  (give these frames "fit": "canvas" in '
              f'the manifest to keep the filmed motion), then art.py qa')
    elif kind == "art":
        print('next: in art.json give each frame "source": "drawn/<name>.png" (and "fixed_canvas": true), then '
              'art.py process and qa')
    return 0


if __name__ == "__main__":
    sys.exit(main())
