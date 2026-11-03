# WowCube standalone simulator

The OctaviOS simulator (engine octavios dev `609d5ae`), built **once**, without a game, that loads any game at runtime
as a plugin. This plugin carries it **prebuilt** for every OS (`simulator/dist`); its sources are private
(wowcube/OCT_cube-sim-sources) and are not part of the plugin. Games compile against the public game API
(`api/`, `api/README.md`), which comes from the same commit of those sources (`api/SOURCE`). No octavios or telemetry
checkout, no compiler for the simulator and no download are needed.

```
wowcube-sim --game <app_dir> [--headless] [--mute] [--frames <dir> --every-ms N] [--seconds S] [--mcp-port N] ...
```

`<app_dir>` is an ordinary `app_<name>` folder (templates/app_ai_template/API.md "App layout"): one `<app>.target`,
`src/app.h`, the packed assets (`index.bin`, `art/packed/`, `sound/assets/`) and the plugin
`out/sim/<app>.dll | .dylib | .so`, built from the game's sources by `tools/sim/build_game.*`.

## Where it lives

The installed binaries are machine state (an installed plugin folder may be read-only or replaced on an update):
`get_sim.*` installs them from `simulator/dist` into `~/.wowcube/sim/<version>/<os>/` (`<version>` = `sim_version` in
`api/SOURCE`; `$WOWCUBE_SIM_DIR` overrides the whole folder). Every tool (`run_hidden`, `run_upload`, `check_env`,
`new_app`, `build_device`) runs that one exe and nothing else (CI points `WOWCUBE_SIM_DIR` at its own folder), and
only when its `--version` names exactly that version: a stale build (an older version that still answers
`--version`) is reported as not installed, with the `get_sim` command (`check_env`: `[MISSING]`, exit 2;
`run_hidden`, `run_upload`, `new_app`: refused). Resolver and check: `tools/sim/sim_path.ps1` (`Resolve-SimExe`,
`Test-SimExe`) / `sim_path.sh` (`sim_exe`, `sim_check`). An explicit `-Exe` / `--exe` skips the check.

## Get it (prebuilt, inside the plugin)

```
simulator/dist/<version>/manifest.txt                              version, sources repository + commit, sha256 + size
simulator/dist/<version>/windows/wowcube-sim.exe                   MSVC /MT, no runtime DLLs
simulator/dist/<version>/linux/wowcube-sim-linux.tar.gz            wowcube-sim + libSDL3.so.0 + spptest (Ubuntu 22.04)
simulator/dist/<version>/macos-arm64/wowcube-sim-macos-arm64.tar.gz    wowcube-sim + libSDL3.0.dylib
simulator/dist/<version>/macos-x86_64/wowcube-sim-macos-x86_64.tar.gz  (the same, Intel)
```

These are the CI artifacts of the sources repository (`wowcube-sim-<os>`) exactly as CI uploaded them; the Linux and
macOS builds stay archives (they keep the exec bit, and the macOS exe is about 107 MB unpacked, mostly zeros).

