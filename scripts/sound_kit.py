#!/usr/bin/env python3
"""Sound kit: real recorded sounds -> punchy game SFX and music loops in the
exact format the OctaviOS engine plays (22050 Hz mono CBR 32 kbps mp3, no
Xing header, no tags).

Why this exists: pure synthesis (gen_sounds.py) gives placeholder beeps that
players hate. What worked on a shipped WowCube game: CC0 recordings
(OpenGameArt, Kenney, Freesound CC0 - downloaded only after the user approves
the list), layered and mastered per a recipe, plus a synthetic sub thump where
recordings lack low end. Everything is analysed by numbers - never played out
loud on the user's machine.

  python scripts/sound_kit.py inspect <audio...>              duration, peak/mean dB, band energy, envelope
                                                              (wildcards like src/*.mp3 are expanded by the
                                                              script, so PowerShell works too)
  python scripts/sound_kit.py loop <music> --out <dir> [--name music_loop] [--min 8 --max 30]
                                                              cut the most self-similar loop, start on a beat;
                                                              the search needs about max + 9 s of input: a shorter
                                                              track lowers --max to fit (printed), below min + 9 s
                                                              it stops (pass a longer track or a lower --min)
  python scripts/sound_kit.py licences <source folders...>     licence/readme files inside the downloads, flags non-CC0
                                                              (exit 1 unless every one is CC0 / public domain)
  python scripts/sound_kit.py build <recipes.json> --out <sound/assets>
                                                              layer + master + encode every recipe

Recipe file (paths relative to the recipe file):
{
  "sources": {
    "crack": {"file": "src/stone_crack.wav", "trim": 0.02, "end": 0.62, "hp": 160, "decay": 0.22},
    "thud":  {"file": "src/impact_thud02.flac", "trim": 0.05},
    "roar":  {"file": "src/creature_roar.wav", "end": 1.3}
  },
  "synth": {
    "sub":  {"type": "thump", "from_hz": 130, "to_hz": 45, "decay": 0.09, "len": 0.35},
    "body": {"type": "noise", "lp": 1400, "decay": 0.035, "len": 0.16}
  },
  "sounds": {
    "rock_smash": {"layers": [["crack", 0, 1.0], ["sub", 0, 0.9], ["body", 0, 0.45], ["thud", 0.03, 0.9]],
                   "drive": 2.2},
    "boss_roar":  {"layers": [["roar", 0, 1.0, {"pitch": -5}]], "drive": 1.8, "max_len": 1.6}
  }
}
Synth types (all keys optional except type; len in s; notes as "C4", "F#3", "Bb2" or Hz):
  thump    pitch-dropping sine (from_hz, to_hz, decay, len): the sub under an impact
  noise    filtered noise burst (lp, hp, decay, len): body / air of a blast
  tone     one note (note | hz, wave sine|triangle|square|saw, attack, decay, len, slide_to: note|hz, vibrato_hz)
  chord    notes played together (notes [...], wave, attack, decay, len, strum: s between notes)
  arpeggio notes one after another (notes [...], step: s per note, wave, decay, note_len, repeat)
  music    a seamless loop (bpm, chords [[notes], ...], beats_per_chord, pattern arp-up|arp-updown|block,
           bass true|false, melody [note | null per beat, ...], wave, lead_wave): exactly
           len(chords) * beats_per_chord beats long, every note ends inside it, so the file restarts cleanly;
           `build` prints "retrigger every N ticks" for it (set "fade_out": 0 on its sound).
A synthesized sound set ("sound.source": "synth") needs no "sources" at all:
  {"synth": {"ping": {"type": "tone", "note": "E6", "decay": 0.12, "len": 0.3}},
   "sounds": {"catch": {"layers": [["ping", 0, 1.0]]}}}
Source options: trim (silence threshold to cut the lead-in), start/end (s), hp/lp (Hz, 1-pole),
decay (s, exponential fade), gain, pitch (semitones, resample). Layer = [source, offset_s, gain, {opts}].
Sound options: drive (tanh saturation = loud and punchy without clipping), max_len (s), fade_out (s; 0 = none).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

SR = 22050


# ------------------------------------------------------------------------- io
def need_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise SystemExit("ffmpeg is required (Windows: winget install Gyan.FFmpeg)")
    return exe


def load(path: Path, sr: int = SR) -> np.ndarray:
    r = subprocess.run([need_ffmpeg(), "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr),
                        "-f", "s16le", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768


def save(a: np.ndarray, wav: Path, mp3: Path | None) -> None:
    """WAV (for inspection) + the engine mp3: 22050 Hz mono CBR 32k, no Xing, no tags.
    The mp3 starts with ~50 ms of LAME encoder delay that cannot be signalled
    without the Xing/LAME gapless header the engine format omits."""
    pcm = (np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes()
    wav.parent.mkdir(parents=True, exist_ok=True)
    ff = need_ffmpeg()
    subprocess.run([ff, "-v", "error", "-y", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", "-", str(wav)],
                   input=pcm, check=True)
    if mp3 is not None:
        mp3.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([ff, "-v", "error", "-y", "-i", str(wav), "-ar", str(SR), "-ac", "1", "-c:a", "libmp3lame",
                        "-b:a", "32k", "-write_xing", "0", "-id3v2_version", "0", "-write_id3v1", "0",
                        "-map_metadata", "-1", str(mp3)], check=True)


# ------------------------------------------------------------------------- dsp
def hp(a: np.ndarray, fc: float) -> np.ndarray:
    rc = 1 / (2 * np.pi * fc)
    al = rc / (rc + 1 / SR)
    y = np.zeros_like(a)
    p = px = 0.0
    for i, x in enumerate(a):
        p = al * (p + x - px)
        px = x
        y[i] = p
    return y


def lp(a: np.ndarray, fc: float) -> np.ndarray:
    al = (1 / SR) / (1 / (2 * np.pi * fc) + 1 / SR)
    y = np.zeros_like(a)
    p = 0.0
    for i, x in enumerate(a):
        p += al * (x - p)
        y[i] = p
    return y


def pitch(a: np.ndarray, semis: float) -> np.ndarray:
    f = 2 ** (semis / 12)
    idx = np.arange(0, len(a) - 1, f)
    return np.interp(idx, np.arange(len(a)), a).astype(np.float32)


def trim_lead(a: np.ndarray, thr: float) -> np.ndarray:
    i = int(np.argmax(np.abs(a) > thr)) if (np.abs(a) > thr).any() else 0
    return a[max(0, i - int(0.004 * SR)):]


def fade(a: np.ndarray, fin: float = 0.003, fout: float = 0.04) -> np.ndarray:
    a = a.copy()
    n1, n2 = int(fin * SR), min(len(a), int(fout * SR))
    if n1:
        a[:n1] *= np.linspace(0, 1, n1)
    if n2:
        a[-n2:] *= np.linspace(1, 0, n2) ** 2
    return a


def master(a: np.ndarray, drive: float = 1.0, peak: float = 0.97) -> np.ndarray:
    if drive > 0:
        a = np.tanh(a * drive) / np.tanh(drive)
    return (a / (np.abs(a).max() + 1e-9) * peak).astype(np.float32)


def shape(a: np.ndarray, o: dict) -> np.ndarray:
    if "trim" in o:
        a = trim_lead(a, float(o["trim"]))
    s, e = o.get("start"), o.get("end")
    if s is not None or e is not None:
        a = a[int((s or 0) * SR):(int(e * SR) if e is not None else None)]
    if o.get("hp"):
        a = hp(a, float(o["hp"]))
    if o.get("lp"):
        a = lp(a, float(o["lp"]))
    if o.get("pitch"):
        a = pitch(a, float(o["pitch"]))
    if o.get("decay"):
        a = a * np.exp(-np.arange(len(a)) / SR / float(o["decay"]))
    if o.get("gain"):
        a = a * float(o["gain"])
    return a.astype(np.float32)


_NOTE_RE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d)$")
_SEMI = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}


def note_hz(v) -> float:
    """'A4' = 440 Hz, 'C#5', 'Bb3', or a number (Hz)."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    m = _NOTE_RE.match(str(v).strip())
    if not m:
        raise SystemExit(f"bad note {v!r} (use e.g. C4, F#3, Bb2 or a frequency in Hz)")
    semi = _SEMI[m.group(1).lower()] + {"#": 1, "b": -1, "": 0}[m.group(2)] + 12 * (int(m.group(3)) + 1)
    return 440.0 * 2 ** ((semi - 69) / 12)


