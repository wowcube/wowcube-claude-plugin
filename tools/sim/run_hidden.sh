#!/usr/bin/env bash
# Run the standalone simulator hidden and muted on Linux or macOS and report the frames (mirror of run_hidden.ps1).
#
#   tools/sim/run_hidden.sh <app_dir> [--seconds 15] [--every-ms 500] [--face -1] [--mcp-port 8177]
#                           [--out-dir <dir>] [--work-dir <dir>] [--fresh-saves] [--allow-drops] [--exe <wowcube-sim>]
#                           [--no-keepalive] [--keepalive-sec 25]
#
# Starts the installed simulator (sim_path.sh sim_exe; refused unless sim_check finds the version this checkout
# needs; --exe <path> skips that check) --headless --mute --game <app_dir> --seconds S [--frames <out>/frames ...]
# in its own process group. Linux: under xvfb-run with X11 forced (a Wayland session would otherwise get a real
# window), so nothing ever appears on the user's display; without xvfb-run (and setsid) the run is refused.
# macOS: --headless keeps the SDL window hidden (verified on CI). The simulator ends itself after S seconds; after
# S + 40 s the process group is killed (only the group this script started). Prints the summary, the last frame and
# a seam report for it (seams.py; never an exit code). The work dir (cfg, logs, the simulated SD-card and flash
# images = the saves) is <out-dir>/work unless --work-dir is given: pass the previous run's work dir to keep its saves.
# <out-dir>/run_info.json is written as soon as the simulator starts, with the same fields as run_hidden.ps1 (pid,
# exe, start_time, out_dir, work_dir, log, mcp_port, seconds, every_ms, ends_at = when --seconds runs out, run_id):
# mcp_port is filled in the moment the "[mcp] control socket listening" line appears (read the port from there, the
# simulator moves to the next port when one is taken); exit and ended_at are added when the run is over.
#
# Exit codes: 0 completed (sim_summary.txt) | 1 setup error | 3 did not end in time (killed) | 4 no frames |
#             5 crashed (signal or exit 99) | 6 start error (simulator exit 10-14, sim_error.txt) | 7 ended early |
#             8 the plugin is older than the game's sources (rebuild: build_game.sh) | 9 output incomplete (exit 15,
#             or a PNG on disk does not decode) | 10 capture schedule incomplete (a slot skipped or dropped: exit 16,
#             or fewer frames than --seconds / --every-ms owe; --allow-drops accepts it)
# A completed run: exit 0, sim_summary.txt of THIS run (--run-id), completed=1, ok=1, elapsed >= --seconds, as many
# PNGs on disk as the summary reports written, every one decoding (tools/sim/check_frames.py) and (unless
# --allow-drops) exactly ceil(seconds*1000 / every-ms) of them; each run writes into a fresh --out-dir (default).
# Keep-alive: a run longer than 50 s (or --seconds 0) starts tools/sim/keepalive.py once the MCP port is known. Every
# --keepalive-sec seconds it spins the cube 1080 deg about the vertical axis (36 MCP `turn 30 0 0`, one a frame, ~0.6 s):
# sustained movement for the engine, so the idle minute that dims the cube and PAUSES the game (battery save) never
# runs out, while gravity in cube space (tilt) is unchanged. --no-keepalive only to test battery save itself. Pulses
# are logged to <out-dir>/keepalive.log (an MCP tap landing inside a pulse may be dropped: retry it).
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
APP_DIR=''; SECONDS_RUN=15; EVERY_MS=500; FACE=-1; MCP_PORT=8177; OUT=''; WORK=''; FRESH=0; EXE=''; ALLOW_DROPS=0
KEEPALIVE=1; KEEPALIVE_SEC=25
fail() { printf 'ERROR: %s\n' "$2" >&2; exit "$1"; }
while [ $# -gt 0 ]; do
    case "$1" in
        --seconds)     SECONDS_RUN="$2"; shift 2;;
        --every-ms)    EVERY_MS="$2"; shift 2;;
        --face)        FACE="$2"; shift 2;;
        --mcp-port)    MCP_PORT="$2"; shift 2;;
        --out-dir)     OUT="$2"; shift 2;;
        --work-dir)    WORK="$2"; shift 2;;
        --fresh-saves) FRESH=1; shift;;
        --allow-drops) ALLOW_DROPS=1; shift;;
        --exe)         EXE="$2"; shift 2;;
        --no-keepalive) KEEPALIVE=0; shift;;
        --keepalive-sec) KEEPALIVE_SEC="$2"; shift 2;;
        -h|--help)     sed -n '2,33p' "$0"; exit 0;;
        -*)            fail 1 "unknown argument: $1";;
        *)             APP_DIR="$1"; shift;;
    esac
