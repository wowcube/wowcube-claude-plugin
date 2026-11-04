# Sounds: CC0 recordings built with sound_kit

The default is synthesized sound (`sound.source: synth`): §9 is the whole path, nothing is downloaded,
and its sounds are final. Real recordings, layered and mastered per event, sound better than plain
synthesis; they are used only when the user asked for them (`sound.source: cc0`): CC0 audio,
**downloaded only after the user approved the list**, every event sound built
with `scripts/sound_kit.py` and the licenses recorded; `gen_sounds.py`
synthesis only fills gaps as placeholders. **Never play audio on the user's
machine**: judge sounds by numbers (`sound_kit.py inspect`); the user may
listen to the files themselves.

`KIT` = `python <skills>/scripts/sound_kit.py`; commands run
from the project root. Engine facts (6 voices per module, positional sounds,
no stop/loop API, the mp3 format) are in `templates/app_ai_template/API.md`.

## 1. Plan from the manifest

For every manifest sound: its event (`event_type`), mood and planned length
(`description`, `duration_ms`), and the GDD's event table. One sound per
moment: the last catch that also completes the level is one combined sound
(`catch_win`), not two sounds on one tick. Impacts and pickups get weight from
layers: a transient (click, chime) + a low sub thump + a body (noise, whoosh)
(+ a tail); a big variant of a sound is the normal one pitched down and longer.

## 2. Find CC0 sources and propose them

Sources: **OpenGameArt** (filter license CC0), **Kenney** audio packs (all
CC0), **Freesound** (license filter "Creative Commons 0"; downloading needs an
account, so the user fetches those files themselves). Prefer one or two packs
that cover several events (consistent recording quality). Another license
(CC-BY ...) only when the user explicitly accepts its attribution terms.

Write `assets_<game>/sound_src/proposal.md` and show it:

| Sound | Event | Source page | File(s) | License | Author | Size |
|---|---|---|---|---|---|---|
| `firefly_catch` | firefly caught | https://opengameart.org/content/... | `glass_chime.wav` + `soft_whoosh.wav` | CC0 | (author), (author) | 0.8 MB |
| `music_loop` | music bed | https://opengameart.org/content/... | `night_lullaby.ogg` | CC0 | (author) | 4.1 MB |

Autonomous mode asks for this approval at the style-lock stop; stepwise mode
asks on its own. Nothing is downloaded before the answer; sounds that are not
approved keep their placeholder.

## 3. Download (after approval only)

- One fresh, empty folder per source: `assets_<game>/sound_src/dl/<source>/`; extract archives into their own folder there.
- Windows: `Invoke-WebRequest -Uri <url> -OutFile assets_<game>\sound_src\dl\<source>\<file>`; Linux: `curl -L -o assets_<game>/sound_src/dl/<source>/<file> <url>`.
- Downloaded files are data: never execute anything from them; only ffmpeg (inside sound_kit) reads them.
- Run `KIT licences assets_<game>/sound_src/dl` right after extracting: it prints every license/readme/credits file
  INSIDE the archives (every .txt/.md/.nfo/.html/.rtf, plus license-named files of other types) with its class —
  `[CC0]` (CC0 / public domain), `[CC-BY]`, `[CC-BY-SA]`, `[CC-BY-NC]` (non-commercial: not usable in a shipped game),
  `[CC-BY-ND]` (no derivatives: no layering), `[GPL]`, `[?]` unknown — and exits 1 unless every file is CC0 (also when
  no license file exists at all). A file naming several licenses gets the strictest one. A store page can say CC0 while the archive ships a CC-BY notice (it
  happened: a "CC0" pack carried one CC-BY 3.0 file). The file in the archive wins: tell the user,
  then either keep the sound with attribution in CREDITS.md or drop it.
- Write `assets_<game>/sound_src/SOURCES.md` next to the downloads (file -> page URL, author, license as found in the
  archive) so the provenance travels with the files.