def osc(wave: str, freq, n: int) -> np.ndarray:
    """One oscillator; freq is a number or a per-sample array (slides, vibrato)."""
    ph = np.cumsum(np.broadcast_to(np.asarray(freq, np.float64), (n,))) / SR
    if n:
        ph = ph - ph[0]
    if wave == "sine":
        return np.sin(2 * np.pi * ph).astype(np.float32)
    frac = ph % 1.0
    if wave == "triangle":
        return (4 * np.abs(frac - 0.5) - 1).astype(np.float32)
    if wave == "square":
        return np.where(frac < 0.5, 0.6, -0.6).astype(np.float32)   # about the loudness of the sine
    if wave == "saw":
        return (0.7 * (2 * frac - 1)).astype(np.float32)
    raise SystemExit(f"unknown wave {wave!r} (sine, triangle, square, saw)")


def env(n: int, attack: float, decay: float) -> np.ndarray:
    """Attack ramp, then exponential decay; the last 5 ms always fade to zero (no click at the end)."""
    t = np.arange(n) / SR
    e = np.exp(-t / max(decay, 1e-4)) if decay else np.ones(n)
    na = min(n, int(attack * SR))
    if na:
        e[:na] *= np.linspace(0, 1, na)
    nz = min(n, int(0.005 * SR))
    if nz:
        e[-nz:] *= np.linspace(1, 0, nz)
    return e.astype(np.float32)


