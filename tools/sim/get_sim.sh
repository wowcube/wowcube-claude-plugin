#!/usr/bin/env bash
# Install the standalone simulator for Linux or macOS from this plugin (no download, no GitHub), verified.
#
#   tools/sim/get_sim.sh
#
# 1. The plugin carries the prebuilt simulator: simulator/dist/<version>/<linux|macos-arm64|macos-x86_64>/
#    wowcube-sim-<os>.tar.gz (wowcube-sim and its libraries; macOS by uname -m: Apple Silicon or Intel), described by
#    simulator/dist/<version>/manifest.txt (the release build of the simulator). <version> is the one this plugin
#    needs (sim_version in api/SOURCE: the public game API and the simulator match one engine version). No git, no
#    network, no compiler.
# 2. The archive's sha256 must match the manifest; it is unpacked into a staging folder and "wowcube-sim --version"
#    (30 s limit) must name that version and the manifest's build id. Only then the files replace
#    <sim dir>: ~/.wowcube/sim/<version>/<os>/ (or $WOWCUBE_SIM_DIR), outside the plugin folder (tools/sim/sim_path.sh).
# 3. There is no other way to get it: the plugin ships no simulator sources, so a missing or damaged prebuilt simulator
#    is an incomplete plugin (reinstall or update it). --no-build is accepted and ignored (old command lines).
# Linux: built on Ubuntu 22.04 (glibc 2.35 or newer); it still needs the system's OpenGL/EGL, X11 or Wayland
# libraries and the system libraries scripts/check_env.sh lists.
# Exit 0 = the simulator is in place and is the version this plugin needs; 1 = failed.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$here/../.." && pwd)"
. "$here/sim_path.sh"
while [ $# -gt 0 ]; do
    case "$1" in
        --no-build)   shift;;   # ignored: there is no local build any more
        -h|--help)    sed -n '2,17p' "$0"; exit 0;;
        *) echo "ERROR: unknown argument $1" >&2; exit 1;;
    esac
done
case "$(uname -s)" in Darwin) os=macos;; Linux) os=linux;; *) echo "ERROR: unsupported OS (Windows: get_sim.ps1)" >&2; exit 1;; esac
bin_dir="$(sim_dir)"
exe="$bin_dir/wowcube-sim"
key="$os"
if [ "$os" = macos ]; then   # one build per architecture: Apple Silicon (arm64) or Intel (x86_64)
    case "$(uname -m)" in arm64|aarch64) key="macos-arm64";; *) key="macos-x86_64";; esac
fi
top="wowcube-sim-$key"
want="$(sim_version)"
dist_dir="$repo_root/simulator/dist/$want"
step() { printf '==> %s\n' "$1"; }
warn() { printf '    %s\n' "$1" >&2; }

# <key> <file>: the value of key=value in a manifest-style file (empty when missing)
kv() { sed -nE "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*(.*[^[:space:]])[[:space:]]*$/\1/p" "$2" 2>/dev/null | head -n 1; }

file_sha256() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
    else return 1; fi
}

install_from_plugin() {
    local manifest="$dist_dir/manifest.txt" entry sha rel file got v ver build
    [ -f "$manifest" ] || { warn "this plugin carries no prebuilt simulator $want (simulator/dist/$want/manifest.txt)"; return 1; }
    [ "$(kv version "$manifest")" = "$want" ] || { warn "the prebuilt simulator is version $(kv version "$manifest"), this plugin needs $want"; return 1; }
    entry="$(kv "$key" "$manifest")"
    sha="$(printf '%s' "$entry" | awk '{print $1}')"; rel="$(printf '%s' "$entry" | awk '{print $3}')"
    [ -n "$sha" ] && [ -n "$rel" ] || { warn "manifest.txt has no $key entry"; return 1; }
    file="$dist_dir/$rel"
    [ -f "$file" ] || { warn "$file is missing"; return 1; }
    step "Checking the prebuilt simulator (sha256, then --version)"
    got="$(file_sha256 "$file")" || { warn "no sha256sum or shasum to verify $file"; return 1; }
    [ "$got" = "$sha" ] || { warn "$file does not match its sha256 in manifest.txt (damaged?)"; return 1; }
    mkdir -p "$stage/x"
    tar xzf "$file" -C "$stage/x" || { warn "cannot unpack $file"; return 1; }
    staged="$stage/x/$top"
    [ -x "$staged/wowcube-sim" ] || { warn "the archive holds no wowcube-sim"; return 1; }
    v="$(sim_exe_version "$staged/wowcube-sim")" || { warn "the prebuilt exe does not answer --version (missing system libraries?)"; return 1; }
    echo "    $v"
    ver="$(printf '%s' "$v" | awk '{print $2}')"
    build="$(printf '%s' "$v" | sed -nE 's/^wowcube-sim [^ ]+ \(([^,)]+).*/\1/p')"
    [ "$ver" = "$want" ] || { warn "the prebuilt exe is not version $want"; return 1; }
    [ "$build" = "$(kv build "$manifest")" ] || { warn "the prebuilt exe names build $build, not the manifest's $(kv build "$manifest")"; return 1; }
    mkdir -p "$bin_dir"
    cp -f "$staged"/* "$bin_dir/" || { warn "cannot copy into $bin_dir"; return 1; }
    return 0
}

stage="$(mktemp -d)"; trap 'rm -rf "$stage"' EXIT
step "Installing the simulator $want from this plugin (simulator/dist) into $bin_dir"
install_from_plugin || {
    echo "ERROR: the prebuilt simulator $want could not be installed (above). The plugin ships no simulator sources, so" >&2
    echo "       there is no local build: reinstall or update the plugin." >&2
    exit 1; }
v="$(sim_check "$exe")" || { echo "ERROR: $v" >&2; exit 1; }
echo "SIMULATOR READY: $exe"
echo "  $v"
exit 0
