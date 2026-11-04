# Visual gate (cube_orchestrator reference)

Code reviewers read code; nobody looked at the screen. On a shipped game, prompt 1
passed both code verifiers with a black cross across all 24 screens (a packer pivot
bug); on the next one a 2-px background cross on every face (full-screen art placed at
+-120 instead of +-119.5) passed code review at 100/100 and was found only on the frames. So after **every coder and every fixer run** the orchestrator builds the
game's plugin for the automatic checks, runs it hidden in the bundled simulator, dumps all 24 screens, and **looks at the frames itself**
before the prompt counts as done. The same gate runs at the infra gate, in Mod mode
and for balance runs. It is mandatory in every run mode.

## Rules

- **Hidden and muted, always** (`references/AGENT_SAFETY.md`). The bundled standalone
  simulator (`simulator/README.md`) loads the game as a plugin and runs `--headless --mute`
  through `tools/sim/run_hidden.ps1` (Windows: window never shown, killed by PID if one ever
  becomes visible, no audio device, crash dialogs suppressed, runs without activation) or
  `tools/sim/run_hidden.sh` (Linux: a private `xvfb-run` display with X11 forced; macOS: a
  hidden window). Never a visible simulator: it is an internal checking tool, not a way for the user to play.
- **One hidden instance at a time.** Gate runs and playtests are never parallel.
- **No input injection.** Interaction goes through the control socket (`SIM_MCP.md`)
  or the game's own test hooks.
- **Not observed = not claimed.** If the gate could not run, record it
  (`not_checked_visually` in the context) and say so; never describe frames you did
  not open. The prompt stays open: save and stop, then rerun the gate on the same prompt once
  the tool works (`references/RUN_MODES.md`, failure policy 5).

## Test hooks

Stage 2 adds them to the game header early (one of the first prompts); the prefix is
recorded in the context (`test_hooks`).

| Define | Default | Test value | Effect |
|---|---|---|---|
| `<GAME>_DEBUG_AUTOPLAY` | `0` | `1` | the game starts by itself and a scripted bot plays it (input from a script instead of taps, twists and tilt) |
| `<GAME>_MUTE` | `0` | `1` | every sound call compiles to nothing (one play helper) |
| `<GAME>_DEBUG_PLAYFIELD_FACE` | `-1` | `0..5` | pins the playfield to one face, so frames show it without tilting the cube |
| `<GAME>_DEBUG_SCENE` | `0` | `1` / `2` | every round starts one move from its win (1) or one step from its loss (2), through the game's own rules |

Older games may still name the third hook `<GAME>_DEBUG_ROOM_PLANE` (same values). Keep the name the game uses
and record it in the context's `test_hooks.plane_pin`; the build tools pass any define name, and the
verifier checks the names recorded there (`cube_verifier`, "Test hooks"). Below, `_DEBUG_PLAYFIELD_FACE`
stands for the recorded `plane_pin` name.

Which build sets what:

| Build | `_DEBUG_AUTOPLAY` | `_MUTE` | `_DEBUG_PLAYFIELD_FACE` |
|---|---|---|---|
| visual gate (frames) | `1` | `1` | `0..5` for tilt games, else `-1` |
| Playtest Agent (interactive) | `0`: the agent's taps, twists and tilts are the only input | `1` | `-1`: the playfield follows the real tilt |
| audio check (sound-event log) | `1` | `0` | as for the visual gate |
| device / shipped | `0` | `0` | `-1` (Stage 5 checks) |

`_DEBUG_SCENE` (when recorded) is `0` in every build above. When a check has not seen an ending it must
show (the visual gate never saw the death or the win screen; the Playtest Agent lists the win or the loss
under `not_observed`), run one short extra check with `_DEBUG_SCENE=1` or `2` for exactly that ending: a
30-60 s gate run (autoplay on) for frames, or a second playtest of only those criteria (autoplay off).
Never record the ending as "accepted, not seen", and never edit the source to get there.

Before the hooks exist, run without them: a hidden run opens no audio device anyway.

