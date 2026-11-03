# Stage 5: delivery (cube_orchestrator reference)

Device `.oct`, store upload with the install QR code, on-device checklist, gameplay video,
balance loop. The device build is driven through `wowcube-boilerplate`; none of the
steps below starts a simulator.

## 1. Ship-build checklist

- [ ] The last visual gate passed on the final source.
- [ ] Test hooks off in `app_<game>/src/app_<game>.h`: `<GAME>_DEBUG_AUTOPLAY 0`,
      `<GAME>_MUTE 0`, `<GAME>_DEBUG_PLAYFIELD_FACE -1`. (`build_game -Define` switched them on
      only in its own snapshot of `src/`.)
- [ ] The launcher icon is the game's: `app_<game>/art/icon.png` is not the template
      icon, and the last pack printed no template-icon warning. An extracted game (Mod mode)
      uses `assets_<game>/icon.png` instead (`repack_app` prints `==> Launcher icon: ...`;
      STAGE3_ASSETS.md §5).
- [ ] The pack is current (a manifest app; an `art/octpack.json` app is checked by the same command against its octpacker inputs): `python <skills>/scripts/build_pipeline.py pack-status --game <game> --workspace assets_<game> --app-dir app_<game> --manifest plans/<game>_assets.json`
      exits 0 (1 = an art, sound, font, icon or manifest change since the pack:
      repack first, `references/STAGE3_ASSETS.md` §7, then rerun the visual gate).
- [ ] Version: `src/app_metadata.h` uses `APP_VERSION OCT_APP_SEMVER(...)`. Every
      rebuild of something the user may have installed bumps the **minor** version and
      resets the patch to 0 (0.1.0 → 0.2.0; the release rule), and the `.oct` carries
      exactly the version in the code (the cube's update check compares it exactly;
      `--verify-oct` checks it). `<skills>/scripts/repack_app.py` does the bump (default
      `--bump minor`; `--bump patch` only when the user asks for a patch release; it also
      accepts the legacy integer `APP_VERSION`, +1). A new game ships its first build at the
      template's 0.1.0 (no bump: nothing is installed yet). A fork is set to 0.0.0 by `fork_app`
      and its first repack ships 0.1.0. Never ship 0.0.0: a fork's `.oct` always comes from
      `repack_app.py`.
- [ ] `APP_GUID1` unchanged since the first install: it is the app's identity (an
      install replaces the pack with the same GUID and keeps its save).
- [ ] Recorded sounds have their lines in `app_<game>/sound/CREDITS.md`.

## 2. Build the device `.oct`

One command, no simulator; it writes `<ws>/dist/app_<game>.oct` and verifies it:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <skills>\scripts\build_device.ps1 -AppDir <ws>\app_<game>
```

```bash
<skills>/scripts/build_device.sh --app-dir <ws>/app_<game>
```

- **The default builder needs only this plugin and the ARM toolchain**: CMake + Ninja
  build the ARM module (`arm-none-eabi-g++`) against the public game API (`api/apps` +
  `api/include`) into `app_<game>/out/`, then `scripts/pack_beta.py --build-oct` writes
  the container from the art Stage 3 packed (`index.bin`, `art/packed`, `sound/assets`). It
  stamps the save size from `APP_SAVE_SIZE` (read through `src/app_metadata.h` and
  `app_save.h`'s static_assert, so keep that assert).
- `-Builder octpack` / `--builder octpack` is only for a developer who passes their own SDK
  checkout (`-OctaviOS` / `--octavios`) and has `uv`: the SDK's `octpack-build` writes the
  same container. The pipeline never needs it; `-NoUv` / `--no-uv` (env
  `WOWCUBE_NO_UV=1`) rules it out.
- **No `art/octpack.json` in an AI-manifest app.** A PSD-authored app with one is packed
  by the SDK's octpacker (`references/STAGE3_ASSETS.md` §9).

**Verification is mandatory.** The script verifies every `.oct` it builds, with either
builder: the ARM tail, then `scripts/pack_beta.py --verify-oct` on the header, read from
the `.oct` itself (or from `octpack-info` on the SDK builder). Any
mismatch, and anything it cannot check (no python, an unreadable header), fails the
build: there is no "checks skipped" outcome. After a manual build, run the same check:
`python <skills>/scripts/pack_beta.py --verify-oct <ws>/dist/app_<game>.oct --app-dir <ws>/app_<game> --code <ws>/app_<game>/out/app_<game>.bin`.

| Field | Expect |
|---|---|
| magic, size, CRC32 | a well-formed `.oct` |
| `code_size`, code offset, the code tail | the size and the bytes of `app_<game>/out/app_<game>.bin` (the ARM code is in the `.oct`) |
| build id | not zero |
| title, version, GUID, categories, save size | equal to the app's defines (`src/app.h` → `app_metadata.h` → `app_save.h`) |
| assets | one `MAP` named `ico` (the launcher finds the icon only through it); the asset list equals `index.bin` |
| version line | `VERSION=<major.minor.patch>`, the semver you expect |

**Hard stop, every mode:** a missing ARM toolchain or a failed or impossible
verification. Fix the environment (`<skills>/scripts/check_env.ps1` / `check_env.sh`);
never deliver a simulator-written or unverified `.oct`.

**Only `dist/` is delivered.** The bundled simulator writes no `.oct`; an `.oct` found in an
app folder (an older simulator wrote one at every start) is never the deliverable.

## 3. Store upload and the install QR code

The cube does not get the game from this computer. The user installs it from their phone: the finished
`.oct` goes to the WowCube store backend, the user gets a QR code and a link, scans the code with their
phone (or opens the link on it), and the WowCube app installs the game on the cube connected to that phone.
Which cube is connected to the phone is the user's business; nothing here asks about cubes or Bluetooth.

**Ask once** before the first upload of a game (uploading sends the game to WowCube's servers): "Upload the
game to the WowCube store to get an install QR code?" A yes covers later uploads of the same game in this
project (record `delivery.store_consent` with the date); a no → the report says the game is ready and the
QR code comes when they say "upload it".

```
python <skills>/scripts/store_upload.py <ws>/dist/app_<game>.oct --yes --verify
```

- Only the verified `.oct` from `dist/`, one file, nothing else.
- It POSTs to `https://wowcube.com/api/v3/upload` (open endpoint, no account), keeps the full link
  including its `?password=` part (without it the link does not work), writes the QR code next to the
  `.oct` as `dist/app_<game>_qr.png`, prints the link, and with `--verify` downloads the stored file back
  and compares its SHA-256 (exit 3 on a mismatch: upload again). Exit 2 = the upload failed (it retries
  once on a 504): say so plainly and keep the `.oct`; never retry in a loop.
