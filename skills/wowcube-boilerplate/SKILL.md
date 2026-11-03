---
name: wowcube-boilerplate
description: >-
  Infrastructure-and-packaging component of the WowCube pipeline, invoked by
  cube_orchestrator — not a standalone user entry point. The orchestrator routes
  here at two points: the infra gate (scaffold app_<game> from the template, pack the
  template art, build the game's plugin for the bundled standalone simulator and look
  at a hidden 24-screen dump) and Stage 5 after implementation (build the device
  .oct against the bundled public game API into dist/, verify it, and upload it to the WowCube
  store for an install QR code after the user's yes). Use only when the orchestrator
  routes here.
---

# WowCube Boilerplate

> **This skill is the infrastructure & packaging component of the `cube_orchestrator` pipeline.** The orchestrator invokes it at two points: the **infra gate** (scaffold `app_<game>/` and prove the hidden simulator builds and renders) and **Stage 5** (build and verify the cube `.oct`, then the store upload and the install QR code). It is not a user-facing entry point.

Prepare a verified build environment for one game, so the first coding prompt lands
in a project that already packs, compiles and renders; and at the end turn the
finished game into a verified `.oct` the user installs from their phone (the store QR code). A broken toolchain found
here costs minutes; found three prompts into implementation it is tangled up with
new code.

```
cube_orchestrator (master controller)
  ├─ Stage 1: cube_game-designer      → GDD
  ├─ Stage 2: technical_prompter      → prompts + asset manifest
  ├─ infra gate: wowcube-boilerplate  → app_<game>/, plugin built, hidden simulator run proven   ← THIS SKILL
  ├─ Stage 3: cube_asset-builder      → packed assets (the pack writes into app_<game>/)
  ├─ Stage 4: coder/verifier/fixer    → game code, visual gate after every prompt
  └─ Stage 5: wowcube-boilerplate     → dist/app_<game>.oct, verified; store upload + QR      ← THIS SKILL
```

## Safety (hard rules)

`skills/cube_orchestrator/references/AGENT_SAFETY.md` binds every step here. In short:

- **No window over the user's screen, no audio.** The agent starts the simulator only
  hidden and muted: `tools/sim/run_hidden.ps1` (Windows: window never shown, killed by
  PID if one ever becomes visible, no audio device) or `tools/sim/run_hidden.sh`
  (Linux: a private virtual display; macOS: a hidden window). The simulator is an internal
  checking tool: never offered to the user as a way to play (they play on their cube).
- **No global input** (SendInput, keybd_event, SetForegroundWindow); the simulator is
  driven only through its control socket or the game's test hooks.
- **Kill only by PID**, only processes you started.
- **Installs and downloads only after the user agreed, as one approval**: the toolchain
  installs (`check_env.ps1 -Install`: quiet winget installs, no installer windows;
  Linux: the distro package manager or pipx, never `curl … | sh`) and getting the
  simulator (`tools/sim/get_sim.*` installs the prebuilt simulator the plugin carries (about 6 MB on Windows, no
  download, nothing to build)) are asked for together in the orchestrator's
  environment message (`AGENT_SAFETY.md`); afterwards the checks and builds use what is
  installed.
- **Store upload only after the user's yes** (it sends the game to WowCube's servers); only the verified `.oct` from `dist/`.
- No commits, pushes or messages unless asked.

## The kit and the workspace

Everything a game needs is in this plugin: the public game API (`api/`: the headers a game
compiles against, `api/README.md`; the engine commit in `api/SOURCE`) and the prebuilt simulator
(`simulator/dist`, `simulator/README.md`). The simulator is built without a game and loads any
game as a plugin
(`<app>/out/sim/<app>.dll|.so|.dylib`, built from the game's sources after every code
change). Nothing else is checked out. Check with `scripts/check_env.*`; if the kit is
too old, update this repository (never patch `simulator/`).

```
<ws>/                                  keep this path short (Python and cl.exe fail past 260 chars)
├── plans/          assets_<game>/     GDD, prompts, manifest / per-game art and sound workspace
├── app_<game>/                        created HERE: <app>.target, src/, art/, sound/, index.bin, out/
│                                      (out/sim/: the plugin and the hidden runs; out/: the ARM module)
└── dist/                              the deliverable: dist/app_<game>.oct

<skills>/                              this plugin, outside the workspace (never write into it):
                                       scripts/, tools/, templates/, skills/, simulator/
~/.wowcube/                            machine state: sim/<version>/<os>/ (the simulator), config.json
```