`tools\sim\get_sim.ps1` (Windows) / `tools/sim/get_sim.sh` (Linux, macOS; the Mac's build by `uname -m`) install it
into `~/.wowcube/sim/<version>/<os>/` (copied, not run in place: the plugin folder may be read-only). The rule: the
manifest's version is the one `api/SOURCE` names, the file's sha256 matches the manifest, and a staged copy answers
`--version` (hidden on Windows) with that version and the manifest's build commit; only then does it replace the
installed exe. There is no fallback: the plugin ships no simulator sources, so a missing or damaged prebuilt
simulator means an incomplete plugin (reinstall or update it).
The Linux build still needs the system's OpenGL (`libopengl0`), EGL, X11 or Wayland, BlueZ (`libbluetooth3`) and
libsystemd; the macOS one carries `libSDL3.0.dylib` (`@executable_path`, ad-hoc signed).

**Maintainers: the simulator and the public game API come from one commit of the sources.** `tests/test_sim_dist.py`
fails when `simulator/dist/<version>/manifest.txt` names another commit or version than `api/SOURCE` (or a file's
sha256 is off), and the plugin's CI (`.github/workflows/game.yml`) starts each OS's binary, builds the template game
against `api/` with it and runs it headless. After the sources repository's CI is green for a commit:

```
python tools/sim/stage_dist.py --from-ci --sources <checkout>   # gh logged in: the CI build of the checkout's HEAD:
                                                                # downloads, checks, stages, writes the manifest
python tools/api/gen_api.py --sources <checkout>                # the public game API from the same commit
python tools/sim/stage_dist.py --check [--run]                  # what the test and CI run
```

`stage_dist.py` checks each archive's layout and the build commit inside each exe, runs `--version` of the binary this
machine can start and removes other versions' folders (the plugin carries one build: about 13 MB). Then commit
`simulator/dist` and `api/`. Only these maintainer scripts use GitHub or the sources.

## Build a game for it

| | Game plugin (after every code change) |
|---|---|
| Windows | `tools\sim\build_game.ps1 -AppDir <app_dir> [-Define NAME=VALUE,...]` -> `<app_dir>\out\sim\<app>.dll` |
| Linux / macOS | `tools/sim/build_game.sh <app_dir> [-D NAME=VALUE ...]` -> `<app_dir>/out/sim/<app>.so|.dylib` |

The plugin is `api/plugin/sim_module.cpp` with the game's `src/app.h`, compiled against `api/include` only.
Requirements:
- **Windows**: `clang-cl` (LLVM: `winget install LLVM.LLVM`, or the VS component "C++ Clang tools for Windows") and
  Visual Studio 2022 (or Build Tools) with the C++ x64 tools (found through `vswhere`: the linker and libraries).
  The simulator is built with MSVC, the plugin with clang-cl, which targets the MSVC ABI.
- **macOS**: Xcode command-line tools.
- **Linux**: a C++20 compiler (g++ or clang++).

`-OutDir <dir>` / `--out-dir <dir>`: the DLL/library, snapshot and logs go there instead of `<app_dir>/out/sim`
(a coder's compile check into its scratch folder; the simulator still loads only `out/sim`).

Test hooks: `-Define` / `-D`: `#define NAME ...` lines are rewritten in a
snapshot of `src/` (`out/sim/obj/src`), so guarded and unguarded hooks are both overridden; a NAME no source defines
becomes a compiler `-D`. A typical check build: `-Define <GAME>_DEBUG_AUTOPLAY=1,<GAME>_MUTE=1`.

**Tap indicator (off).** octavios dev/test firmware paints the struck screen white for 100 ms after every applied tap
(`OCT_DEBUG_TAP_FLASH`, a debug aid; release firmware, branch `main`, has none). The prebuilt simulator leaves it out,
so a frame captured right after a tap shows the game's own answer, as on a cube with release firmware (measured
2026-11-03: in a tap-flash build the struck screen is white from ~80 to ~180 ms after the MCP tap's reply, in the
default build never). `--version` of a tap-flash build ends in `, tap flash`.

## Run flags

| Flag | Meaning |
|---|---|
| `--game <app_dir>` | load the game (also env `WOWCUBE_SIM_GAME`). Without it: the blank simulator (the built-in shell) |
| `--headless` | the window is never shown and the loop runs without activation (Windows: `WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE`, input and global key state ignored, no file dialogs or message boxes, crash/assert/abort dialogs suppressed: exit 99 + `headless_crash.txt`, no Bluetooth auto-connect, no settings written, no single-instance mutex; Linux/macOS: `SDL_WINDOW_HIDDEN`, no Bluetooth reconnect, no settings written). Implies `--mute` |
| `--mute` | no audio device is opened; the mixer still runs into a modelled ~200 ms playback queue (SDL's limit) drained at the real rate, a stall being an underrun that is never caught up later, so voices end when they would on the cube and `SND_play` keeps accepting (sound starts are logged for MCP `record`) |
| `--frames <dir>` | PNG of all 24 screens as an unfolded cross (TOP above FRONT; LEFT FRONT RIGHT BACK; BOTTOM) every `--every-ms` (default 500), `frame_<index>_<ms>.png` |
| `--every-ms <n>` | frame period in ms (needs `--frames`). A `--seconds S` run owes `ceil(S*1000 / n)` frames |
| `--allow-drops` | accept a capture with skipped (host stall) or dropped (writers behind) slots; default: `ok=0`, exit 16 |
| `--face <f>` | `-1` cross (default), `0..5` one face (top, front, right, back, left, bottom) |
| `--seconds <s>` | exit after `s` seconds and write `<workdir>/sim_summary.txt` (`ok`, `completed`, `run_id`, `captured`, `written`, `write_failed`, `dropped`, `skipped`, `expected`, `skewed`, `skewed_slots`, `elapsed_ms`, ...; `ok=1` only for a run that reached `s` with every PNG written and, without `--allow-drops`, no slot skipped or dropped). An early close writes it with `completed=0`. A PNG or summary that cannot be written makes the exit code 15. `0` = run until closed |
| `--run-id <id>` | any token, echoed into `sim_summary.txt`: the run wrappers check the summary is their run's |
| `--mcp-port <n>` | the MCP control socket (default 8077, next free port if taken; 127.0.0.1 only). Wire commands: `skills/cube_orchestrator/SIM_MCP.md`, client: `tools/sim/mcp.ps1` |
| `--fresh-saves` | delete the simulated SD-card and flash images in the work dir first: exactly `{e|i}<0-7>_<1|2>.raw`; one that cannot be deleted is a start error (exit 10) |
| `--version` | print `wowcube-sim <version> (<commit>, <os>, engine ...)` and exit 0 (Windows: also `<workdir>/sim_version.txt`) |
| `--workdir <dir>` | cfg, `log_1.txt`, card images, `sim_summary.txt`, `sim_error.txt` (default: the exe's folder on Windows, the current folder on Linux/macOS) |

The simulator boots like a cube: ~3 s of the engine's eyes intro on the face that is up, then the game. Judge the
last frames of a run of 15 s or more.

Nothing is written into `<app_dir>` by a run: the pack is built in memory (a baked-in build still writes the `.oct`
next to its app, as upstream). The device `.oct` is built by `scripts/build_device.*` (ARM module from `api/apps` +
`api/include`, no octavios needed).

Start errors print to stderr, go to `log_1.txt` and `<workdir>/sim_error.txt`, and exit with: `10` bad arguments,
`11` app folder missing or without exactly one `.target`, `12` plugin missing or not loadable, `13` ABI mismatch
(not a plugin, plugin/app ABI version, struct layout, built for another app), `14` no packed assets, `15` output
(`--frames` folder cannot be created; at the end also: a PNG or `sim_summary.txt` could not be written: a short write
or a failed close counts), `16` capture schedule incomplete (a `--frames` slot skipped or dropped, without
`--allow-drops`). Every shutdown path returns that verdict (also `--seconds 0` closed by the user). Precedence in the
wrappers: a crash (5), then `sim_error.txt` (6: a start error, also an initialization 15), then the end-of-run 15 (9)
and 16 (10).
A visible run on Windows also shows them in a message box; `--headless` never does.

### Hidden runs on Windows (agents)

`tools\sim\run_hidden.ps1 -AppDir <app_dir> -Seconds 20 -EveryMs 1000 [-McpPort 8177] [-OutDir <dir>]` starts
`--headless --mute` through `tools\sim\hidden_launch.ps1` (`SW_HIDE` + `CREATE_NO_WINDOW`, every top-level
window polled every 50 ms, the process killed by PID the moment one is visible), prints the last frame and a seam
report (`tools\sim\seams.py`). Exit 0 = the timed run completed; 1 setup, 2 visible (killed), 3 timeout, 4 no frames, 5 crash,
6 start error, 7 ended early (or ran shorter than `-Seconds`, or the summary is another run's), 8 plugin older than `src\`,
9 output incomplete (simulator 15, or a PNG that does not decode), 10 capture schedule incomplete (simulator 16, or
fewer frames than owed; `-AllowDrops`). A pass needs exit 0, this run's `sim_summary.txt` (run id) with
`completed=1 ok=1`, the full duration, every PNG decoding (`tools/sim/check_frames.py` reads all of them), as many as
written and exactly `ceil(Seconds*1000 / EveryMs)`; each run gets a fresh `-OutDir`, an old frames folder is refused. The work dir (cfg, log, the card images that hold the saves) is
`<OutDir>\work`, so a new `-OutDir` means empty saves; `-WorkDir <earlier OutDir>\work` (`run_hidden.sh --work-dir`) reuses an
earlier run's saves. Below 250 ms per frame a desktop loses a slot or two during the boot intro (exit 10): use `-AllowDrops`
for motion and video captures.
`tools/sim/run_hidden.sh` applies the same rules on Linux (Xvfb) and macOS. `<OutDir>\run_info.json` (both wrappers, written at the start) holds pid, start time, `ends_at` and the MCP port:
an MCP session (a playtest) is `-Seconds 1500 -EveryMs 0 -AllowEarlyStop` (a lifetime longer than the 10-20 min a playtest takes; it is stopped early anyway), driven with `tools\sim\mcp.ps1 -Port <port> ...` and
ended with `tools\sim\stop.ps1 -RunInfo <OutDir>\run_info.json` (stops that PID only if it is still the same exe).

### Upload mode (Windows)

`wowcube-sim --upload <file.oct> --mac <AA:BB:CC:DD:EE:FF> [--upload-name <label>] [--connect-sec N] [--dry-run]`
uploads one `.oct` to one paired cube over Bluetooth SPP and exits; always headless, no game, no MCP socket.
Wrapper, exit codes and status: `tools/cube_upload/README.md`. Linux: `~/.wowcube/sim/<version>/linux/spptest` (the
command-line uploader the prebuilt Linux simulator ships next to `wowcube-sim`).

### Linux / macOS headless

`--headless` hides the SDL window, but SDL still needs a video backend for the OpenGL context: run under Xvfb
(`xvfb-run -a -s "-screen 0 1280x1024x24" wowcube-sim --headless ...`) or a real session (the window stays hidden).
`SDL_VIDEODRIVER=offscreen` with EGL may work too (not verified). Frames are read from the engine's framebuffers,
not from the window, so they do not depend on the display.

## Plugin ABI

`api/plugin/oct_sim_plugin.h`. The plugin is the game compiled as on the cube: `api/plugin/sim_module.cpp` includes
`oct_app_module.h` and the game's `app.h` with `OCT_APP_MODULE` (every engine call goes through `OCT_APP_IMPORTS`,
the 168-slot `octAppImports_t`) and `OCT_SIM_PLUGIN` (`TL` = `thread_local`: the simulator runs the eight modules
as eight threads that share one copy of the library). It exports one C function:

```c
const octSimGameEntry_t* oct_sim_game_entry(void);
```

returning `magic` `"WOSP"`, `version` (`OCT_SIM_PLUGIN_VERSION` = 1), the `OCT_APP_ABI_VERSION` it was built against,
a layout fingerprint (sizes of `void*`, `bool`, `octAppImports_t`, `octTm_t`, `octSprite_t` (+ alignment),
`octBmpInfo_t`, `octEntryInfo_t`, `octTapSource_t`, `octCubePose_t`, `octModulePose_t`, `octCubeStats_t`,
`octDiagnosticInfo_t`, offset of the last import slot), a pointer to its `OCT_APP_IMPORTS`, the callbacks of
`octAppExports_t` as native pointers (`on_init`, `on_tick` required; `on_proc_draw`, `on_save`, `on_save_synced`,
`on_dock` per `APP_HAS_*`), and the `app_metadata.h` values (`app_name` = the `.target` stem, `APP_TITLE`,
`APP_GUID1`, `APP_VERSION`, `APP_CATEGORIES`, `APP_COLORS`, `APP_SAVE_SIZE`).

Global constructors: on the cube the binder fills the import table BEFORE it runs a module's constructors, so a
constructor may call `OCT_*`. A shared library's constructors run inside `LoadLibrary`/`dlopen`, before the
simulator could fill anything, so `sim_module.cpp` copies the filled table from the executable's exported
`oct_sim_host_imports()` in its first dynamic initializer, defined above `#include "app.h"` (a translation unit
initializes its variables in order). `TL` globals are initialized per module thread on first use, after binding:
one copy per module, as on the cube. That is the supported model: ordinary globals of the game's one translation
unit. `__attribute__((constructor))`, `[[gnu::constructor]]` and `init_priority` are not (such a function can run
before that first initializer, on Linux by priority, and call empty imports): `game_lint.py` refuses them in every
build. A non-`TL` global is one copy for all eight modules, as it never is on the cube:
games keep every mutable global `TL` (templates/app_ai_template/API.md). `reserved[0]` = 1 says the plugin did this;
the log line `imports before constructors: yes` confirms it.

The simulator refuses a plugin whose magic, versions, layout or app name differ (exit 13), fills its import table
with the same list of engine functions the cube's binder uses,
builds the pack from `<app_dir>` with the plugin's metadata, and binds the callbacks per module through
`OctSimBindLinkedApp` when the engine starts the app (`OctAppTesting = 1`), exactly as for a baked-in app.

Differences to the baked-in simulator: the game sees the module view of the engine (as on the cube) instead of the
whole engine; the libc stand-ins of `oct_freestanding.h` apply (device `sinf`/`cosf` approximations, `snprintf` =
`OCT_snprintf`), except `memset`/`memcpy`/`memcmp`/`sqrtf`, which come from the host; an app's `WLOG_*` telemetry is
compiled out (`APP_TELEMETRY` is not defined; the import slots are `NULL`). The engine's own records still reach the log.

Floating point: the cube compiles with `-fsingle-precision-constant -Werror=double-promotion -Werror=float-conversion`
(api/apps/CMakeLists.txt). A g++ plugin (Linux) gets `-fsingle-precision-constant` too; clang (clang-cl on
Windows, Apple clang) has no such flag, so there an unsuffixed literal (`x * 0.5`) is computed in double and
rounded back, which can differ from the cube in the last bit; `-Wdouble-promotion -Wfloat-conversion` report those
spots. Literals cannot differ: `build_game.*` first runs `tools/sim/game_lint.py` over the snapshot and refuses an
unsuffixed floating literal (`file:line`, fix: add `f`), comments and strings ignored; an old game opts out with
`-AllowDoubleLiterals` / `--allow-double-literals` (then its simulator floats may differ from the cube). The gate for
everything else is the **device check** `build_game.*` runs next: the source snapshot compiled with
`arm-none-eabi-g++` and the cube's exact flags (`-Werror`, syntax only), so a game that would not build for the cube
fails before any simulator run. `-NoDeviceCheck` / `--no-device-check` skips it (CI does on Windows/macOS, which have
no ARM toolchain; Linux CI runs it).

Captures (`--frames`, MCP `screens`, `record`) copy the 24 framebuffers and the topology under one lock that the modules' display DMA and module 0's topology publish also take: no torn
screen. The lock alone does not make pixels and topology agree during a twist (module 0 may publish the new topology
while another module's screens still hold the old picture), so each DMA tags its screen with the signature of the
topology its module drew under and the publish tags the topology: a `--frames` slot waits up to 100 ms (at most half
a period) and MCP `screens` up to 100 ms for all 24 tags to match; a frame taken without it is counted `skewed`
(summary `skewed`, `skewed_slots`). `record` samples on its period and does not wait. Screens of different modules may come from different engine
ticks (the modules are not in lockstep), as on the cube.

## What was verified (2026-11-02, re-checked 2026-11-03)

| | Windows 11 (local) | Linux (GitHub `ubuntu-22.04`, CI) | macOS (GitHub `macos-latest` arm64 and `macos-15-intel` x86_64, CI) |
|---|---|---|---|
| simulator builds | yes (MSVC 2022, Release) | yes (g++, SDL3 3.4.16 from source, BlueZ) | yes (Apple clang, Homebrew SDL3) |
| template plugin builds | yes (clang-cl) | yes (g++) | yes (Apple clang) |
| template headless run (15 s) | yes: never visible (watchdog `max_visible=0`), muted, Demo 0 as expected; **pixel-identical** to the former patched `tools/sim_headless` build for the same app | yes, under Xvfb: 15/15 frames, `check_template_frame.py` MATCH | yes (hidden window, Apple software GL 4.1): 15/15 frames, MATCH |
| a full game (autoplay) | yes: 20 s headless, the game plays (timer, kills, enemies, player); same picture as the former `tools/sim_headless` up to gameplay randomness | - | - |
| MCP | `ping`, `info` (folder + title), `screens faces`, `twist`, `idle` answered | socket starts (log) | socket starts (log) |
| start errors | exit 10/11/12/13/14/15 with `sim_error.txt`, never visible; a struct-layout change (`-Zp1`) is refused (13); unwritable `--frames` -> 15; `--fresh-saves` with a locked card image -> 10, an `e1_backup.raw` is kept | exit 10, 11, 15 asserted | - |
| `--mute` mixer (2026-11-03) | a test game playing a sound every 0.5 s: module 0 accepted 44 of 44 `SND_play` (6 voices), MCP `record` meta lists a `snd` start on module 0 every 500 ms | - | - |
| constructors (2026-11-03) | a non-`TL` global initialized with `OCT_random(5, 5)` reads 5; log `imports before constructors: yes` | - | - |
| device check (2026-11-03) | template and a full game pass; a `double` in the game fails the build before compiling the plugin | runs in CI | skipped (no ARM toolchain) |
| strict runs (2026-11-03) | reused `-OutDir` with frames refused (exit 1); summary checked for run id, `completed=1`, `ok=1`, duration, frame count | `run_hidden.sh` in CI | `run_hidden.sh` in CI |
| re-review fixes (2026-11-03) | template 15 s: 15/15 frames, every PNG decoded, `expected=15`, Demo 0 as expected; a full game 20 s every 500 ms: 40/40, `skewed=0`, the game plays; MCP `ping`, `info`, `twist`, `idle`, `screens faces` after the twist; an unsuffixed literal fails `build_game`, `-AllowDoubleLiterals` builds it | `run_hidden.sh` in CI | `run_hidden.sh` in CI |
| exe size | 6 MB (was 111 MB: the 100 MB upload buffer was emitted as initialized data) | - | - |
| baked-in build (`build_sim -BakeApp`, sources repository) | builds and runs headless; frame identical to the plugin run | - | - |

The Windows CI runner has no OpenGL 3.3 driver (`wglCreateContextAttribsARB missing`): the simulator and the plugin
build there, the run ends at GL init with exit 99 and no dialog; CI skips that step only when the log names
`wglCreateContextAttribsARB missing`, any other failure fails the job. Linux/macOS `--headless`
was only run on CI; a visible run with real audio was not tried anywhere (agents never start one).
