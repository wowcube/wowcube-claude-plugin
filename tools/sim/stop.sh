#!/usr/bin/env bash
# Stop a hidden simulator that run_hidden.sh started (an MCP playtest you are done with), safely. Mirror of stop.ps1.
#
#   tools/sim/stop.sh <out-dir>/run_info.json
#
# Reads pid and exe from run_info.json (written by run_hidden.sh) and stops that instance only while the PID still
# runs the recorded exe (a finished run's PID may since belong to another program): on Linux the PID is the process
# group leader run_hidden.sh started (xvfb-run, Xvfb and the simulator), so the whole group gets SIGTERM, then SIGKILL
# after 5 s if it is still there; on macOS the PID is the simulator itself. Never stops anything by name. Leaves
# <out-dir>/stop_requested first, so run_hidden.sh --allow-early-stop reports the run as stopped on purpose.
#
# Exit codes: 0 stopped (or already gone) | 1 usage error | 2 the PID now belongs to another process (left running)
set -uo pipefail

ri="${1:-}"
case "$ri" in -h|--help|'') sed -n '2,12p' "$0"; [ -n "$ri" ]; exit $?;; esac
[ -f "$ri" ] || { echo "FAIL: $ri not found" >&2; exit 1; }
# one key per line (run_hidden.sh) or all on one line: the value after "pid": and the string after "exe":
json="$(tr -d '\r\n' < "$ri")"
pid="$(printf '%s\n' "$json" | sed -n 's/.*"pid":[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -n 1)"
exe="$(printf '%s\n' "$json" | sed -n 's/.*"exe":[[:space:]]*"\(\([^"\\]\|\\.\)*\)".*/\1/p' | head -n 1)"
exe="${exe//\\\"/\"}"; exe="${exe//\\\\/\\}"
[ -n "$pid" ] && [ -n "$exe" ] || { echo "FAIL: $ri has no pid/exe" >&2; exit 1; }

if ! kill -0 "$pid" 2>/dev/null; then echo "pid $pid: already gone"; exit 0; fi
# the PID must still run our exe (directly, or with it as an argument: xvfb-run <exe> ...)
if [ -r "/proc/$pid/cmdline" ]; then
    args="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
else
    args="$(ps -o args= -p "$pid" 2>/dev/null || true)"
fi
case "$args" in
    *"$exe"*|*"$(basename "$exe")"*) ;;
    *) echo "pid $pid: mismatch: it now runs '${args:-?}', not $exe - left running" >&2; exit 2;;
esac

: > "$(dirname "$ri")/stop_requested"
kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
for _ in $(seq 1 50); do
    kill -0 "$pid" 2>/dev/null || { echo "pid $pid: stopped"; exit 0; }
    sleep 0.1
done
kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null
sleep 0.2
echo "pid $pid: stopped (killed)"
exit 0