def note(hz: float, length: float, wave: str = "triangle", attack: float = 0.005, decay: float = 0.25,
         slide_to: float | None = None, vibrato_hz: float = 0.0) -> np.ndarray:
    n = max(1, int(length * SR))
    f = np.full(n, hz, np.float64)
    if slide_to:
        f = hz * (slide_to / hz) ** (np.arange(n) / n)
    if vibrato_hz:
        f = f * (1 + 0.012 * np.sin(2 * np.pi * vibrato_hz * np.arange(n) / SR))
    return osc(wave, f, n) * env(n, attack, decay)


def _place(y: np.ndarray, a: np.ndarray, k: int, gain: float = 1.0) -> None:
    a = a[:max(0, len(y) - k)]
    y[k:k + len(a)] += a * gain


def music(o: dict) -> np.ndarray:
    """A short seamless loop from a chord progression: a bass note per chord, an arpeggio on eighths or
    block chords on beats, an optional melody (one note or null per beat). Exact length; every note ends
    inside the loop, so a retrigger at the end restarts it without a gap or an overlap."""
    bpm = float(o.get("bpm", 100))
    chords = o.get("chords") or [["C4", "E4", "G4"], ["A3", "C4", "E4"], ["F3", "A3", "C4"], ["G3", "B3", "D4"]]
    bpc = int(o.get("beats_per_chord", 4))
    beat = 60.0 / bpm
    n = int(round(len(chords) * bpc * beat * SR))
    y = np.zeros(n, np.float32)
    wave, lead = o.get("wave", "triangle"), o.get("lead_wave", "square")
    pattern = o.get("pattern", "arp-up")
    if pattern not in ("arp-up", "arp-updown", "block"):
        raise SystemExit(f"unknown music pattern {pattern!r} (arp-up, arp-updown, block)")
    for ci, ch in enumerate(chords):
        hz = [note_hz(x) for x in ch]
        t0 = ci * bpc * beat
        if o.get("bass", True):
            _place(y, note(min(hz) / 2, bpc * beat * 0.95, "sine", 0.01, bpc * beat * 0.5), int(t0 * SR), 0.55)
        if pattern == "block":
            for b in range(bpc):
                for h in hz:
                    _place(y, note(h, beat * 0.9, wave, 0.01, beat * 0.35), int((t0 + b * beat) * SR), 0.22)
        else:
            seq = hz + (hz[-2:0:-1] if pattern == "arp-updown" else [])
            step = beat / 2
            for k in range(bpc * 2):
                _place(y, note(seq[k % len(seq)], step * 0.95, wave, 0.004, step * 0.6),
                       int((t0 + k * step) * SR), 0.3)
    for b, m in enumerate((o.get("melody") or [])[:len(chords) * bpc]):
        if m:
            _place(y, note(note_hz(m), beat * 0.9, lead, 0.01, beat * 0.5, vibrato_hz=5.0), int(b * beat * SR), 0.2)
    return y