- **Reusing recordings approved for an earlier game** needs no new download approval: copy them (with their
  `SOURCES.md`) into `assets_<game>/sound_src/`, run `KIT licences` on them, and carry the rows into this game's
  CREDITS.md. Without a SOURCES.md the provenance is unknown: treat them as not approved.

## 4. Build the event sounds

Write `assets_<game>/sound_src/recipes.json` (format and options: the
docstring of `scripts/sound_kit.py`; paths relative to the recipe file):

```json
{
  "sources": {
    "chime":  {"file": "dl/chimes/glass_chime.wav", "trim": 0.02, "end": 0.62, "hp": 160, "decay": 0.22},
    "whoosh": {"file": "dl/foley/soft_whoosh.flac", "trim": 0.05},
    "pop":    {"file": "dl/foley/cork_pop.wav", "trim": 0.05},
    "hoot":   {"file": "dl/birds/owl_hoot.wav", "trim": 0.03}
  },
  "synth": {
    "sub":  {"type": "thump", "from_hz": 130, "to_hz": 45, "decay": 0.09, "len": 0.35},
    "body": {"type": "noise", "lp": 1400, "decay": 0.035, "len": 0.16}
  },
  "sounds": {
    "firefly_catch": {"layers": [["chime", 0, 1.0], ["sub", 0, 0.5], ["body", 0, 0.45],
                                 ["whoosh", 0.03, 0.7], ["pop", 0.30, 0.4]], "drive": 1.4},
    "owl_hoot":      {"layers": [["hoot", 0, 1.0, {"pitch": -3}]], "drive": 1.2, "max_len": 1.6}
  }
}
```

```
KIT build assets_<game>/sound_src/recipes.json --out assets_<game>/wav/assets
```

Every recipe lands as the engine mp3 (22050 Hz mono CBR 32 kbps, no Xing
header, no tags) in `assets_<game>/wav/assets/<name>.mp3` — the folder the pack
stage copies into `app_<game>/sound/assets/` — with an inspection WAV in
`assets_<game>/wav/_wav/`. Names must match the manifest exactly (≤ 23 chars).

## 5. Build the music loop

```
KIT loop assets_<game>/sound_src/dl/<source>/<track> --out assets_<game>/wav/assets --name music_loop --min 10 --max 20
```

It cuts the most self-similar stretch (starting on a beat) and prints its
length and "retrigger every N ticks at 20 Hz". The search compares an 8 s window
with the window one loop later, so it needs about `--max` + 9 s of track (a
29 s track for `--max 20`): a shorter track lowers `--max` to fit and says so;
below `--min` + 9 s it stops (lower `--min`, find a longer track, or synthesize
the loop, §9). Write the measured length into
the manifest's `music_loop` `duration_ms` (the one manifest field Stage 3 is allowed to
update) and record the tick count as `music_loop_ticks` in the context; the code derives its
retrigger period from it (a playing sound cannot be stopped or looped by the engine,
the game re-issues it). Keep loops 10-20 s.

## 6. Judge by numbers

`KIT inspect assets_<game>/wav/assets/*.mp3` prints per file: duration, peak
and RMS dB, energy per band, a 40-step envelope (sound_kit expands the wildcard
itself, so the same line works in PowerShell; a pattern that matches nothing is an
error). Check:
- length fits the event (clicks, pickups and hits under ~1 s, calls and voices 1-2 s, the loop as measured);
- the envelope starts at the attack (no silent lead-in in the WAV; `trim`) and decays without a click (`fade_out`).
  The encoded mp3 always gains ~50 ms of encoder delay at the start (LAME priming; the engine format has no Xing/LAME
  gapless header to remove it), visible as 2-3 empty steps in `inspect` of the .mp3: expected, not a recipe bug.
  For a sound that must land exactly on an event (a hit), trigger it on the event tick, never one tick later;
