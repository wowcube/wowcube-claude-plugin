---
name: wowcube-tools
description: >-
  The WowCube toolbox without stages or gates, for developers who already have a game
  or a build: install the bundled build checker and check a game with it (hidden runs,
  frames of all 24 screens), repack assets with a version bump and a device .oct, verify
  or inspect an .oct, make an install link and QR code for the phone (the game file goes
  to WowCube's servers), compare builds, undo the last change, cut a sprite sheet into
  sprites, inspect sounds and their licences, record a demo video. Use when the profile's entry
  mode is "tools", or for single requests like "build the .oct", "repack and bump the
  version", "verify this .oct", "put it on my cube", "give me the QR code", "compare
  these two builds", "check these sounds" (in any language). Game design and
  implementation go through cube_orchestrator.
---

# WowCube tools

One request, one tool, a short report. No stages, no style lock, no reviewers. The safety rules still
hold in full: `<skills>/skills/cube_orchestrator/references/AGENT_SAFETY.md` (no windows over the
user's screen, no audio, PID-only stops, an install link and QR code only after the user's yes, no commits
unasked).

**Never mention the simulator to a user unless they ask about it directly**, developers included: it is
the internal build checker (tool and file names below are for you, not for the user's ears). Say what is
checked ("the game builds and all 24 screens look right"), never offer it as a way to play or to look at
the game.

`<skills>` = the folder two levels above this SKILL.md (the plugin root; `${CLAUDE_PLUGIN_ROOT}` when the host exports it); resolve it on every entry, never store it. `<app>` =
the game folder (`app_<game>/`, one `.target` marker, `src/app_metadata.h`); `<ws>` = the folder that
holds it. First run of the day: `<skills>/scripts/check_env.ps1` / `check_env.sh` (exit 0 = ready; it
installs nothing; installs follow the one-time environment approval).

| Task | Command | Notes |
|---|---|---|
| Get the simulator (once) | `<skills>\tools\sim\get_sim.ps1` / `tools/sim/get_sim.sh` (the prebuilt simulator this plugin carries (about 6 MB on Windows; no download, no GitHub, nothing to build)) | Exit 0 = `~/.wowcube/sim/<version>/<os>/wowcube-sim` answers `--version`. Installing: only after the user agreed |
| Build the game's plugin | `<skills>\tools\sim\build_game.ps1 -AppDir <app>` / `tools/sim/build_game.sh <app>` | After every code change; the simulator refuses an older plugin |
| Check the game without a window | `tools/sim/run_hidden.ps1 -AppDir <app> -Seconds 20 -EveryMs 1000` / `run_hidden.sh <app> --seconds 20 --every-ms 1000`: frames of all 24 screens, no audio (`cube_orchestrator/references/VISUAL_GATE.md`, "Build, run, look") | Exit 0 only when the timed run completed; look at the PNGs before saying anything about them |
| Drive a running hidden instance | its control socket (`cube_orchestrator/SIM_MCP.md`) | Only an instance this session started |
| Repack + version bump + device `.oct` | `python <skills>/scripts/repack_app.py --app-dir <app>` (`--skip-device` = repack and bump only; `--bump minor\|patch`, default minor; `--builder auto\|octpack\|python`; `--out <path>.oct`) | Detects the app's own pack path (manifest, PSD `art/octpack.json`, older layouts); refuses (exit 2, nothing written) when those sources cannot produce every sprite packed today and prints the `extract_art.py` command; bumps the minor version (patch reset to 0; the `.oct` carries exactly the code's version); writes `<ws>/dist/app_<game>.oct` |
| Device `.oct` only | `<skills>/scripts/build_device.ps1 -AppDir <app>` / `build_device.sh --app-dir <app>` | Verifies what it builds; an unverifiable build fails |
| Verify an `.oct` | `python <skills>/scripts/pack_beta.py --verify-oct <file.oct> --app-dir <app> [--code <app>/out/app_<game>.bin]` | Header (title, version, GUID, categories, save size) against the app's defines, the `ico` map, the ARM code |
| Is the pack current? | `python <skills>/scripts/build_pipeline.py pack-status --game <game> --workspace assets_<game> --app-dir <app> --manifest plans/<game>_assets.json` | Manifest apps (the pack record) and `art/octpack.json` apps (`index.bin` newer than its inputs); exit 1 prints what changed |
| Install on the cube (install link + QR code) | `python <skills>/scripts/store_upload.py <ws>/dist/app_<game>.oct --yes --verify` | Ask once first ("Make an install link and a QR code so you can put the game on your cube from your phone? (The game file is sent to WowCube's servers for that.)"); writes `dist/app_<game>_qr.png`, prints the link (keep `?password=`); the user scans it with their phone and the WowCube app installs it on their cube. `cube_orchestrator/references/DELIVERY.md` §3 |
| Undo the last change | `python <skills>/scripts/history.py restore --workspace <ws> --game <game>` (`list` shows the snapshots; `snapshot` before every change) | Then rebuild and check, and `repack_app.py` (the minor version still goes up): `cube_orchestrator/references/RUN_MODES.md`, "History and undo" |
| Cut a sprite sheet into sprites | `python <skills>/skills/cube_art-director/scripts/art.py slice <sheet.png> --cell WxH` (or `--grid CxR`, `--atlas a.json`; `--names a,b,..`) | One named PNG per sprite, empty cells skipped; sizes: `art.py sizes` (`cube_art-director/references/SIZES.md`) |
| List what an `.oct` holds | `python <skills>/scripts/pack_beta.py --inspect-oct <file.oct> [--json]` | Header plus every asset: kind, name, size, payload sha1; no app folder needed |
| Compare two builds | `python <skills>/scripts/pack_beta.py --compare-oct <a.oct> <b.oct>` | Exit 0 same, 1 different: header fields (version, GUID, title, categories, save size, code) and assets added / removed / changed / moved. To see a changed sprite, look at the app's PNG sources (`assets_<game>/art/`, the PSDs) |
| Extract the art of a packed game | `python <skills>/scripts/extract_art.py --app-dir <app> --out <ws>/assets_<game> [--manifest <ws>/plans/<game>_assets.json]`, or `--oct <file.oct> --out <dir>` | Reads the current format (`index.bin`, `art/packed/*.raw` + `*.pal`, or an `.oct`; palette sprites and every raw format the engine draws: RGB565 plain/RLE/SOFTKEY, ARGB6666 plain/RLE, MONO1; an unknown format is an error, exit 1): one pixel-exact RGBA PNG per sprite in `<out>/art/` (the pack reads them there), an untouched copy in `<out>/original/` and every packed record (sprites, font glyphs, palettes) in `<out>/original/packed/`, the launcher icon as `<out>/icon.png`, the listing `<out>/extracted.json` (sizes, format, flags, palettes, frame links, pixel digests); from an `.oct` also the sounds (`<out>/wav/assets/`). `--manifest` writes a manifest with every sprite and sound as `keep`; the manifest pack then changes nothing the mod does not touch: untouched sprites, font glyphs (while the font's `font_<n>.fnt` source is unchanged since the extraction; an edited one rebuilds that font only, a font the pack never held is not packed unless the manifest names it in `"fonts"`), palettes and the icon go back byte for byte at their old asset ids and the game's own `_ids.h` is kept; only edited or added sprites are encoded anew (`python <skills>/scripts/carry_art.py --manifest <m> --workspace <ws>` lists which). Refuses to overwrite PNGs without `--force` |
| Unpack sprites (older packs) | `python <skills>/scripts/unpack.py --packed-dir <dir> --output-dir <out>` | Only the older packed-PNG format with a `pal.png`; the current format is `extract_art.py` |
| Fork a game (a new game from a working one) | `<skills>\scripts\fork_app.ps1 -Source <app> -Name <new> [-Title "..."]` / `scripts/fork_app.sh --source <app> --name <new> [--title "..."]` | Copies `app_<old>` to `app_<new>` (no build output, no pack record), renames the `.target` marker, headers, `#include`s and `APP_DIR`, writes a fresh random `APP_GUID1`, the title and version 0.0.0 (the first `repack_app` ships 0.1.0; a legacy integer `APP_VERSION` becomes the semver fields); copies `assets_<old>/` and `plans/<old>_*` when they exist. Refuses an existing target; the source stays untouched. Then `build_game` and `build_device` |
| Sprite sheet from finished pictures | `python <skills>/skills/cube_art-director/scripts/art.py sheet <art.json or manifest> [--set s] [--cols N]` | One grid PNG plus a JSON atlas (each sprite's x, y, w, h; one animation list per set) in `<workspace>/sheet/`; from the finals `art.py process` wrote |
| Inspect sounds | `python <skills>/scripts/sound_kit.py inspect <files or glob>` | Numbers only (duration, peak, loudness, bands): never play audio |
| Check sound licences | `python <skills>/scripts/sound_kit.py licences <folder>` | Exit 1 unless every licence file inside is CC0; the archive's own licence wins over a store page |
| Gameplay or demo video | the frames of a hidden autoplay run + ffmpeg (`cube_orchestrator/references/DELIVERY.md` §5), or the `wowcube-demo-video` skill for the 1920x1080 presentation format | Never open the video; give the path |

## Rules of thumb

- **`APP_GUID1` never changes** for an update of the same game; a fork is a new game with a new GUID
  and a new title: `fork_app.ps1` / `fork_app.sh` make both and set version 0.0.0 (its first repack ships 0.1.0).
- **Versions**: every build you hand out gets a new minor version (patch 0): `repack_app.py` does it; the
  `.oct` carries exactly the version in `src/app_metadata.h`.
- **Deliver from `dist/` only** (`build_device` writes it); the simulator writes no `.oct`, and an `.oct`
  left in an app folder by an older simulator is never the deliverable.
- An app without a manifest is repacked from its own sources (`repack_app.py` detects them); never write
  a one-entry manifest for it (the pack would drop every other asset). An app that has only its packed art
  (no PNG or PSD sources) is extracted first (`extract_art.py --manifest`): that manifest covers every
  asset.
- Engine facts and limits: `<skills>/templates/app_ai_template/API.md`.

## Report

What ran, the exit code, the output paths (absolute), versions before and after, and anything that was
not checked. When the request grows into changing the game itself, hand over to `cube_orchestrator`
(Mod mode).