| Step | Windows | Linux / macOS |
|---|---|---|
| Toolchain report | `scripts/check_env.ps1` | `scripts/check_env.sh` |
| Get the simulator (once) | `tools/sim/get_sim.ps1` (the plugin's prebuilt simulator) | `tools/sim/get_sim.sh` |
| Scaffold + pack + plugin (+ hidden smoke run) | `scripts/new_app.ps1` | `scripts/new_app.sh` |
| Game plugin after a code change | `tools/sim/build_game.ps1 -AppDir <app> [-Define ...]` | `tools/sim/build_game.sh <app> [-D ...]` |
| Hidden simulator for agent checks | `tools/sim/run_hidden.ps1`, `mcp.ps1`, `stop.ps1` | `tools/sim/run_hidden.sh` (Linux under `xvfb-run`) |
| Device `.oct` | `scripts/build_device.ps1` | `scripts/build_device.sh` |
| Repack + version bump + device build | `scripts/repack_app.py` | same |
| Store upload + install QR code | `python scripts/store_upload.py <oct> --yes --verify` | same |

## When to use

- Infra gate: no `app_<game>/` in the dev layout yet (one `.target`, `src/app_metadata.h`),
  or the toolchain or the app folder is in doubt.
- Stage 5: every prompt passed its gates and there is no verified `dist/app_<game>.oct`
  of the current source; or a mod or repack needs a new device build; or the user asks
  for an upload.

Not for game code (Stage 4) or asset generation (Stage 3).

## Infra gate

### Step 0: toolchain report

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <skills>\scripts\check_env.ps1
```
```bash
bash <skills>/scripts/check_env.sh
```

It reports, and changes nothing: the simulator (`~/.wowcube/sim/<version>/<os>/wowcube-sim` present and
answering `--version` with exactly the version `api/SOURCE` names: a stale build is not OK; else `[MISSING]` with the `get_sim` command, even when `get_sim` could
install it (the plugin carries it prebuilt) or build it, because installing it waits for the approval); the plugin compiler (Windows: `clang-cl` plus the Visual Studio
2022 C++ x64 tools; macOS: the Xcode command-line tools; Linux: g++ or clang++); the
device build (CMake, Ninja, `arm-none-eabi-g++`); python with Pillow/numpy/pytoshop/psd-tools;
ffmpeg; for information the Codex CLI login, Node.js + Playwright, long-path risk. Linux
adds `xvfb-run` (hidden runs) and the SDL3 runtime. Exit 0 = ready, 2 = something missing
(the line says how to fix it). `check_env.ps1 -Install` runs quiet winget installs (no
installer windows) for the missing tools (Python and its packages, LLVM, CMake, Ninja, Arm GNU
toolchain, FFmpeg, VS 2022 Build Tools; several GB): only after the user agreed (the
one-time environment approval); winget asks to accept the package and source agreements
unless `-AcceptAgreements` is given. A fresh install needs a new shell before it is on
PATH. `check_env.sh` installs nothing: it prints the package line, never a download piped
into a shell.

### Step 1: the app name

`app_<game>`, lowercase letters, digits and `_` (the SDK requires 3 lowercase letters,
`_`, then `[A-Za-z0-9_]`). Take `<game>` from the plans' file names; ask if it is not
settled: it is baked into the marker, headers, ids and outputs.

### Step 2: scaffold, pack, build, hidden smoke run

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <skills>\scripts\new_app.ps1 -Name <game> -Workspace <ws> -Smoke [-GetSim] [-WithSave] [-Title "<Title>"] [-Category game|screensaver|test]
```
```bash
bash <skills>/scripts/new_app.sh --name <game> --workspace <ws> --smoke [--get-sim] [--with-save] [--title "<Title>"] [--category game|screensaver|test]
```

`-GetSim` / `--get-sim` only after the user's one-time environment approval (it may download or
build the simulator). Without it a missing simulator stops `new_app` before it creates anything,
with the `get_sim` command to run.

What it does, in order:

1. Toolchain report (Step 0; installs nothing).
2. Copies `templates/app_ai_template` to `<ws>/app_<game>`, renames the marker and the
   `app_ai_template*` headers, replaces the template name in every text file (`APP_DIR`,
   includes). A template `art/octpack.json`, if any, is set aside: AI-art apps are packed
   by the repo's python packer.
