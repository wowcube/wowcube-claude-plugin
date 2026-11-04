# Simulator control socket (MCP): agent self-check and playtest

Reference for `cube_orchestrator` (starts and stops the hidden simulator) and for the
Playtest Agent in `cube_verifier` (drives it). The simulator is the bundled standalone
one (`simulator/README.md`; prebuilt, the plugin ships no simulator sources). Safety
rules: `references/AGENT_SAFETY.md`.

Every other gate reads code. Through this socket the agent sees and drives the running
game (24-screen dumps, frame recordings with sound starts, twists, taps, cube tilt), so
an iteration is checked the way a player would check it.

## What it is

The simulator (`wowcube-sim`, Windows, Linux, macOS) opens a control socket at start-up:

- bound to `127.0.0.1` only; port 8077 by default, or the next free port up to +15;
  `--mcp-port N` sets the first port tried (`run_hidden.ps1 -McpPort` / `run_hidden.sh --mcp-port`);
- log line `[mcp] control socket listening on 127.0.0.1:<port> (<app>)` (in the run's work
  folder: Windows `log_1.txt`, Linux/macOS `log_linux.txt`); `run_hidden.ps1` and `run_hidden.sh`
  write `<OutDir>/run_info.json` as soon as the simulator starts (pid, exe, start_time, out_dir,
  work_dir, log, seconds, every_ms, `ends_at`) and fill in `mcp_port` when that line appears (only
  while the wrapper runs: start it in the background, `references/VISUAL_GATE.md`);
  `mcp.ps1 -RunInfo <OutDir>\run_info.json` reads the port from there or, when it is still `null`,
  from that log line;
- a text protocol: one request per line, one reply per line; commands run on the
  simulator's main thread once per frame; no reply within 15 s → `err timeout`
  (`record n ms` gets 15 s + n·ms + n/4 s; `mcp.ps1` waits that long plus 30 s, so one long
  recording never times out in the client first).
- a second client is normal: for an instance that lives longer than 50 s the wrapper's keep-alive
  (`tools/sim/keepalive.py`, `run_info.json` `keepalive: true`, log `<OutDir>/keepalive.log`) holds
  its own connection and every 25 s sends 36 `turn 30 0 0` (~0.6 s, one a frame: a 1080 deg spin about
  the vertical axis) so the engine never enters battery save (60 s without input: dimmed, "PAUSED").
  Gravity in cube space and the pose after it are unchanged; a `tap` that lands inside a pulse can come
  back `err tap_dropped` (a turning cube takes no taps): send it again.