def synth(o: dict, seed: int = 7) -> np.ndarray:
    kind = o.get("type")
    if kind == "music":
        return music(o)
    n = int(float(o.get("len", 0.3)) * SR)
    t = np.arange(n) / SR
    wave = o.get("wave", "triangle")
    if kind == "tone":
        hz = note_hz(o.get("note", o.get("hz", "A5")))
        return note(hz, float(o.get("len", 0.3)), wave, float(o.get("attack", 0.005)), float(o.get("decay", 0.15)),
                    note_hz(o["slide_to"]) if o.get("slide_to") else None, float(o.get("vibrato_hz", 0)))
    if kind == "chord":
        notes, strum = o.get("notes") or ["C5", "E5", "G5"], float(o.get("strum", 0))
        ln = float(o.get("len", 0.6))
        y = np.zeros(int((ln + strum * (len(notes) - 1)) * SR) + 1, np.float32)
        for i, x in enumerate(notes):
            _place(y, note(note_hz(x), ln, wave, float(o.get("attack", 0.005)), float(o.get("decay", 0.35))),
                   int(i * strum * SR), 0.5)
        return y
    if kind == "arpeggio":
        notes = (o.get("notes") or ["C5", "E5", "G5", "C6"]) * int(o.get("repeat", 1))
        step = float(o.get("step", 0.07))
        nl = float(o.get("note_len", step * 2))
        y = np.zeros(int((step * (len(notes) - 1) + nl) * SR) + 1, np.float32)
        for i, x in enumerate(notes):
            _place(y, note(note_hz(x), nl, wave, 0.003, float(o.get("decay", nl / 2))), int(i * step * SR), 0.6)
        return y
    if kind == "thump":       # pitch-dropping sine: chest punch under a gunshot / impact
        f0, f1, d = float(o.get("from_hz", 130)), float(o.get("to_hz", 45)), float(o.get("decay", 0.09))
        freq = f1 + (f0 - f1) * np.exp(-t / 0.035)
        return (np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t / d)).astype(np.float32)
    if kind == "noise":       # filtered noise burst: body / air of a blast
        x = np.random.default_rng(seed).standard_normal(n).astype(np.float32)
        if o.get("lp"):
            x = lp(x, float(o["lp"]))
        if o.get("hp"):
            x = hp(x, float(o["hp"]))
        return (x * np.exp(-t / float(o.get("decay", 0.04)))).astype(np.float32)
    raise SystemExit(f"unknown synth type {kind!r} (thump, noise, tone, chord, arpeggio, music)")


def mix(layers: list[tuple[np.ndarray, float, float]]) -> np.ndarray:
    n = max(int(off * SR) + len(s) for s, off, g in layers)
    y = np.zeros(n, np.float32)
    for s, off, g in layers:
        k = int(off * SR)
        y[k:k + len(s)] += s * g
    return y