3. **Dev metadata** in `src/app_metadata.h`: a **random non-zero `APP_GUID1`** (the game's
   permanent identity), `APP_TITLE` from the name (`app_my_game` → "My Game") or
   `-Title`, `APP_VERSION OCT_APP_SEMVER(APP_VERSION_MAJOR, MINOR, PATCH)`, `APP_CATEGORIES` from
   `-Category` (the GDD's "Category" line in its Genre section; default `game`). `src/app.h`
   includes `app_metadata.h` first and defines none of its macros. `-WithSave` enables
   `src/app_save.h` (the save area, `APP_SAVE_SIZE`) with a `SAVE_MAGIC` from the name; without it the
   template's `app_save.h` (magic `TPL1`, demo fields) is removed and the saves prompt creates the game's own.
   `SIM_SINGLE_THREAD` is never defined (it would run the app on one module only and hide
   lockstep bugs). An old-layout template is migrated (defines moved out of `app.h`).
4. **Pack** with `scripts/pack.py` (beta container): fonts are staged into `art/fonts/`
   first, then `index.bin`, `art/packed/*.raw|*.pal`, `src/app_<game>_ids.h` and the
   launcher map `ico` from `art/icon.png`. It fails without `.raw` files, `index.bin`, the
   `ico` map, or the `BMP_font_*` glyphs (without them every label draws nothing).
5. **The simulator and the plugin**: when `~/.wowcube/sim/<version>/<os>/wowcube-sim` is missing it
   runs `tools/sim/get_sim.*` (installs the plugin's prebuilt simulator) only
   with `-GetSim` / `--get-sim`; then `tools/sim/build_game.*` compiles the game into its plugin
   (`out/sim/<app>.dll|.so|.dylib`). This proves the toolchain and that the app compiles.
   `-VisibleSim` prints the command that opens the simulator for the user; nothing is
   started.
6. **`-Smoke` / `--smoke`**: one hidden, silent run of 15 s (`-SmokeSeconds`) with a PNG
   of all 24 screens every second (`tools/sim/run_hidden.*`: Windows polls the windows
   every 50 ms and kills by PID if one is visible; Linux runs under `xvfb-run` with X11
   forced; both exit non-zero unless the timed run completed). Without `xvfb-run` the
   Linux smoke run is refused and says so. `-Run` / `--run` are the old names of this
   switch; they never open a window.

Exit 0 = infrastructure verified. A non-zero exit names the failed step: retry that
step alone (below), or report it, before Stage 3 packs into the folder.

Other switches: `-SkipBuild` (scaffold + pack only), `-SkipEnvCheck`, `-Template`.

### Step 3: look at the frames (this is the gate)

Open the last frames the run printed (Read tool;
`<ws>/app_<game>/out/sim/runs/<time>/frames/frame_*.png`, the six faces as an unfolded
cross: TOP above FRONT; LEFT, FRONT, RIGHT, BACK in a row; BOTTOM below). The simulator
first shows the engine's boot intro (the eyes on the face that is up, the other screens near-black);
each module leaves it on its own, about 4-4.5 s in on a desktop and later on a slow machine. Judge
the last frames, never one in which a screen still shows the intro. The template starts in **Demo 0**, which draws exactly
this:

| Where | Expected |
|---|---|
| TOP, all 4 screens | the template's teal arrow disc (a white up-arrow on a teal circle), centred on each screen |
| FRONT, 1 screen of its top row | the same disc; about a second after the demo starts it hops to the neighbouring top-row screen, so either one is right |
| the other 19 screens | plain black (the template's `OCT_background(0x0000)`): correct here, not a failure |

Pass when:

- the run exited 0 (Windows also printed `max_visible=0`: no window ever appeared);
- the five discs are there, whole, centred and clean: no garbage, no flat magenta (key
  colour) screen, no fringes or offsets, no black bar or cross across a disc's screen;
  the other 19 screens plain black;
- the last frames no longer show the intro (the app started).

Demo 0 draws no text: the fonts are checked by the pack step (it fails without
`BMP_font_*` glyphs in the ids header), not on these frames. A failure is fixed before
Stage 3. If the smoke run cannot happen (no simulator yet, Linux without `xvfb-run`),
record `not_checked_visually`, say so, and never fall back to a visible run.
Record `infra: "ok"` in the context only after you looked.

### Retrying a failed step (existing app)

`new_app` creates the folder once. When a later step failed (pack, simulator build,
smoke run), fix the cause and rerun **only that step** on the existing `app_<game>/`.
Never run `new_app` on it again: it refuses an existing folder, and a second scaffold
would mint a new `APP_GUID1` (the game's permanent identity). Only when `new_app` failed
before it wrote `src/app_metadata.h` (nothing to keep yet) is the half-made folder moved
aside (renamed, e.g. `app_<game>.failed`; never deleted) and `new_app` run again.

**Pack** (the template art; fonts staged into `art/fonts/` first, as `new_app` does):

```powershell
New-Item -ItemType Directory -Force <ws>\app_<game>\art\fonts | Out-Null
Copy-Item <ws>\app_<game>\art\font_* <ws>\app_<game>\art\fonts\ -Force
cd <ws>\app_<game>
python <skills>\scripts\pack.py --export --build-palette --build-ids --art-dir art --exported-dir art\exported --packed-dir art\packed --output-dir art\packed --ids-output src\app_<game>_ids.h --assets assets --beta-app-dir <ws>\app_<game> --app-name app_<game> --icon <ws>\app_<game>\art\icon.png
```
```bash
mkdir -p <ws>/app_<game>/art/fonts && cp -f <ws>/app_<game>/art/font_* <ws>/app_<game>/art/fonts/
cd <ws>/app_<game> && python3 <skills>/scripts/pack.py --export --build-palette --build-ids --art-dir art --exported-dir art/exported --packed-dir art/packed --output-dir art/packed --ids-output src/app_<game>_ids.h --assets assets --beta-app-dir <ws>/app_<game> --app-name app_<game> --icon <ws>/app_<game>/art/icon.png
```

Then check what `new_app` checks: `.raw` files in `art/packed/`, `index.bin` with the
`ico` map, `BMP_font_*` glyphs in `src/app_<game>_ids.h`.

**Plugin build**: `powershell -NoProfile -ExecutionPolicy Bypass -File <skills>\tools\sim\build_game.ps1 -AppDir <ws>\app_<game>`;
Linux/macOS `bash <skills>/tools/sim/build_game.sh <ws>/app_<game>`. A missing simulator:
`<skills>/tools/sim/get_sim.*`, after the user's approval.

**Smoke run**: `powershell -NoProfile -ExecutionPolicy Bypass -File <skills>\tools\sim\run_hidden.ps1 -AppDir <ws>\app_<game> -Seconds 15 -EveryMs 1000 -FreshSaves`;
Linux/macOS `bash <skills>/tools/sim/run_hidden.sh <ws>/app_<game> --seconds 15 --every-ms 1000 --fresh-saves`.
Its `mcp: listening on 127.0.0.1:<port>` line may name 8178 or higher: 8177 is only the first port tried, and a
simulator still holding it (the user's, or an instance not yet stopped) moves the new one to the next free port
(`cube_orchestrator/SIM_MCP.md`). Not a fault; later steps read the port from `run_info.json`.
Then Step 3.

### Step 4: report and hand off

Tell the orchestrator (and, in stepwise mode, the user): `app_<game>/app_<game>.target`;
`src/app_metadata.h` (GUID, title, version); `src/app_<game>.h` (where the game code
goes; the first prompt replaces the template demo); `index.bin` + `art/packed`; the
plugin; the frame folder you looked at. Then return to `cube_orchestrator`.

### Gotchas (why the script exists)

1. **The pack-header defines live only in `src/app_metadata.h`.** The device build and the
   plugin read them from there (octpack-build compiles it alone with a host compiler, so it
   may include only `oct_app_version.h`, `oct_app_categories.h` and `app_save.h`). A second,
   different definition in `app.h` fails the `-Werror` ARM build.
2. **`APP_GUID1` is random per game and never changes after the first install**: an
   install replaces any pack with the same GUID and the save area is keyed by it.
3. **Pack before running**: the simulator loads `index.bin` + `art/packed` at start-up
   (exit 14 without them) and the code compiles against `src/app_<game>_ids.h`; all three
   come from one pack.
4. **Fonts are packed only from `art/fonts/`** (scaffold) or `assets_<game>/fonts/`
   (Stage 3); otherwise labels silently draw nothing.
5. **Rebuild the plugin after every code change**: `run_hidden` refuses a plugin older
   than `src/` (exit 8).
6. **A simulator run writes nothing into `app_<game>/`** (the pack is built in memory).
   The deliverable is only ever `dist/app_<game>.oct` from `build_device`.

## The hidden simulator (agent checks)

Used by the visual gate after every prompt and by the Playtest Agent; the procedure and
what to look for are in `cube_orchestrator/references/VISUAL_GATE.md`, the simulator's
flags in `simulator/README.md`.

```powershell
# plugin with test hooks on (a snapshot of src/ is compiled; the real header keeps them off)
powershell -NoProfile -ExecutionPolicy Bypass -File <skills>\tools\sim\build_game.ps1 -AppDir <ws>\app_<game> -Define <GAME>_DEBUG_AUTOPLAY=1,<GAME>_MUTE=1
# hidden run: PNG of the 24 screens every 500 ms for 20 s
powershell -NoProfile -ExecutionPolicy Bypass -File <skills>\tools\sim\run_hidden.ps1 -AppDir <ws>\app_<game> -Seconds 20 -EveryMs 500 -OutDir <ws>\assets_<game>\qa\sim\p03-1
```
```bash
bash <skills>/tools/sim/build_game.sh <ws>/app_<game> -D <GAME>_DEBUG_AUTOPLAY=1 -D <GAME>_MUTE=1
bash <skills>/tools/sim/run_hidden.sh <ws>/app_<game> --seconds 20 --every-ms 500 --out-dir <ws>/assets_<game>/qa/sim/p03-1
```

- Test hooks (exact names, `#ifndef`-guarded in the game header): `<GAME>_DEBUG_AUTOPLAY`
  (default 0), `<GAME>_MUTE` (default 0), `<GAME>_DEBUG_PLAYFIELD_FACE` (default -1; 0..5 pins the
  playfield to a face). `-Define` / `-D` rewrites the snapshot's `#define` lines or passes
  the define to the compiler.
- `run_hidden` exits 0 only when the timed run completed (`sim_summary.txt`); 1 setup
  error, 2 a window became visible (Windows; killed), 3 did not end in time (killed), 4 no
  frames, 5 crashed, 6 start error (simulator exit 10-14, `sim_error.txt`), 7 ended before
  its time, 8 the plugin is older than `src/` (rebuild), 9 output incomplete (a PNG or the
  summary not written, or a PNG that does not decode), 10 capture schedule incomplete (a
  frame slot lost: simulator exit 16, summary `ok=0`; `-AllowDrops` accepts it, for 50-100 ms motion and video
  captures only). Only exit 0 counts as a run. Each run's work dir (saves) is `<OutDir>\work`; `-WorkDir` reuses an
  earlier run's (`cube_orchestrator/references/VISUAL_GATE.md`).
- MCP on the hidden instance (playtests): rebuild the plugin with autoplay off, plane pin
  -1 and mute on (`-Define <GAME>_DEBUG_AUTOPLAY=0,<GAME>_DEBUG_PLAYFIELD_FACE=-1,<GAME>_MUTE=1`),
  start it in the background with `run_hidden.ps1 ... -Seconds 1500 -EveryMs 0 -McpPort 8177
  -AllowEarlyStop`; `<OutDir>\run_info.json` carries `pid` and `mcp_port`; drive it with
  `tools\sim\mcp.ps1 -Port <port> "screens faces <abs.png>" "twist 3"`
  (`cube_orchestrator/SIM_MCP.md`); stop it with `tools\sim\stop.ps1 -RunInfo <OutDir>\run_info.json`
  (never a bare `Stop-Process -Id`). Procedure: `cube_orchestrator/references/VISUAL_GATE.md`
  "Playtest Agent".
- Capture with `screens faces` / `record` (byte-exact framebuffers); `shot` reads the
  window's back buffer.

## Stage 5: device .oct, store upload, on-device check

### Step 1: ship-build checklist

`cube_orchestrator/references/DELIVERY.md` §1: last visual gate passed on the final
source; test hooks at their defaults in the real header; the launcher icon is the
game's (`art/icon.png` is not the template's); the pack is current
(`build_pipeline.py pack-status ...` exits 0; for an `art/octpack.json` app it compares
`index.bin` with the octpacker inputs); the minor version bumped (patch 0) for any
build the user may have installed, and the `.oct` carrying exactly that version; `APP_GUID1` unchanged since the first
install.

### Step 2: build and verify (no simulator)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <skills>\scripts\build_device.ps1 -AppDir <ws>\app_<game> [-Builder auto|octpack|python] [-Out <path>.oct]
```
```bash
bash <skills>/scripts/build_device.sh --app-dir <ws>/app_<game> [--builder auto|octpack|python] [--out <path>.oct]
```

- **The default builder (`python`) needs only this plugin and the ARM toolchain**:
  a CMake + Ninja build (`arm-none-eabi-g++`) of `api/apps` against the public game API
  (`api/include`) into `app_<game>/out`, then `scripts/pack_beta.py --build-oct`. The art
  Stage 3 packed (`index.bin`, `art/packed`, `sound/assets`) goes in as it is. It stamps
  the save size (header offset 184) from `APP_SAVE_SIZE` reached through
  `src/app_metadata.h` (`sizeof(record)` is read from `app_save.h`'s static_assert of the
  wire size, so keep that assert); for an app without saves its output was byte-identical
  to the SDK's `octpack-build` in our validation.
- `octpack` is only for a developer who passes their own SDK checkout (`-OctaviOS` /
  `--octavios`, plus `uv`); the pipeline never needs it.
- **Verification is mandatory** (both builders; the script fails on any mismatch and also
  when it cannot verify): the `.oct` ends with the bytes of `out/app_<game>.bin` (the ARM
  code is in it); then `scripts/pack_beta.py --verify-oct` checks the header, taken from
  `octpack-info` when it runs and otherwise read locally from the `.oct`: magic, size,
  CRC32, `code_size` and offset, a non-zero build id, title, version, GUID, categories and
  save size equal to the app's defines (`src/app.h` → `app_metadata.h` → `app_save.h`), a
  MAP asset named `ico` (the launcher finds the icon only through it), and the asset list
  equal to `index.bin`. There is no "checks skipped" outcome: unverified means failed
  (python must be on PATH).
- **Only `dist/` is delivered**, never `app_<game>/app_<game>.oct`. Build it after the
  last simulator run of the session.
- A missing ARM toolchain or a failed verification is a hard stop: fix the environment
  (Step 0), never ship a simulator-written `.oct`.

### Repacking after asset or code changes: `repack_app.py`

```bash
python <skills>/scripts/repack_app.py --app-dir <ws>/app_<game> [--skip-device] [--builder auto|octpack|python] [--out <path>.oct]
```

One command for "I changed the art/code, rebuild": it re-runs the app's own pack command,
detected from disk in this order: `app_<game>/art/octpack.json` (PSD-authored art) → the
SDK's `octpack-pack` (needs a developer's SDK checkout and `uv`: not part of this kit);
`<ws>/assets_<game>/art/*.png` → the asset stage's `build_pipeline.py pack --workspace
assets_<game>` from `<ws>` (manifest from `<ws>/plans/<game>_assets.json`; it refuses an
incomplete set and refreshes `.pack_inputs.json`); an app-local `assets/art/` → the older
pipeline command; otherwise the scaffold's `pack.py` call (fonts staged into
`art/fonts/`). Before it packs, it checks that the sources on disk can produce every sprite
packed today and refuses (exit 2, nothing written) when they cannot: an app delivered without
its art sources (only `art/packed` + `index.bin`) would otherwise be re-packed from the
template's `art/assets.psd` and lose all its art. Font glyphs count: a glyph whose `font_<n>.fnt` is
not there and that no extraction keeps (`assets_<game>/extracted.json`) would vanish with all the
game's text. The message names the sprites and the
`scripts/extract_art.py` command that recovers them (`--allow-asset-loss` overrides). Then it
**bumps the minor version** and resets the patch (`--bump patch` for a patch instead):
`APP_VERSION_MINOR`/`_PATCH` in `src/app_metadata.h`, else a literal
`OCT_APP_SEMVER(a, b, c)`, else a legacy integer `APP_VERSION` (+1; a minor of 255 needs a
manual major bump). Then, unless `--skip-device`, it runs `build_device` into
`dist/app_<game>.oct` and prints the path and `major.minor.patch`. The cube compares
versions on install, so an un-bumped rebuild may not replace the installed one.

### Step 3: store upload and the install QR code

The cube does not get the game from this computer: the user installs it from their phone. Ask once per
game "Upload the game to the WowCube store to get an install QR code?"; after the yes:

```
python <skills>/scripts/store_upload.py <ws>/dist/app_<game>.oct --yes --verify
```

It uploads the verified `.oct` (only that file) to `https://wowcube.com/api/v3/upload`, writes the QR code
`dist/app_<game>_qr.png`, prints the install link (keep its `?password=` part) and checks the stored copy
by SHA-256 (exit 3 = mismatch: upload again; exit 2 = the upload failed: report it, keep the `.oct`, no
retry loop). Give the user the QR code and the link with one line: "Scan it with your phone (or open the
link on it): the WowCube app installs the game on your cube." Details: `cube_orchestrator/references/DELIVERY.md` §3.

`tools/cube_upload/` (a Bluetooth upload through the simulator) is internal and legacy, never offered.

### Step 4: on-device checklist

Give the user the on-device checklist (`DELIVERY.md` §4): the icon and title in
the launcher; taps on each face (and per screen where designed), twists both ways, half
twists ignored, tilt; music and effects together and positional sounds from the right
place (the simulator plays only module 0, so the cube is the first real test of the mix);
HUD upright on the side faces; animations smooth; saves survive a shake to the launcher
and a relaunch; idle pause after ~60 s; five minutes without a freeze.

### Step 5: report

The absolute `dist/app_<game>.oct` path, its size and version, the builder used, the
verification lines, and the store link and QR code path if it was uploaded. Then return to
`cube_orchestrator`.

## PSD-authored art (human artists)

**External users (this kit alone):** export the PSD's layers to PNG (Photoshop: File > Export > Layers to Files, one PNG per sprite, named as in the manifest) and use the manifest path
(`cube_orchestrator/references/STAGE3_ASSETS.md` §8-9). Nothing below is needed for that.

**Internal SDK only: octpacker.** For WowCube developers with an SDK checkout, the SDK's own packer is
the official path for art made in Photoshop: `art/octpack.json`
lists fonts, asset PSDs, map PSDs (an `ico` map for the launcher) and `raw` PNG folders;
`art/!pack.txt` holds the palette groups and their tokens (`<FULLSIZE>`, `<ARGB>`,
`<SOFTKEY>`, `<HALF>` ...). The SDK's `octpack-pack` packs it (sound sources in
`sound/*.wav|mp3` are converted too). octpacker is not part of this kit: such a project
needs a developer's SDK checkout and `uv` (`repack_app.py --octavios <dir>`,
`build_device -OctaviOS <dir> -Builder octpack`). No adapter from the AI manifest to
`octpack.json` exists (open item); AI-manifest apps stay on `build_pipeline.py pack`.

## Legacy apps on the repo's python packer (internal, legacy)

Internal and legacy: only for WowCube's own older apps. New games, and every external user, use the
manifest path. Hand-authored apps ported from the old internal tools `psd.exe` + `utils.exe` (not part
of this kit) can still be packed by `scripts/pack.py` (it reproduces the legacy tools' output, measured
on a real corpus):

- **`art/!pack.txt`** is auto-detected: one palette per block at exactly the declared size
  (symbol bitness `ceil(log2(size))`), the block's tags (`<FULLSIZE> <ALPHA> <OPAQUE> <ADD>
  <BG> <BUMP> <DUDV> <REFL>`) OR'd into every member's header. `<ALPHA>` lowers the
  anti-aliasing threshold to zero instead of forcing the bit; `<OPAQUE>` is the only
  unconditional override. `--pack-config <path>` points
  elsewhere, `--no-pack-config` opts out.
- **`art/!pack.bat` wins over filename heuristics**: it names the PSDs that are exported at
  all, which of them are `-map` documents, which palette config `utils.exe` consumed, and
  the ids header name. `--no-pack-bat` / `--pack-bat <path>`. Apps without it are unaffected.
- **`$name` layers** (`$score!font2`) are NAME_ declarations, not sprites; a `$` after a
  base name (`hero$player`) still annotates a sprite.
- **`!marker` suffixes and the layer colour swatch carry data**: `!rateN` and the swatch
  (`Rate = colour + 1`) set `octBmp_t.Rate`; `!font`/`!label` make a map place a text label;
  `!pingpong !loop !once !hide !pause !twistable !fliph !flipv !ccw !cwcw !cw` set place
  flags.
- **`--manifest` wins** over an auto-detected `!pack.txt` (printed note); an explicit
  `--pack-config` is still honoured alongside it.
- Palettes are **population-weighted** (a rare accent colour survives), so a repack can
  grow (+12.9 % on a real corpus) without a regression; alpha-flagged groups write `.pal`
  in the alpha-spread format `OCT_BLEND_alpha` reads. Check decoded pixels before
  treating either as a bug.