Clients. Windows: `tools/sim/mcp.ps1` (one connection, one reply line per command, exit 1
on any `err`):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <skills>\tools\sim\mcp.ps1 -RunInfo <OutDir>\run_info.json ping info "screens faces C:\abs\p03_idle.png"
powershell -NoProfile -ExecutionPolicy Bypass -File <skills>\tools\sim\mcp.ps1 -Port <port> "twist 3" idle "sleep 150" "screens faces C:\abs\p03_twist.png"
```

`sleep <ms>` is the client's own pause (never sent): use it between an action and the capture that
judges it.

Linux/macOS: a shell function (keep the heredoc lines at column 0):

```bash
simcmd() { python3 - "$@" <<'EOF'
import socket, sys
s = socket.create_connection(("127.0.0.1", int(sys.argv[1])), 300)
s.sendall((" ".join(sys.argv[2:]) + "\n").encode())
print(s.makefile().readline().strip())
EOF
}
# the port (the instance may still be starting), then poll until it answers
port=$(sed -nE 's/.*control socket listening on 127\.0\.0\.1:([0-9]+).*/\1/p' <out-dir>/work/log_linux.txt | tail -n 1)
for i in $(seq 60); do simcmd "$port" ping 2>/dev/null | grep -q pong && break; sleep 0.5; done
```

Between an action and its capture: `simcmd "$port" idle; sleep 0.15`.

## Hard rules

1. **Hidden and muted only.** Agent runs use `tools/sim/run_hidden.ps1` / `.sh`
   (`--headless --mute`: window never shown, killed by PID if one ever becomes visible on
   Windows, no audio device, crash dialogs suppressed, runs without activation;
   `references/VISUAL_GATE.md`). Never a visible simulator: it is an internal checking tool.
2. **Never inject global input**: no SendInput, keybd_event, SetForegroundWindow; no
   SPACE for the unfold view (a synthetic SPACE once unmuted the user's call
   microphone). Interaction is socket commands or the game's test hooks.
3. **Never touch the user's instance.** 8077 belongs to whatever the user runs; agent
   instances start at 8177 (`run_hidden -McpPort` / `--mcp-port`, recorded as `playtest_port`), and `info`
   confirms the app before anything is scored. 8177 is only the first port tried: when it is taken (another
   simulator still running, the user's or one not yet stopped) the instance takes the next free one, up to
   8192, and logs it. A smoke run on 8178 is that, not a fault: always read the port from `run_info.json` or the
   `[mcp] control socket listening` line, never assume 8177.
4. **One instance per check, stopped by its PID.** There is no quit command; the
   `Seconds` lifetime is the watchdog. A playtest instance lives `playtest_seconds` (context; default
   1500 s): real playtests took 10-20 min, and an instance that closes itself mid-playtest looks like a
   crash. `run_info.json` records `ends_at`; the brief passes it to the Playtest Agent. An instance you will stop before its time (a
   Windows playtest) is started with `run_hidden.ps1 -AllowEarlyStop` and stopped with
   `tools/sim/stop.ps1 -RunInfo <OutDir>\run_info.json`; without `-AllowEarlyStop` the
   stop ends the run with exit 7 (`references/VISUAL_GATE.md`). Never kill by process name.
5. **Playtests run their own build**: autoplay off, plane pin -1, muted
   (`references/VISUAL_GATE.md`, Playtest Agent). The visual gate's autoplay binary would
   override every tap, twist and tilt the agent sends.
6. **Never claim a playtest that did not happen**, never describe frames you did not open.

## Availability probe (once per session, before Stage 4)

Record `sim_mcp` in `context/<game>_context.json`:

| Value | Meaning |
|---|---|
| `wire` | a hidden instance answers `ping` with `ok pong` (`mcp.ps1` / `simcmd`) |
| `absent` | no answer: the instance died at start-up (a finding by itself) or no simulator yet |

With the bundled simulator `wire` is the normal case, so the Playtest Agent normally
runs. With `absent` the visual gate still runs on the hidden frames and every summary
says nobody drove the game.

## Commands

| Wire request | Reply / effect |
|---|---|
| `ping` | `ok pong` |
| `info` | `ok info <port> <w> <h> <app_folder> <app_title>` |
| `screens faces <png>` | six faces 3×2 in scene orientation, byte-exact from the 24 framebuffers, gaps RGB(1,1,1) |
| `screens <png>` | the raw 960×1440 atlas of the 24 displays plus the layout map |
| `record <n 1..100> <ms 20..2000> <prefix>` | frames `<prefix>000.png …` and `<prefix>meta.txt`: pose, gravity, layout and sound starts (`snd <ms> frame module id vol`, `sndq … quad owner id`) |
| `shot <max_side> <png>` | the 3D window; **unreliable on a hidden window**, use `screens` |
| `twist <0..23>` | replies when the snap animation settles, **before** the game has drawn the result: a `screens` / `record` sent at once still shows the pre-twist picture (verified 2026-11-03). Send `idle`, then `sleep 150` (≥ 3 ticks), then capture. twid = 2·plane (CCW) or 2·plane+1 (CW), +12 = half twist; planes top 0, front 1, right 2, back 3, left 4, bottom 5 |
| `tap quad <0..23>` / `tap face <0..5> <0..3>` | taps that screen directly, no aiming: scene quad = face·4 + quad, the same numbering as `screens faces` (below) and the game's `appTapQuad`; follows twists (the screen bound there now is struck). Replies with where the tap went (below). Spaced automatically: waits until 600 ms after the previous click before striking. Append `double` for a double tap (reply `series 2`) |
| `tap module <0..7> <0..2>` | taps one physical screen (module, its screen 0..2), the numbering of the log's `tap fused: module M screen S` |
| `tap <x> <y>` | taps window pixels of the 3D view (aim with `face` and `shot`); `err no_screen` when the aim misses every screen |
| `cube <yaw> <pitch> <roll>` / `turn …` | rotates the **cube**: gravity and the IMU follow |
| `camera <yaw> <pitch>` / `orbit …` / `face <0..5>` / `reset` | moves the **viewer** only. `face <n>` aims the 3D camera at game plane n wherever the cube is turned (`face 1` = front: verified with `shot`, upright and after `cube 90 0 0`); it changes nothing in `screens` / `record`, which always show all six faces in scene orientation. It matters only for `tap <x> <y>` aiming and `shot` |
| `unfold <0\|1>` | the six-face cross in the 3D view |
| `idle` | replies once no twist or drag is in flight |
| `shake` | the game exits to the launcher (below) |
| `log` | `ok log <run-start offset> <abs log path>`; includes `OCT_trace` and telemetry lines |

Give absolute paths (the simulator's working folder is its own). There is no pause,
step, speed, mute or quit command.

## Observation script (Playtest Agent)

Short and scripted: every image costs tokens.

1. **Identity**: `info` names `app_<game>`; otherwise stop, wrong instance.
2. **Idle**: `screens faces` → does it render, right backdrop, no garbage, no blank
   faces where art belongs?
3. **This prompt's mechanic**, with `verification_criteria` as the script: `twist` the
   faces it names, `tap quad <n>` on the screens it names (below: read the reply's `match` and
   `delivered`), `cube` poses when it reads
   gravity; after each action `idle`, `sleep 150`, then `screens faces` (a capture sent
   right after the reply can still show the frame before the action). The 150 ms count from
   the reply: a tap's reply already comes after its strike and the cube's verdict (below), so
   the capture shows the game's own answer to it. The standalone simulator has no white tap flash
   (see "Captures after a tap").
4. **Motion**: `record 20 100 <prefix>` and compare frames: what should move moved, what
   should hold held. `meta.txt` shows **whether and when sounds started** (`snd` /
   `sndq` lines), never how they sound.
5. **Orientation** (games that read gravity): `cube 0 0 0`, `cube 0 0 90`, `cube 0 90 0`,
   `screens faces` each, then `cube 0 0 0` again before anything else is judged.
6. **Survival**: `ping` still answers, a final `screens faces`, the log tail has no
   `terminate` or assert lines.
7. **Shake** only when the prompt is about shake-to-exit, and only as the last action.

### Moving the camera vs moving the cube

- `camera`, `orbit`, `face`, `reset` walk the viewer around a cube that stays put.
  Nothing in the game changes.
- `cube` and `turn` rotate the cube itself, as a hand would. Gravity turns with it, so
  a game reading `OCT_TM_gravity_*` or `OCT_TM_top_side()` reacts. Pose is measured from
  the upright cube, front face forward: yaw 90 brings the right face to the front, pitch
  90 the front face to the top, roll 90 the right face to the top. `cube 0 0 0` stands
  it upright again; `reset` does not (it only moves the camera).

### Aiming taps and twists

- Twists need no aiming.
- **Taps: name the screen.** `tap quad <n>` (or `tap face <f> <q>`, the same screen) strikes one
  screen whatever the camera and the cube's pose. Read the number off a `screens faces` picture:
  faces top, front, right in the upper row and back, left, bottom in the lower one (face 0..5),
  and inside each face quad 0 top-right, 1 top-left, 2 bottom-left, 3 bottom-right, so
  quad = face·4 + that; the game's `appTapQuad` returns the same number. After a twist
  the same quad names the screen now bound there.
- **Read the reply**: the simulator waits for the cube's own tap decision (the leader fuses the
  eight modules' rows, as on hardware) and says where the tap went:
  `ok tap struck module 7 screen 1 quad 1 face 0 fused module 7 screen 1 quad 1 face 0 series 1 agreeing 8/8 delivered 1 match 1`.
  `match 1` = the tap went to the screen you struck; `delivered 1` = the game's `on_tap` got it
  (`delivered 0`: the game was not taking input at that moment: still booting, paused by battery save
  (the log's `[state] 6 -> 5`: that tap resumed it, tap again; with the keep-alive on this should not
  happen: check `keepalive.log`), frozen by an assembly, or
  inside the engine's 1 s settle window: the engine delivers a tap only once its state has held 1000 ms
  (`OCT_GESTURE_STATE_SETTLE_MS`), and a game that calls `OCT_restart` (it sets the RUNNING state again)
  restarts that window, so the taps in the second after it are lost, on the cube as here. See "Lost taps
  after a restart" below);
  `series` = its place in a quick series (`count` in `on_tap`). `err tap_dropped ... verdicts few_agreeing:1/1`
  = the leader decided it was no tap (too few modules' rows agreed); `err tap_unconfirmed` = the leader
  decided nothing for that click: its rows were absorbed into a tap struck within 50 ms before it (only a
  mouse click can still do that), a twist was opening or settling, or the modules are not running.
  Neither is a game defect.
- **Taps are spaced for you**: send taps back to back, no `sleep` needed. Every `tap` waits, before
  it strikes, until 600 ms have passed since the previous click (the cube's 536 ms series window plus
  a margin), so each plain tap is a fresh single tap: `series 1`, `match 1 delivered 1` on a game that
  takes input and does not restart its state on a tap (20 back-to-back `tap quad 0..19`: all 20 so,
  verified 2026-11-03; the template since 2026-11-03: 12 of 12 plain and 2 of 2 double taps delivered). The cost: a tap sent
  right after another one's reply takes up to ~600 ms to answer. Why: the leader takes a tap row
  labelled within 50 ms of the previous tap's as a late row of that tap and drops it silently, and a
  tap 60-536 ms after one on the same face continues its series; the socket answers a tap 30-50 ms
  after its click, so unspaced taps alternated ok / `tap_unconfirmed` / `tap_dropped few_sharing:3/3`.
- **Double taps**: `tap quad <n> double` (also `tap face <f> <q> double`, `tap module <m> <s> double`)
  strikes the screen twice, 200 ms apart (inside the 60-536 ms series window, as a hand does), and
  replies with the second tap's verdict: `... series 2 ... delivered 1 match 1` (~0.8 s per double tap)
  on a game whose first tap does not restart its state (else the second tap is `delivered 0`: below).
  Two separate `tap` commands never make a series any more (the second waits out the window); when the
  first tap of a double is lost, the reply is its `err ...` with ` (the first tap of a double tap)`.
  `tap <x> <y> double` is `err bad_arg`.
- **Lost taps after a restart.** A game that calls `OCT_restart` from `on_tap` (a restart, the next
  level; the template did so on every demo switch before 2026-11-03) starts the engine's 1 s settle window
  with that tap: the next tap within ~1 s is `delivered 0` (plain taps then alternate `delivered 1` /
  `delivered 0`, and a double tap's second tap is `delivered 0`). Recognize it: `match 1`, `agreeing 8/8`,
  `delivered 0`, and the previous delivered tap less than ~1.1 s before it changed the game's scene. It is
  the engine's behaviour, not a simulator fault: `sleep 1100` and tap again. Do not score it as a game
  defect when the game restarts or changes level on that tap by design; when ordinary taps (moves, menu
  steps) are lost this way, the game resets its state on every tap and a player loses taps on the cube too:
  report it once as a responsiveness finding ("taps within 1 s of a tap are ignored"; the code calls
  `OCT_restart` outside `on_init`), not per tap.
- `tap <x> <y>` still clicks window pixels of the 3D view: `face <n>` points the camera at face
  n (game plane numbers, as in the twist table), `info` gives the window size, `shot` shows
  where the quads are; aim at the middle of one quad (the centre of a face is a bezel gap).
  `err no_screen` means the aim missed every screen: re-aim, or use `tap quad`. The reply then
  names the screen the click hit, as above.
- The log has one line per tap: `[sim] tap: screen <sid> (module M screen S)` for the click,
  then the leader's `[gesture] tap fused: module M screen S series N agreeing A of R ...` or
  `[gesture] tap dropped: <reason>`, then `[mcp] ok tap ...` with the reply. A `tap fused`
  module/screen that differs from the `[sim] tap` line above it is a simulator fault: report
  it, do not score the game for it. Check the effect in the game with `screens faces`.
- **Captures after a tap.** octavios dev/test firmware paints the struck screen white for 100 ms
  after every tap (`OCT_DEBUG_TAP_FLASH`, a debug aid; release firmware has none). The bundled
  simulator leaves it out by default (`simulator/README.md`, "Tap indicator"), so `idle`,
  `sleep 150`, `screens faces` after a tap's reply shows what the game drew, never that white.
  Only a simulator whose `--version` line (the context's `sdk.version`) ends in `, tap flash` (`-TapFlash`)
  shows it: there the struck screen turns white ~80 ms after the tap's reply and stays white
  until ~180 ms after it (measured 2026-11-03 with `record 30 20`), exactly where `sleep 150`
  lands, so wait `sleep 300` before capturing, and a screen that is fully white in one capture right after a
  tap and normal in the next is the indicator, never a finding. Timing of a tap command: it
  waits up to ~0.6 s before striking (spacing, above) and then for the verdict (usually
  30-50 ms, at most 1.5 s), so a tap's reply can take ~0.6 s; that wait is already behind you
  when the reply arrives.
- Long scripted sequences belong to the visual gate's autoplay run; the playtest build
  has autoplay off, so every input you send reaches the game and nothing else plays.
- Turning the cube or the camera while unfolded does nothing: `unfold 0` first.
- Leave the cube upright when done: `cube 0 0 0`.

### Shaking exits the game

For an ordinary game the engine runs its default shake handler and **returns to the
launcher**; the app's `on_shake` is never consulted. A screenshot after a shake that
shows the launcher is correct behaviour, not a crash. Never shake mid-script.

## What a playtest can and cannot judge

**Can**: does it render; the right art on the right face and screen; scale; the
response to taps, twists and tilt; gravity handling; motion; survival; whether and when
sounds start.

**Cannot**: how anything sounds, feel and exact timing on hardware, balance,
RNG-dependent outcomes, memory, and anything about the physical cube (the simulator runs
PC-compiled code; ARM code is Stage 5's job). **If it cannot be observed, it is not a
finding.** Say what was not observable and move on.

## Simulator state and the `.oct` note

- Each run keeps per-module SD-card and flash images in its work folder
  (`e<m>_<inst>.raw`, `i<m>_<inst>.raw`). `run_hidden` gives every run a **new** work folder
  (`<OutDir>/work`), so a new run starts with empty saves. Saves survive a relaunch only when the
  next run reuses the work folder: `run_hidden.ps1 -WorkDir <previous OutDir>\work` /
  `run_hidden.sh --work-dir <previous out-dir>/work` (with a new `-OutDir` for its frames). For a clean
  run use `-FreshSaves` / `--fresh-saves` (it deletes only that work folder's own images; never touch
  the user's).
- A run writes nothing into `app_<game>/` (the pack is built in memory) and no `.oct`. The
  deliverable is built by Stage 5 into `dist/`.