done
[ -n "$APP_DIR" ] && [ -d "$APP_DIR" ] || fail 1 "usage: run_hidden.sh <app_dir> [...] (app folder not found: '$APP_DIR')"
APP_DIR="$(cd "$APP_DIR" && pwd)"
case "$(uname -s)" in Darwin) os=macos; ext=dylib;; Linux) os=linux; ext=so;; *) fail 1 "unsupported OS (Windows: run_hidden.ps1)";; esac
. "$repo/tools/sim/sim_path.sh"
. "$repo/tools/sim/run_info.sh"
if [ -z "$EXE" ]; then
    # the installed simulator must be the version this checkout needs (a stale build behaves differently: taps, MCP forms)
    sim_problem="$(sim_check)" || fail 1 "$sim_problem"
    EXE="$(sim_exe)"
fi
[ -x "$EXE" ] || fail 1 "$EXE not found - get it: tools/sim/get_sim.sh"
n_targets=$(find "$APP_DIR" -maxdepth 1 -name '*.target' -type f | wc -l)
[ "$n_targets" -eq 1 ] || fail 1 "$APP_DIR must hold exactly one *.target marker"
app=$(basename "$(find "$APP_DIR" -maxdepth 1 -name '*.target' -type f)" .target)
plugin="$APP_DIR/out/sim/$app.$ext"
[ -f "$plugin" ] || fail 1 "$plugin not found - build it: tools/sim/build_game.sh $APP_DIR"
newer=$(find "$APP_DIR/src" -type f -newer "$plugin" | head -n 1)
[ -z "$newer" ] || fail 8 "source changed after the plugin build (e.g. $newer): tools/sim/build_game.sh $APP_DIR"

# every run gets its own artifacts: a fresh out dir by default, a run id the simulator echoes into sim_summary.txt
RUN_ID="$(date +%s)_$$_${RANDOM}${RANDOM}"
[ -n "$OUT" ] || OUT="$APP_DIR/out/sim/runs/$(date +%Y%m%d_%H%M%S)_$$"
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
[ -n "$WORK" ] || WORK="$OUT/work"
mkdir -p "$WORK"; WORK="$(cd "$WORK" && pwd)"; FRAMES="$OUT/frames"
if ls "$FRAMES"/frame_*.png >/dev/null 2>&1; then fail 1 "$FRAMES already holds frames of another run: pass a new --out-dir (or none)"; fi
rm -f "$WORK/sim_summary.txt" "$WORK/sim_error.txt"
args=(--headless --mute --run-id "$RUN_ID" --game "$APP_DIR" --seconds "$SECONDS_RUN" --mcp-port "$MCP_PORT" --workdir "$WORK" --face "$FACE")
[ "$EVERY_MS" -gt 0 ] && args+=(--frames "$FRAMES" --every-ms "$EVERY_MS")
[ "$FRESH" -eq 1 ] && args+=(--fresh-saves)
[ "$ALLOW_DROPS" -eq 1 ] && args+=(--allow-drops)
PY=python3; command -v python3 >/dev/null 2>&1 || PY=python
[ "$EVERY_MS" -le 0 ] || command -v "$PY" >/dev/null 2>&1 || fail 1 "python not found: every frame is checked with tools/sim/check_frames.py"

command -v setsid >/dev/null 2>&1 || [ "$os" = macos ] || fail 1 "setsid not found (util-linux)"
# battery-save keep-alive (keepalive.py): runs longer than 50 s or until stopped, unless --no-keepalive
if [ "$KEEPALIVE" -eq 1 ] && { [ "$SECONDS_RUN" -eq 0 ] || [ "$SECONDS_RUN" -gt 50 ]; }; then
    if ! command -v "$PY" >/dev/null 2>&1; then
        echo "WARNING: python not found - no keep-alive: the game pauses (battery save) after 60 s without input" >&2
        KEEPALIVE=0
    fi
else
    KEEPALIVE=0
