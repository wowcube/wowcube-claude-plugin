#!/usr/bin/env bash
# Where the standalone simulator lives, and whether it is the version this checkout needs
# (source it: . tools/sim/sim_path.sh). bash 3.2 compatible.
#
# The simulator binaries are machine state, not plugin files: an installed plugin folder may be read-only or replaced
# on an update. get_sim.sh installs the plugin's prebuilt simulator (simulator/dist) into the user's folder; every
# tool runs that one.
#   sim_os               linux | macos
#   sim_version          the simulator version this plugin needs: sim_version in api/SOURCE (the public game API and
#                        the prebuilt simulator come from one commit of the sources; tests/test_sim_dist.py)
#   sim_dir              the install folder: $WOWCUBE_SIM_DIR, else ~/.wowcube/sim/<version>/<os>
#   sim_exe              <sim_dir>/wowcube-sim (it may be missing: get_sim.sh). There is no other place: CI sets
#                        WOWCUBE_SIM_DIR
#   sim_tool <name>      a file next to the exe (spptest)
#   sim_exe_version <exe>  "<exe> --version" with a 30 s limit: prints the version line, non-zero when it does not answer
#   sim_check [<exe>]    the check every tool runs before it relies on the exe: present, answers --version, and its
#                        version equals sim_version. 0 = ok (prints the version line); 1 = not usable (prints what is
#                        wrong and the fix, get_sim.sh, on stdout)

_sim_path_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

sim_os() { case "$(uname -s)" in Darwin) echo macos;; *) echo linux;; esac; }

sim_version() {
    local v
    v="$(sed -nE 's/^[[:space:]]*sim_version[[:space:]]*=[[:space:]]*([A-Za-z0-9._-]+)[[:space:]]*$/\1/p' \
        "$_sim_path_repo/api/SOURCE" 2>/dev/null | head -n 1)"
    echo "${v:-unknown}"
}

sim_dir() {
    if [ -n "${WOWCUBE_SIM_DIR:-}" ]; then echo "$WOWCUBE_SIM_DIR"; return; fi
    echo "$HOME/.wowcube/sim/$(sim_version)/$(sim_os)"
}

sim_tool() { echo "$(sim_dir)/$1"; }

sim_exe() { sim_tool wowcube-sim; }

sim_exe_version() {
    local path="$1" out
    [ -x "$path" ] || return 1
    out="$("$path" --headless --version 2>/dev/null & pid=$!; ( sleep 30; kill -9 "$pid" ) >/dev/null 2>&1 & killer=$!
            wait "$pid"; code=$?; kill "$killer" 2>/dev/null; exit $code)" || true
    out="$(printf '%s\n' "$out" | head -n 1)"
    case "$out" in "wowcube-sim "*) printf '%s\n' "$out"; return 0;; esac
    return 1
}

sim_check() {
    local path="${1:-$(sim_exe)}" want line got fix
    want="$(sim_version)"
    fix="run tools/sim/get_sim.sh (it installs simulator $want from this plugin into $(sim_dir); installing software waits for the user's approval)"
    if [ ! -x "$path" ]; then echo "no simulator at $path: $fix"; return 1; fi
    if ! line="$(sim_exe_version "$path")"; then
        echo "$path does not answer --version (missing libraries or an older build?): $fix"; return 1
    fi
    got="$(printf '%s' "$line" | awk '{print $2}')"
    if [ "$got" != "$want" ]; then echo "$path is wowcube-sim $got, this checkout needs $want: $fix"; return 1; fi
    printf '%s\n' "$line"
    return 0
}