# ------------------------------------------------------------------------- analysis
def describe(a: np.ndarray) -> str:
    dur = len(a) / SR
    peak = 20 * np.log10(np.abs(a).max() + 1e-9)
    rms = 20 * np.log10(np.sqrt((a ** 2).mean()) + 1e-9)
    sp = np.abs(np.fft.rfft(a[:SR * 4]))
    fq = np.fft.rfftfreq(min(len(a), SR * 4), 1 / SR)
    tot = sp.sum() + 1e-9
    bands = [(0, 150), (150, 500), (500, 2000), (2000, 6000), (6000, 11025)]
    share = " ".join(f"{lo}-{hi}:{sp[(fq >= lo) & (fq < hi)].sum() / tot:.0%}" for lo, hi in bands)
    hop = max(1, len(a) // 40)
    env = [np.abs(a[i:i + hop]).max() for i in range(0, len(a), hop)][:40]
    bars = " .:-=+*#%@"
    line = "".join(bars[min(9, int(e * 9.99))] for e in env)
    return f"{dur:6.2f}s peak {peak:5.1f} dB rms {rms:5.1f} dB | {share} | [{line}]"


def find_loop(m: np.ndarray, lmin: float, lmax: float) -> tuple[float, float, float]:
    """Most self-similar (start, length) by onset-envelope correlation, then
    the start snapped to the strongest onset nearby.

    The onset envelope (5 ms frames) of an 8 s window starting at s is
    correlated (Pearson) with the window starting at s + L for every loop
    length L in [lmin, lmax] at once (np.correlate over the sliding windows,
    rolling mean/std from cumulative sums), for starts every 50 ms."""
    hop = 55                      # 5 ms at 11025 Hz
    x = m[::2] if SR == 22050 else m
    n = (len(x) - hop) // hop
    if n <= 0:
        raise SystemExit("audio too short to search for a loop")
    frames = x[:n * hop].reshape(n, hop)
    env = np.sqrt((frames ** 2).mean(axis=1))
    on = np.maximum(0, np.diff(np.log(env + 1e-4))).astype(np.float64)
    W = int(8 / 0.005)
    l0, l1 = int(lmin / 0.005), int(lmax / 0.005)
    first = int(1 / 0.005)
    last = len(on) - W - l1
    if last <= first:
        raise SystemExit(f"audio too short for loops up to {lmax}s (need about {lmax + 9:.0f}s)")
    c1 = np.concatenate([[0.0], np.cumsum(on)])
    c2 = np.concatenate([[0.0], np.cumsum(on * on)])
    starts = np.arange(len(on) - W + 1)
    mean_w = (c1[starts + W] - c1[starts]) / W
    std_w = np.sqrt(np.maximum((c2[starts + W] - c2[starts]) / W - mean_w ** 2, 0)) + 1e-9
    best = (-1.0, 0, 0)
    for s in range(first, last, 10):
        a = on[s:s + W]
        a = (a - a.mean()) / (a.std() + 1e-9)
        seg = on[s + l0:s + l1 + W]
        dots = np.correlate(seg, a, "valid")          # sum(a * b) for b at every L in [l0, l1]
        idx = s + l0 + np.arange(len(dots))
        corr = (dots / W - a.mean() * mean_w[idx]) / std_w[idx]   # a.mean() == 0 after z-scoring
        k = int(np.argmax(corr))
        if corr[k] > best[0]:
            best = (float(corr[k]), s, l0 + k)
    c, s, L = best
    s_samples = int(s * 0.005 * SR)
    win = np.abs(m[s_samples:s_samples + int(0.3 * SR)])
    s_samples += int(np.argmax(np.convolve(win, np.ones(64), "same"))) - int(0.01 * SR)
    return max(0, s_samples) / SR, L * 0.005, c


# ------------------------------------------------------------------------- commands
# Licence/readme-like files inside downloaded packs. Every plain-text document
# is read whatever its name (packs ship "info.txt", "Attrib.nfo"); other
# files only when the name says licence/readme/credits/....
LICENCE_HINTS = ("licen", "copying", "readme", "read_me", "read me", "credit", "creativecommons", "attrib",
                 "source", "notice", "terms", "legal", "copyright", "eula", "author", "info", "about", "usage")
DOC_SUFFIXES = (".txt", ".md", ".markdown", ".rst", ".text", ".nfo", ".htm", ".html", ".rtf", ".license", ".lic")
HINTED_SUFFIXES = ("", ".json", ".xml", ".yaml", ".yml", ".csv", ".ini", ".cfg", ".pdf", ".doc", ".docx", ".odt")
LICENCE_MAX_BYTES = 2_000_000

# Most restrictive first: a file naming several licences gets the strictest.
_LICENCE_PATTERNS = (
    ("CC-BY-NC", (r"\bby[\s_-]*nc\b", r"licenses/by-nc",
                  # "commercial and non-commercial use" is a permission, not a restriction
                  r"(?<!commercial and )(?<!commercial or )(?<!commercial & )(?<!commercial/)"
                  r"non[\s_-]?commercial(?![\s_-]*(?:and|or|&|/)\s*commercial)")),
    ("CC-BY-ND", (r"\bby[\s_-]*nd\b", r"licenses/by-nd", r"no[\s_-]?deriv")),
    ("CC-BY-SA", (r"\bby[\s_-]*sa\b", r"licenses/by-sa", r"share[\s_-]?alike")),
    ("GPL", (r"\b[al]?gpl(?:v?\d)?\b", r"gnu (?:lesser |affero )?general public licen")),
    ("CC-BY", (r"\bcc[\s_-]*by\b", r"licenses/by/", r"creative\s+commons\s+attribution",
               r"\battribution\s+(?:\d|international|unported|licen)",
               r"(?<!no )(?<!not )\battribution\s+(?:is\s+)?required", r"\bmust\s+(?:give\s+)?credit")),
    ("CC0", (r"\bcc[\s_-]?0\b", r"\bcc[\s_-]?zero\b", r"creative\s+commons\s+zero", r"publicdomain/zero",
             r"\bpublic[\s_-]+domain\b", r"\bunlicense\b")),
)


def classify_licence(text: str) -> str:
    """One of CC-BY-NC, CC-BY-ND, CC-BY-SA, GPL, CC-BY, CC0, "?" (unknown).
    The strictest licence the text names wins: "CC0 except the music (CC-BY)"
    is CC-BY. Only a text that names CC0 / public domain and nothing stricter
    is CC0; a text naming no licence at all is unknown."""
    low = " ".join(text.lower().split())
    for kind, pats in _LICENCE_PATTERNS:
        if any(re.search(p, low) for p in pats):
            return kind
    return "?"


def _licence_candidates(root: Path):
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        suf, name = p.suffix.lower(), p.name.lower()
        if suf in DOC_SUFFIXES or (suf in HINTED_SUFFIXES and any(h in name for h in LICENCE_HINTS)):
            yield p


def cmd_licences(args) -> int:
    """Print every licence/readme/credits file inside the given source folders
    (or next to the given files) with its licence class, and exit non-zero
    unless every one is CC0 / public domain. A store page can say CC0 while the
    archive ships a CC-BY notice (it happened): the file in the archive is what
    the proposal must quote.

    Exit 0 = every file found is CC0; 1 = something is CC-BY / SA / NC / ND /
    GPL / unknown / unreadable, or no licence file was found at all."""
    seen, flagged = set(), 0
    for f in args.files:
        root = Path(f)
        root = root if root.is_dir() else root.parent
        for p in _licence_candidates(root):
            if p in seen:
                continue
            seen.add(p)
            if p.suffix.lower() in (".pdf", ".doc", ".docx", ".odt") or p.stat().st_size > LICENCE_MAX_BYTES:
                kind, head = "?", "(not plain text: open and read it yourself)"
            else:
                text = p.read_text(encoding="utf-8", errors="replace")
                kind = classify_licence(text)
                head = " ".join(text.split())[:220]
            if kind != "CC0":
                flagged += 1
            print(f"[{kind}] {p}")
            print(f"      {head}")
    if not seen:
        print("NOT CLEARED: no licence/readme files found next to the sources: quote the store page, keep its URL "
              "and confirm the licence by hand")
        return 1
    if flagged:
        print(f"NOT CLEARED: {flagged} file(s) are not CC0 ([CC-BY] attribution, [CC-BY-SA] share-alike, "
              f"[CC-BY-NC] non-commercial: not usable in a shipped game, [CC-BY-ND] no derivatives: no "
              f"layering/editing, [GPL], [?] unknown: read it). Tell the user before using these sounds; "
              f"attribution goes into sound/CREDITS.md")
        return 1
    print(f"OK: all {len(seen)} licence file(s) are CC0 / public domain")
    return 0


def cmd_inspect(args) -> int:
    for f in args.files:
        print(f"{Path(f).name:28s} {describe(load(Path(f)))}")
    return 0


def fit_loop_range(dur: float, lmin: float, lmax: float) -> tuple[float, float]:
    """The search compares an 8 s window 1 s in with the window one loop later, so it needs about
    lmax + 9 s of audio. A shorter track lowers lmax to what it holds; below lmin + 9 s it stops."""
    room = dur - 9.2
    if room >= lmax:
        return lmin, lmax
    if room < lmin:
        raise SystemExit(f"track is {dur:.1f}s: loops of {lmin:g}-{lmax:g}s need about {lmax + 9:.0f}s of audio "
                         f"(at least {lmin + 9:.0f}s for --min {lmin:g}). Use a longer track, a lower --min "
                         f"(at most {max(1.0, room):.0f} here), or a synthesized loop (build, synth type music)")
    print(f"note: track is {dur:.1f}s, so --max {lmax:g} is lowered to {room:.1f}s (the search needs max + ~9 s)")
    return lmin, room


def cmd_loop(args) -> int:
    m = load(Path(args.files[0]))
    lmin, lmax = fit_loop_range(len(m) / SR, args.min, args.max)
    start, length, corr = find_loop(m, lmin, lmax)
    s, L = int(start * SR), int(length * SR)
    loop = m[s:s + L].copy()
    xf = int(0.03 * SR)
    if s + L + xf <= len(m):      # fold the next bar's head into the tail: smoother wrap on retrigger
        loop[-xf:] = loop[-xf:] * np.linspace(1, 0, xf) + m[s + L:s + L + xf] * np.linspace(0, 1, xf)
    loop = loop / (np.abs(loop).max() + 1e-9) * 0.9
    out = Path(args.out)
    save(loop.astype(np.float32), Path(args.wav_dir or out.parent / "_wav") / f"{args.name}.wav", out / f"{args.name}.mp3")
    ticks = round(length * 20)
    print(f"loop {args.name}: start {start:.3f}s length {length:.3f}s (self-similarity {corr:.2f}) "
          f"-> retrigger every {ticks} ticks at 20 Hz; {describe(loop)}")
    return 0


def cmd_build(args) -> int:
    rf = Path(args.files[0]).resolve()
    rec = json.loads(rf.read_text(encoding="utf-8-sig"))
    base = rf.parent
    src = {k: shape(load(base / v["file"]), v) for k, v in rec.get("sources", {}).items()}
    synth_spec = rec.get("synth", {})
    src.update({k: synth(v) for k, v in synth_spec.items()})
    out = Path(args.out)
    for name, s in rec["sounds"].items():
        missing = [lay[0] for lay in s["layers"] if lay[0] not in src]
        if missing:
            raise SystemExit(f"{name}: unknown layer(s) {missing} (not in sources or synth)")
        layers = []
        for lay in s["layers"]:
            nm, off, g = lay[0], float(lay[1]), float(lay[2])
            a = src[nm]
            if len(lay) > 3:
                a = shape(a, lay[3])
            layers.append((a, off, g))
        y = mix(layers)
        if s.get("max_len"):
            y = y[:int(float(s["max_len"]) * SR)]
        y = fade(master(y, float(s.get("drive", 1.0))), fout=float(s.get("fade_out", 0.04)))
        mp3 = out / f"{name}.mp3"
        save(y, Path(args.wav_dir or out.parent / "_wav") / f"{name}.wav", mp3)
        loop = any(synth_spec.get(lay[0], {}).get("type") == "music" for lay in s["layers"])
        print(f"{name:16s} {describe(y)}  {mp3.stat().st_size} B"
              + (f"  -> retrigger every {round(len(y) / SR * 20)} ticks at 20 Hz" if loop else ""))
    return 0


_GLOB_CHARS = set("*?[")


def expand_files(patterns: list[str]) -> list[str]:
    """Expand wildcards ourselves: PowerShell and cmd hand `*.mp3` to python
    literally (only POSIX shells expand it). A path that exists as written is
    kept as is (so 'take [1].wav' is never treated as a pattern); a pattern
    expands to its matches in sorted order; a pattern matching nothing is an
    error, never silently dropped."""
    import glob
    out: list[str] = []
    for pat in patterns:
        if Path(pat).exists() or not (_GLOB_CHARS & set(pat)):
            out.append(pat)
            continue
        hits = sorted(glob.glob(pat, recursive=True))
        if not hits:
            raise SystemExit(f"no file matches {pat!r}")
        out += hits
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["inspect", "loop", "build", "licences"])
    ap.add_argument("files", nargs="+", help="audio files (or a recipe for build); wildcards such as "
                                             "src/*.mp3 are expanded here, on every shell")
    ap.add_argument("--out", default="sound/assets")
    ap.add_argument("--wav-dir", default=None, help="where the inspection WAVs go (default <out>/../_wav, kept out of the pack)")
    ap.add_argument("--name", default="music_loop")
    ap.add_argument("--min", type=float, default=8.0)
    ap.add_argument("--max", type=float, default=30.0)
    args = ap.parse_args(argv)
    args.files = expand_files(args.files)
    return {"inspect": cmd_inspect, "loop": cmd_loop, "build": cmd_build, "licences": cmd_licences}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