fi
KA_PID=''; KA_LOG="$OUT/keepalive.log"
if [ "$os" = linux ]; then
    command -v xvfb-run >/dev/null 2>&1 || fail 1 "xvfb-run not found (apt install xvfb): a hidden run needs a virtual display"
    echo "==> Hidden run: xvfb-run $EXE ${args[*]}"
    # Force X11 so the window lands on xvfb's virtual display: on a Wayland session SDL would otherwise pick
    # WAYLAND_DISPLAY and open a real window on the user's screen despite xvfb-run's DISPLAY.
    ( exec env -u WAYLAND_DISPLAY XDG_SESSION_TYPE=x11 SDL_VIDEODRIVER=x11 SDL_AUDIO_DRIVER=dummy SDL_AUDIODRIVER=dummy \
          setsid xvfb-run -a -s "-screen 0 1280x1024x24" "$EXE" "${args[@]}" > "$OUT/stdout.txt" 2>&1 ) &
else
    echo "==> Hidden run: $EXE ${args[*]}"
    ( exec env SDL_AUDIO_DRIVER=dummy "$EXE" "${args[@]}" > "$OUT/stdout.txt" 2>&1 ) &
fi
PGID=$!
# run_info.json now, while the instance runs (a playtest reads ends_at and mcp_port from it)
RI_PID="$PGID"; RI_EXE="$EXE"; RI_START="$(ri_iso_utc)"; RI_OUT="$OUT"; RI_WORK="$WORK"; RI_LOG="$WORK/log_linux.txt"
RI_MCP_PORT=''; RI_SECONDS="$SECONDS_RUN"; RI_EVERY_MS="$EVERY_MS"; RI_ENDS_AT="$(ri_ends_at "$SECONDS_RUN")"
RI_RUN_ID="$RUN_ID"; RI_EXIT=''; RI_ENDED=''; RI_KEEPALIVE="$KEEPALIVE"; RI_KEEPALIVE_LOG=''
[ "$KEEPALIVE" -eq 1 ] && RI_KEEPALIVE_LOG="$KA_LOG"
ri_write "$OUT/run_info.json"
echo "started hidden: pid $PGID  run info: $OUT/run_info.json (ends_at ${RI_ENDS_AT:-never})"
limit=$((SECONDS_RUN + 40)); waited=0; code=''
while kill -0 "$PGID" 2>/dev/null; do
    if [ -z "$RI_MCP_PORT" ] && [ $((waited % 5)) -eq 0 ]; then
        RI_MCP_PORT="$(ri_mcp_port "$OUT/stdout.txt")"
        if [ -n "$RI_MCP_PORT" ]; then
            ri_write "$OUT/run_info.json"
            echo "mcp: listening on 127.0.0.1:$RI_MCP_PORT"
            if [ "$KEEPALIVE" -eq 1 ]; then
                # ends itself when the simulator closes the socket; stopped below otherwise (only this PID)
                "$PY" "$here/keepalive.py" --port "$RI_MCP_PORT" --period "$KEEPALIVE_SEC" --first "$KEEPALIVE_SEC" \
                    --log "$KA_LOG" > /dev/null 2>&1 &
                KA_PID=$!
                echo "keep-alive: pid $KA_PID, a yaw pulse every $KEEPALIVE_SEC s (log $KA_LOG; off: --no-keepalive)"
            fi
        fi
    fi
    if [ "$waited" -ge $((limit * 10)) ]; then
        kill -TERM -- "-$PGID" 2>/dev/null || kill -TERM "$PGID" 2>/dev/null; sleep 1
        kill -KILL -- "-$PGID" 2>/dev/null || kill -KILL "$PGID" 2>/dev/null
        code=timeout; break
    fi
    sleep 0.1; waited=$((waited + 1))
done
if [ -z "$code" ]; then wait "$PGID"; code=$?; fi
if [ -n "$KA_PID" ]; then
    for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
        kill -0 "$KA_PID" 2>/dev/null || break; sleep 0.1
    done
    kill -TERM "$KA_PID" 2>/dev/null; wait "$KA_PID" 2>/dev/null
    [ -f "$KA_LOG" ] && sed 's/^/  /' "$KA_LOG"
fi
[ -n "$RI_MCP_PORT" ] || RI_MCP_PORT="$(ri_mcp_port "$OUT/stdout.txt")"
RI_EXIT="$code"; RI_ENDED="$(ri_iso_utc)"
ri_write "$OUT/run_info.json"
echo "pid $PGID: exit=$code mcp_port=${RI_MCP_PORT:-not seen}"