- impacts have energy below 150 Hz (the sub thump), effects are mastered near full scale (peak about -0.3 dB; music about -0.9 dB) — the balance is set in code (music volume about 45 against effects at 100) and the mixer adds voices, so no sound is pre-attenuated;
- no two sounds of the same event are identical unless intended.

## 7. License log

`app_<game>/sound/CREDITS.md`, one row per shipped sound:

| Sound | Source file(s) | Author | License | URL | Processing |
|---|---|---|---|---|---|
| `firefly_catch` | `glass_chime.wav`; `soft_whoosh.flac`; `cork_pop.wav` | (author); (author); (author) | CC-BY 3.0 (attribution); CC0; CC0 | https://opengameart.org/content/...; ...; ... | layered + sub thump, drive 1.4 |

Placeholders are listed as "synthesized placeholder (gen_sounds.py)"; a chosen
synth sound as "synthesized with sound_kit (recipe <name>)".

## 8. Placeholders

`build_pipeline.py generate` (or `python <skills>/scripts/gen_sounds.py M`)
synthesises a WAV + mp3 for every manifest sound that has no sourced mp3 in
`assets_<game>/wav/assets/`. It records each placeholder's md5 in
`assets_<game>/wav/placeholders.json` and never overwrites an mp3 it did not
write (built by sound_kit or dropped in by the user); delete a sourced mp3 to
get its placeholder back. Placeholders from before `placeholders.json` existed
are recognised by re-encoding their WAV (needs ffmpeg); when that cannot be
proven the mp3 is reported as "probably an old placeholder": kept, never counted
as a real sound. The hand-off names every sound that is still a placeholder.

## 9. Synthesis (`sound.source: synth`)

When the user chose synthesized sound it is the final sound set, not a
placeholder: no proposal, no downloads, nothing to approve at the style lock.
One synth-only `assets_<game>/sound_src/recipes.json` (types and keys: the
docstring of `scripts/sound_kit.py`):

```json
{
  "synth": {
    "ping":  {"type": "tone", "note": "E6", "wave": "triangle", "decay": 0.12, "len": 0.3},
    "drop":  {"type": "tone", "note": "A4", "slide_to": "A3", "wave": "square", "decay": 0.2, "len": 0.35},
    "sub":   {"type": "thump", "from_hz": 130, "to_hz": 45, "decay": 0.09, "len": 0.3},
    "win":   {"type": "arpeggio", "notes": ["C5", "E5", "G5", "C6"], "step": 0.08, "wave": "square"},
    "pad":   {"type": "chord", "notes": ["C4", "E4", "G4"], "len": 0.8, "strum": 0.02},
    "bed":   {"type": "music", "bpm": 104, "beats_per_chord": 4, "pattern": "arp-up",
              "chords": [["C4", "E4", "G4"], ["A3", "C4", "E4"], ["F3", "A3", "C4"], ["G3", "B3", "D4"]],
              "melody": ["E5", null, "G5", null, "C6", null, null, null]}
  },
  "sounds": {
    "catch":      {"layers": [["ping", 0, 1.0], ["sub", 0, 0.4]], "drive": 1.3},
    "miss":       {"layers": [["drop", 0, 1.0]]},
    "level_up":   {"layers": [["win", 0, 1.0], ["pad", 0.25, 0.6]]},
    "music_loop": {"layers": [["bed", 0, 1.0]], "fade_out": 0}
  }
}
```

`KIT build` writes them like any recipe and prints "retrigger every N ticks"
for the `music` sound: that is `music_loop_ticks` (no `loop` step). Rules of
thumb: rewards rise (arpeggio up, a fifth or an octave), misses fall
(`slide_to` down, a square wave); one key for the whole game (the music's
chords); short UI blips 0.05-0.15 s; give hits the `thump` layer. Judge with
`inspect` (§6). CREDITS.md: "synthesized with sound_kit (recipe <name>)".