- Every upload makes a new link; earlier links keep working. Record it in the context:
  `delivery.store = {"url", "qr", "date", "version", "sha256"}`.
- Give the user the QR code (the PNG path; show the image when the host can) and the link, with one line:
  "Scan it with your phone, or open the link on it: the WowCube app installs the game on your cube."
  The link is the user's: never post it anywhere.

`tools/cube_upload/` (Bluetooth upload through the simulator) is internal and legacy: never part of the
user's flow.

## 4. On-device checklist (give it to the user)

- The launcher shows the game's icon and title; the game starts.
- Controls on the real hardware: taps on each face (and per screen where designed),
  twists both ways, half twists ignored, tilt.
- Sound: music and effects together, balanced; positional sounds come from the right
  place (the simulator plays only module 0, so the cube is the first real test of the
  mix).
- Orientation: the HUD is upright on the side faces; the playfield follows the face
  that is up.
- Smoothness: animations at their speed, no hiccups on full-screen animations.
- Saves (if any): progress survives a shake back to the launcher and a relaunch.
- Idle: after about 60 s without input the game pauses; waking the cube relaunches to
  home (expected).
- Five minutes of play without a freeze.

Problems go back through Mod mode (T1–T3) with the user's notes; a correction that is a
standing preference goes to `context/rules.md`.

## 5. Gameplay video (optional)

Offered in the final report, made when the user wants it (or when the request asked
for one); a GDD may say what it should show. The last long autoplay run's frames are kept only when the
video was asked for; otherwise they are deleted after the look like every check's frames, and a video
asked for later is made from a fresh hidden autoplay run (a few minutes). From the last long autoplay run (frames
every 50 ms = one per tick, run with `-AllowDrops`: a slot lost in the boot intro is not a reason to redo it; ~300 KB per 24-screen PNG, so 80 s is ~470 MB: delete the
frames once the video is made). To cut it to the GDD's length (say 30-40 s with a round
end), keep only the frames in that window: their names carry the time in ms
(`frame_<index>_<ms>.png`), e.g. `Where-Object { [int]($_.BaseName -split '_')[2] -ge 38000 }`
before the `ForEach-Object`:

```powershell
$d = '<frames dir>'
Get-ChildItem $d -Filter 'frame_*.png' | Sort-Object Name | ForEach-Object { "file '$($_.FullName -replace '\\','/')'"; 'duration 0.05' } | Set-Content "$d\video.txt" -Encoding ascii
ffmpeg -v error -f concat -safe 0 -i "$d\video.txt" -vf "fps=20,pad=ceil(iw/2)*2:ceil(ih/2)*2" -c:v libx264 -pix_fmt yuv420p -crf 18 "<ws>\dist\app_<game>_gameplay.mp4"
```

MCP `record` frames (any OS): `ffmpeg -framerate 20 -i <prefix>%03d.png -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" -c:v libx264 -pix_fmt yuv420p out.mp4`.
The video is silent (no audio is ever captured). Give the user the path; do not open
it. A presentation video in the standard demo format (1920x1080: 3D cube, unfolded net, controls legend,
captions) comes from the `wowcube-demo-video` skill: method A records the HTML prototype (Node + Playwright:
a one-time install the user approves; the external path), methods B/C capture the real game with a bot on a
host g++ build and need the internal SDK (its `oct_test_shim.h` is not in this kit).

## 6. Balance loop (after the first playable build)

Expect two or three passes ("slow the hero down 4x", then "a bit livelier").

1. Every pace number lives in one tunables block of named constants at the top of the
   game header, mirrored by the GDD's tunables table.
2. **Measure**: hidden autoplay runs of 60–120 s (`references/VISUAL_GATE.md`) with the
   game logging its key numbers through `OCT_trace` (time to the first
   success or failure, objects on screen, score per minute); read them from the run's log
   (`<OutDir>/work/log_1.txt`, Linux/macOS `log_linux.txt`).
3. **Ask** the user a short questionnaire: too fast or slow, too hard or easy, which
   moment. The user plays it on their cube: a new device build and a store upload (a new QR code).
4. **Change only the tunables** (the light lane, RUN_MODES.md), run the visual gate, build, upload
   (a new QR code). Record each pass in the context (`balance_passes`: values before and after,
   why).

Autonomous runs do not tune beyond the GDD's numbers on their own: feel needs a human.

## 7. Report

Finish with the end-of-run report from `references/RUN_MODES.md`, written to `context/<game>_report.md`
and shown in the chat.