**Audio check** (prompts that add sound): its own build, autoplay on and `<GAME>_MUTE=0` (every gate build is
muted, so its log has no sound starts; the simulator's own `--mute` still logs sound starts); start it with
`run_hidden.ps1 ... -EveryMs 0 -McpPort <port> -AllowEarlyStop` and
take ONE continuous `record <n> <ms>` that spans the whole stretch to judge (a round end, the misses;
`record 60 1000` takes about 75 s: `mcp.ps1` waits n·ms + n/4 s + 30 s for it by itself): two
back-to-back `record` calls leave a gap of many seconds while the first writes its PNGs, and a sound in that gap
looks missing. The `<prefix>meta.txt` lists one `snd`/`sndq` line per sound start; stops and mixer cuts
(`SND_set_mixer`) are not logged, so they are judged from the code.

## Build, run, look

1. **Build** the game's plugin with the hooks this check needs (seconds to a minute). A
   snapshot of `src/` is compiled (`out/sim/obj/src`), so the real header keeps the hooks
   off:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File <skills>\tools\sim\build_game.ps1 -AppDir <ws>\app_<game> -Define <GAME>_DEBUG_AUTOPLAY=1,<GAME>_MUTE=1
   ```
   ```bash
   bash <skills>/tools/sim/build_game.sh <ws>/app_<game> -D <GAME>_DEBUG_AUTOPLAY=1 -D <GAME>_MUTE=1
   ```

   Add `<GAME>_DEBUG_PLAYFIELD_FACE=<plane>` for tilt games. A compile error is a
   **critical** finding: the error lines go straight to the fixer. No simulator yet:
   `tools/sim/get_sim.*`.

2. **Run** hidden; PNGs of all 24 screens every `EveryMs`, exit after `Seconds`:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File <skills>\tools\sim\run_hidden.ps1 -AppDir <ws>\app_<game> -Seconds 20 -EveryMs 500 -OutDir <ws>\assets_<game>\qa\sim\p03-1
   ```
   ```bash
   bash <skills>/tools/sim/run_hidden.sh <ws>/app_<game> --seconds 20 --every-ms 500 --out-dir <ws>/assets_<game>/qa/sim/p03-1
   ```

   Typical: prompt checks 15-20 s at 250-500 ms; **never shorter than 10 s**. The boot intro (the
   engine's two white eyes on the up face, every other screen near-black `#080408`) is not one
   moment for the whole cube: each of the 8 modules leaves it on its own. Measured with `run_hidden`
   on a desktop (the scaffolded template and a finished game, 5 runs at 250-500 ms): the last module
   left it between 3.8 and 4.5 s, and at 4.0 s up to 23 of 24 screens still showed it; a slower or
   busy machine takes longer (an end-to-end run saw most modules still in it at 4-6 s). So judge
   frames from about 8 s on, normally the last ones, and only frames in which **no** screen still
   shows the intro (a near-black screen where the game draws something, or the eyes on TOP, means
   that module is still booting: take a later frame, or run longer). Faster captures lose a slot or two: measured on a desktop with the template app,
   50 ms lost 2 slots in every run and 100 ms 1 slot in one run of two, all during the boot intro, which
   a strict run reports as exit 10 (simulator exit 16). So motion and animation run at 100 ms and the
   video run at 50 ms (one frame per tick) **with `-AllowDrops` / `--allow-drops`**: a missing frame
   does not matter for a contact sheet or a video, and every frame on disk is still decoded and counted.
   Keep 250 ms or slower, without `-AllowDrops`, for every check that counts frames.
   `-FreshSaves` / `--fresh-saves` when saves must start empty. **Saves and the work dir**: the
   simulated SD-card and flash images (the saves), the cfg and `log_1.txt` live in the run's work dir,
   which is `<OutDir>\work`, so every run with a new `-OutDir` starts with **empty** saves. A check
   that a save survives a relaunch (Stage 2 saves prompts, Stage 5) runs twice: the first run
   writes the save, the second gets a new `-OutDir` and **the first run's work dir**:
   `-WorkDir <first OutDir>\work` (`run_hidden.sh --work-dir <first out-dir>/work`). Never point
   `-WorkDir` at another game's or the user's folder. Frames land in
   `<OutDir>/frames/frame_<index>_<ms>.png`: the six faces as an unfolded cross (TOP above
   FRONT, BOTTOM below, LEFT FRONT RIGHT BACK in a row); `-Face 0..5` / `--face` gives one
   face at full size.

   **Only exit 0 counts**: the timed run completed (`sim_summary.txt`) and, on Windows, no
   window was ever visible. Every other exit means the run did not complete; its frames
   never pass the gate. (`-AllowEarlyStop` is only for playtests you stop on purpose, below.)

   | Exit | Meaning | Do |
   |---|---|---|
   | 0 | ran its full time, summary written, never visible | look at the frames |
   | 1 | setup error (no simulator, no plugin, bad folder) | fix the command; `get_sim`, `build_game` |
   | 2 | a window became visible and was killed (Windows) | report it; never retry visibly |
   | 3 | did not end in time, killed | stability finding |
   | 4 | no frames written | tool or start-up problem; read the log it names |
   | 5 | the game crashed (exit 99 + `headless_crash.txt`, a signal) | **critical** finding with the crash text |
   | 6 | start error (simulator exit 10-14: arguments, app folder, plugin, ABI, no packed assets; `sim_error.txt`) | fix what it names (rebuild the plugin, pack) |
   | 7 | ended before its time without a summary | **critical** stability finding with the log tail |
   | 8 | the plugin is older than `src/` | rebuild it (step 1) |
   | 9 | output incomplete: a PNG or `sim_summary.txt` could not be written (simulator exit 15: disk full, permissions), or a PNG on disk does not decode | free disk space / fix the folder, run again; never look at those frames |
   | 10 | capture schedule incomplete: a frame slot was skipped or dropped (**simulator exit 16**, summary `ok=0` with `skipped` / `dropped` > 0: the host stalled, usually during the boot intro below 250 ms, or the disk is slow), or fewer frames than `-Seconds` / `-EveryMs` owe | at 250 ms or slower: run again on a quieter machine; at 50-100 ms (motion, video) rerun with `-AllowDrops` / `--allow-drops`, which is only for runs where gaps between frames do not matter |

   Simulator exit codes and what `run_hidden` makes of them: 0 → 0; 10-14 (start errors) → 6; 15 (output not
   written) → 9; 16 (capture schedule incomplete) → 10; 99, an NTSTATUS code or a signal → 5. `run_hidden` prints the
   run's `sim_summary.txt` whenever it exists, also for a failed run.

   Exit 0 is strict: the summary is this run's (`run_id`), `completed=1 ok=1`, it ran the full `-Seconds`, every
   PNG on disk decodes (`tools/sim/check_frames.py`, all of them, not only the last), there are exactly as many as the
   summary reports written and as the schedule owes (`ceil(Seconds*1000 / EveryMs)`). A start error is exit 6 even
   when the simulator said 15 (its `--frames` folder could not be created: `sim_error.txt` decides first). The
   summary's `skewed=N` / `skewed_slots` name frames taken while some screens still showed another topology after a
   100 ms wait (a twist being redrawn, or the start-up): a note, not a failure; judge the frame after it. A frame
   marked skewed can also show neighbouring modules one tick apart (a counter 12/24 on one screen next to 13/24 on
   the next): capture timing, not a game bug ("Per-module skew in one frame" below).

   **Long runs do not pause.** A run longer than 50 s (and every `-Seconds 0` / playtest instance) starts a
   keep-alive (`tools/sim/keepalive.py`): every 25 s a 0.6 s spin of the whole cube about the vertical axis, which the
   engine counts as the cube being handled, so its battery save (60 s idle: the cube dims, a game shows "PAUSED" and
   stops) never starts; tilt (gravity in cube space) is unchanged. `run_info.json` says `"keepalive": "starting"` until the first
   complete pulse (about 25 s in), then `true` (`"failing"` / `"failed"` when pulses fail); pulses are in
   `<OutDir>/keepalive.log`. A "PAUSED" toast or a dimmed cube in such a run is therefore not expected: the
   keep-alive did not run (python missing, `-NoKeepAlive`; read its log) - rerun, do not judge those frames.
   A tap sent during a pulse can come back `err tap_dropped` (a turning cube takes no taps): send it again
   (`SIM_MCP.md`); it is not a game finding. Only a
   check of battery save itself passes `-NoKeepAlive` / `--no-keepalive` (`simulator/README.md`).

   Every run also prints a `seams:` line for its last frame (`tools/sim/seams.py`, also runnable on any
   frame: exit 1 = seams). `seams: none` is the pass. A 2-px (x2 art) or 1-px (fullsize art) line of the background
   on the inner screen edges is screen-filling art placed at +-120: **major** V1 finding, fix = `QUAD_FILL` (+-119.5,
   API.md "Coordinates"). A line the design draws on purpose (a frame around a picture) is noted as such.

3. **Look** (Read tool on the PNGs). Open at least the first frame in which no screen shows the
   boot intro any more (about 4.5 s on a desktop, later on a slow machine; step 2), one from the
   middle and the last; for motion, a contact sheet of every 10th
   frame:

   ```powershell
   $d = '<ws>\assets_<game>\qa\sim\p03-1\frames'
   Get-ChildItem $d -Filter 'frame_*.png' | Sort-Object Name | ForEach-Object { "file '$($_.FullName -replace '\\','/')'" } | Set-Content "$d\frames.txt" -Encoding ascii
   ffmpeg -v error -f concat -safe 0 -i "$d\frames.txt" -vf "select='not(mod(n,10))',scale=iw/3:-1,tile=3x3" -frames:v 1 "$d\sheet.png"
   ```
   ```bash
   d='<ws>/assets_<game>/qa/sim/p03-1/frames'
   ls "$d"/frame_*.png | sort | sed "s|.*|file '&'|" > "$d/frames.txt"
   ffmpeg -v error -f concat -safe 0 -i "$d/frames.txt" -vf "select='not(mod(n,10))',scale=iw/3:-1,tile=3x3" -frames:v 1 "$d/sheet.png"
   ```

`-D` / `-Define` work for guarded and unguarded hooks alike (the snapshot's `#define`
lines are rewritten). Linux needs `xvfb-run` (and `setsid`); without it the run is
refused, never shown on the real display.

## What to look for

| # | Check | Typical cause |
|---|---|---|
| V1 | Every screen that should show something does; no black, garbage or magenta screens; no black bars or crosses between screens; `seams: none` | pivots, art at +-120 instead of +-119.5, palette alpha, missing assets, a palette backdrop |
| V2 | The right content on the right face and screen (the GDD's screen map: playfield, HUD, backdrop) | wrong plane, wrong quad |
| V3 | On-screen size as designed | the ×2 rule ignored (half-size sprites), fullsize misuse |
| V4 | Side faces upright; panoramas continuous around the four side faces; unique objects (sun, moon) exactly once on the cube | per-screen tiling, rotation |
| V5 | Clean edges: no boxes, fringes or key colour around sprites | keying, alpha |
| V6 | Text visible and spelled right | fonts not packed, label slots exhausted |
| V7 | Motion between frames: what should move moved (autoplay), what should hold held, no flicker | tick logic, sequences |
| V8 | Stability: the full run time, all frames written, no `terminate` or assert lines in the log | crashes, pool overflow |
| V9 | This prompt's Verification items that can be seen | the prompt itself |

**Drawn by the checker, not a finding** (`simulator/README.md`, "What the frame dump draws"): the grey `#282828`
lines and fields (the dump's 4 px gaps between screens, 12 px between faces, the empty corners of the cross), and
2 px pink/cyan pairs on the edges of bright shapes on every screen of every app, the template too (the engine draws
at 120×120, doubles it and takes red from the previous pixel, so red sits 2 px off along each screen's rows). A
fringe that is also in the source sprite (`qa/all.png`), in a key colour, wider than 2 px or all round a shape, or a
background-colour line on the inner screen edges (`seams:`) is a real V1/V5 finding.

**Verdict**: PASS, or FAIL with findings (format in `references/AGENT_BRIEFS.md`).
Critical or major findings go to the fixer together with the frames that show them;
minor ones are recorded and fixed when cheap. After the fix: build, run, look again.

## Playtest Agent (interaction)

The Playtest Agent (`cube_verifier`) drives taps, twists and tilts through the hidden instance's
control socket (`sim_mcp` is `wire`, `SIM_MCP.md`). When the socket does not answer (step 3's `ping`
fails), stop that instance by PID and start a fresh one once; still no answer → an environment blocker
(`RUN_MODES.md`, failure policy 5): the prompt stays open, never passed on the visual gate alone, and the
run stops with the tool's error. It never plays the
visual gate's build: there autoplay feeds the inputs and the plane pin overrides the
tilt, so the agent's own taps, twists and tilts would prove nothing.

1. Rebuild the plugin for the playtest: autoplay off, plane pin -1, still muted (the
   next gate run rebuilds it with its own hooks).

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File <skills>\tools\sim\build_game.ps1 -AppDir <ws>\app_<game> -Define <GAME>_DEBUG_AUTOPLAY=0,<GAME>_DEBUG_PLAYFIELD_FACE=-1,<GAME>_MUTE=1
   ```

2. Start the instance in the background with no periodic frames and a lifetime that
   covers the playtest: `-Seconds` = the context's `playtest_seconds` (default **1500**, 25 min).
   Real playtests took 10-20 min (the agent reads, aims, captures and waits between commands), so
   the old 300 s lifetime ended the instance mid-playtest; the instance is stopped by PID as soon
   as the agent returns (step 5), so a long lifetime costs nothing. Raise `playtest_seconds` for a
   long game; `run_info.json` records `ends_at`, which goes into the brief. You will stop it before its time on purpose, so pass
   `-AllowEarlyStop` (without it the stopped run ends with exit 7; crashes, a visible
   window and timeouts still fail with it). `run_hidden` blocks until the instance ends
   and is its watchdog (visibility, `run_info.json`'s port): run it as a background shell
   command (Claude Code: the PowerShell/Bash tool's `run_in_background: true`), never in
   a foreground call that can time out (the watcher dies, the simulator runs on unwatched,
   `mcp_port` stays `null`), and never with `&` / `Start-Job` inside a foreground call.

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File <skills>\tools\sim\run_hidden.ps1 -AppDir <ws>\app_<game> -Seconds 1500 -EveryMs 0 -McpPort 8177 -AllowEarlyStop -OutDir <ws>\assets_<game>\qa\sim\p03-play
   ```

   Linux/macOS: the same, with `--allow-early-stop`: `bash <skills>/tools/sim/run_hidden.sh <ws>/app_<game>
   --seconds <playtest_seconds> --every-ms 0 --mcp-port 8177 --allow-early-stop --out-dir
   <ws>/assets_<game>/qa/sim/p03-play` (as a background shell command), stopped with `tools/sim/stop.sh
   <out-dir>/run_info.json` in step 5. It writes `<out-dir>/run_info.json` at the start (`ends_at`, `pid`) and
   adds `mcp_port` about a second later (also in `<out-dir>/stdout.txt` and `<out-dir>/work/log_linux.txt`:
   `[mcp] control socket listening on 127.0.0.1:<port>`, `SIM_MCP.md`). One
   instance at a time: start the next hidden run only after `stop` (or the run) has ended this one. Never kill
   it by name.

3. Connect through `run_info.json` (Windows): `mcp.ps1 -RunInfo` waits up to 30 s for the port
   (`mcp_port`, written about a second after the start, else the log line) and prints it:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File <skills>\tools\sim\mcp.ps1 -RunInfo <ws>\assets_<game>\qa\sim\p03-play\run_info.json ping info
   ```

   Check `ping` → `ok pong` and that `info` names `app_<game>`; give the Playtest Agent the
   printed port (or the `run_info.json` path).
4. Dispatch the Playtest Agent with the Verification Task JSON plus `playtest_port`,
   `frames_dir` and `ends_at` (from `run_info.json`), using a subagent type that has a shell (for `tools/sim/mcp.ps1` or
   `simcmd`). It follows `SIM_MCP.md`'s observation script and returns its JSON
   (pass at 90 with no critical issue). Read its `criteria_observed`: below about half,
   the score does not cover the prompt; when the game starts a round at boot, give the
   playtest build a title or a paused start (a test hook) so the agent connects before
   anything is decided.
5. Stop the instance as soon as the agent returns, also on failure: Windows `tools\sim\stop.ps1 -RunInfo
   <out dir>\run_info.json`, Linux/macOS `tools/sim/stop.sh <out dir>/run_info.json` (each stops only that
   process: same PID and exe, never a reused PID, never by name).

**Per-module skew in one frame.** The eight modules are threads that are not in lockstep (`simulator/README.md`,
captures), so one frame can show a HUD value one tick apart on different screens (score 4 on FRONT, 5 on RIGHT) at
a tick boundary. Before calling it a finding, look at the next frame (or `record 2 50`): skew that is gone there is
expected; the same mismatch in two consecutive frames is a real bug (state not computed identically on all modules).
In hidden runs this shows most often in frames the summary marks skewed (`skewed_slots`): e.g. 12/24 on one module
next to 13/24 on its neighbour is capture timing, not a game bug; never send it to a fix round on that frame alone.

## Evidence

- Frames are written to `assets_<game>/qa/sim/p<NN>-<attempt>/` and **deleted as soon as the check is
  done** (you looked, the findings are written into the context with the verdict): a prompt's frames
  are hundreds of MB. A finding that needs a picture as evidence keeps that one frame, copied to
  `<ws>/.agent_scratch/evidence/`, until the fix passed. Kept only: the final long autoplay run's frames
  when a gameplay video was asked for (`references/DELIVERY.md` §5), a Mod-mode baseline until the mod's
  checks are done, and a stepwise checkpoint's one sheet until the user answered.
- **Safe to delete at any time** (the user may ask): `assets_<game>/qa/sim/`, `app_<game>/out/` (build
  output, rebuilt on demand), `<ws>/.agent_scratch/`, old `.history/` snapshots the user will not undo to.
  **Never delete**: `plans/`, `context/`, `assets_<game>/` outside `qa/sim/` (`raw/`, `art/`, `style/`,
  `original/` feed the next change), `app_<game>/` outside `out/` (`.pack_inputs.json` included), `dist/`,
  `wowcube.project.json`.
- *(stepwise)* The checkpoint shows the sheet and names what nothing could judge: how
  it sounds, how it feels, balance, the real cube.
- The last Stage 4 run (long autoplay at 50 ms) feeds the gameplay video
  (`references/DELIVERY.md`).

## Infra gate, Mod mode, balance

- **Infra gate**: the template's Demo 0 exactly as it should look after the boot intro
  (V1, V2, V5, V8): the teal arrow disc (a white up-arrow on a teal circle) on all four TOP screens and on
  one FRONT screen (it hops to the neighbouring FRONT screen about a second in); the other 19 screens are
  plain black, which is correct there. A missing, cut, offset or fringed disc, garbage,
  a flat magenta (key colour) screen, black bars across a disc's screen, or the intro
  still showing in the last frames fails it. Demo 0 draws no text: the fonts are checked by the pack
  (`BMP_font_*` in the ids header), not on these frames. The simulator is an internal checking
  tool: never give the user a command to open it; they play the game on their cube (Stage 5's QR code).
- **Mod mode**: M1 keeps baseline frames; M5 repeats the run with the same hooks and
  timings and compares side by side: the change is visible, nothing else moved.
- **Balance runs**: 60–120 s of autoplay with the game logging its key numbers through
  `OCT_trace` (it prints to the simulator log); read them from the log, not from the
  pictures.