[ "$code" = timeout ] && fail 3 "did not end within $limit s - its process group was killed"
[ -f "$WORK/sim_error.txt" ] && fail 6 "start error: $(tr '\n' ' ' < "$WORK/sim_error.txt")"
{ [ "$code" -ge 128 ] || [ "$code" -eq 99 ]; } && fail 5 "crashed (exit $code); see $WORK and $OUT/stdout.txt"
sumv() { sed -n "s/^$1=//p" "$WORK/sim_summary.txt" 2>/dev/null | head -n 1; }
if [ -f "$WORK/sim_summary.txt" ]; then
    sed 's/^/  /' "$WORK/sim_summary.txt"
    [ "$(sumv run_id)" = "$RUN_ID" ] || fail 7 "sim_summary.txt belongs to another run (run_id '$(sumv run_id)', expected $RUN_ID)"
fi
[ "$code" = 15 ] && fail 9 "the simulator could not write its output (a PNG or sim_summary.txt; disk full or permissions?)"
# exit 16 = the simulator's "capture schedule incomplete"; a summary with ok=0 and lost slots means the same even when
# the exit code got lost on the way (an older simulator, a wrapper): never report that as "no summary"
lost=$(( $(sumv dropped || true) + 0 + $(sumv skipped || true) + 0 )) 2>/dev/null || lost=0
if [ "$code" = 16 ] || { [ -f "$WORK/sim_summary.txt" ] && [ "$(sumv ok)" = 0 ] && [ "${lost:-0}" -gt 0 ] && [ "$ALLOW_DROPS" -eq 0 ]; }; then
    fail 10 "frame slots were lost (simulator exit $code; ok=$(sumv ok) dropped=$(sumv dropped) skipped=$(sumv skipped) expected=$(sumv expected)): the host stalled (often during the boot intro at --every-ms below 250) or the disk is slow; --allow-drops accepts it when gaps between frames do not matter"
fi
last=''
if [ -d "$FRAMES" ]; then last="$(ls "$FRAMES"/frame_*.png 2>/dev/null | sort | tail -n 1)"; fi
if [ -n "$last" ]; then
    echo "frames: $(ls "$FRAMES"/frame_*.png | wc -l) in $FRAMES"
    echo "last frame: $last"
    face_arg=(); [ "$FACE" -ge 0 ] && face_arg=(--face)
    "$PY" "$here/seams.py" "$last" ${face_arg[@]+"${face_arg[@]}"} | sed 's/^/  /' || true
fi
echo "log: $WORK/log_linux.txt, $OUT/stdout.txt"
[ "$EVERY_MS" -gt 0 ] && [ -z "$last" ] && fail 4 "no frames in $FRAMES"
if [ -f "$WORK/sim_summary.txt" ]; then what="sim_summary.txt: completed=$(sumv completed) ok=$(sumv ok) elapsed_ms=$(sumv elapsed_ms)"; else what="no sim_summary.txt in $WORK"; fi
{ [ "$code" -eq 0 ] && [ "$(sumv completed)" = 1 ]; } || fail 7 "ended before its timed exit (exit $code, $what)"
# a completed run: exit 0, its own summary, the full requested time, every capture written and on disk
[ "$(sumv ok)" = 1 ] || fail 9 "the run's output is incomplete (ok=$(sumv ok), write_failed=$(sumv write_failed))"
[ "$(sumv elapsed_ms)" -ge $((SECONDS_RUN * 1000)) ] || fail 7 "ran $(sumv elapsed_ms) ms, less than the requested $SECONDS_RUN s"
if [ "$EVERY_MS" -gt 0 ]; then
    # every PNG decodes, as many as written, and (strict) as many as the schedule owes
    em=$EVERY_MS; [ "$em" -ge 10 ] || em=10
    expect=$(( (SECONDS_RUN * 1000 + em - 1) / em ))
    cf_args=("$here/check_frames.py" "$FRAMES" "$WORK/sim_summary.txt" --expect "$expect")
    [ "$ALLOW_DROPS" -eq 1 ] && cf_args+=(--allow-drops)
    "$PY" "${cf_args[@]}" | sed 's/^/  /'
    case "${PIPESTATUS[0]}" in
        0) ;;
        1) fail 9 "a frame PNG does not decode (truncated or corrupt; above)";;
        2) fail 4 "the summary reports $(sumv written) frames written, $FRAMES holds a different count";;
        4) fail 10 "the capture schedule is incomplete (above); --allow-drops accepts it";;
        *) fail 1 "check_frames.py failed";;
    esac
fi
echo "OK: hidden, muted; timed run completed"
exit 0
