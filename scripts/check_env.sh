#!/usr/bin/env bash
# Linux/macOS mirror of check_env.ps1: check the WowCube toolchain. Everything a game needs comes from this
# plugin (the public game API in api/, the prebuilt simulator in simulator/dist): no octavios or telemetry checkout.
# Reports only (distros differ): prints the install line for what is missing.
#
#   simulator  wowcube-sim (~/.wowcube/sim/<version>/<os> or $WOWCUBE_SIM_DIR) present and answering --version with
#              the version this plugin needs (sim_version in api/SOURCE; a stale build is not OK); else MISSING
#              with the get_sim.sh command (it installs the prebuilt simulator this plugin carries); run only after
#              the user agreed
#              + xvfb-run on Linux (hidden runs: no window on the user's display) and the system libraries the
#              prebuilt Linux simulator loads (OpenGL/EGL, BlueZ libbluetooth3, libsystemd)
#   plugin     a C++20 compiler for the game plugin (macOS: Xcode command-line tools clang; Linux: g++ or clang++)
#   device     .oct build: cmake, ninja, arm-none-eabi-g++; the public game API (api/apps + api/include)
#   assets     python3 3.11+ with Pillow/numpy/pytoshop/psd-tools/requests, ffmpeg
#   info       Codex CLI logged in with ChatGPT, ffprobe, Node.js + Playwright + Chromium (optional: only HTML
#              prototypes and demo videos need them), uv (only octpack-build against an optional octavios checkout)
#
# Usage: check_env.sh [--workspace <dir>] [--report-only]      (--octavios <dir> is accepted and ignored)
# Exit 0 = everything required is present; 2 = something required is missing.
set -uo pipefail

WORKSPACE="$(pwd)"; OCTAVIOS=''
while [ $# -gt 0 ]; do
    case "$1" in
        --octavios)    OCTAVIOS="$2"; shift 2;;
        --workspace)   WORKSPACE="$2"; shift 2;;
        --report-only) shift;;
        *) echo "unknown argument: $1" >&2; exit 1;;
    esac
done
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
case "$(uname -s)" in Darwin) OS=macos;; *) OS=linux;; esac

have() { command -v "$1" >/dev/null 2>&1; }
ok()   { echo "  [ok]      $1"; }
info() { echo "  [info]    $1"; }
missing=()
miss() { echo "  [MISSING] $1  -> $2"; missing+=("$1"); }

echo "==> WowCube toolchain (public game API in $REPO_ROOT/api, prebuilt simulator in $REPO_ROOT/simulator/dist)"
[ -n "$OCTAVIOS" ] && info "--octavios is ignored: no octavios or telemetry checkout is needed"

# --- C++ compiler (game plugin) -------------------------------------------------------------------------
cxx=''
if [ -n "${CXX:-}" ] && have "${CXX%% *}"; then cxx="$CXX"
elif have c++; then cxx="$(command -v c++)"
elif have clang++; then cxx="$(command -v clang++)"
elif have g++; then cxx="$(command -v g++)"; fi
if [ -n "$cxx" ]; then ok "C++ compiler for the game plugin (tools/sim/build_game.sh): $cxx"
elif [ "$OS" = macos ]; then miss "C++ compiler (game plugin)" "xcode-select --install (the user runs it: it opens Apple's installer)"
else miss "C++ compiler (game plugin)" "see the install line below (g++ or clang)"; fi

# --- simulator --------------------------------------------------------------------------------------
. "$REPO_ROOT/tools/sim/sim_path.sh"
SIM="$(sim_exe)"
# the plugin carries the prebuilt simulator (simulator/dist/<version>, tools/sim/stage_dist.py): get_sim installs it
dist_ready=0
[ -f "$REPO_ROOT/simulator/dist/$(sim_version)/manifest.txt" ] && dist_ready=1
# OK only for the version this plugin needs (api/SOURCE): a stale build answers --version too
if sim_line="$(sim_check "$SIM")"; then ok "simulator: $sim_line"
else
    # always MISSING (exit 2), even when the plugin carries it: installing it puts software on the machine, which waits
    # for the user's one-time environment approval (new_app.sh --get-sim runs get_sim.sh after it)
    if [ -x "$SIM" ]; then what="simulator: $sim_line"; else what="simulator: not installed"; fi
    if [ "$dist_ready" -eq 1 ]; then miss "$what; this plugin carries it prebuilt, get_sim installs it (no download)" \
              "bash $REPO_ROOT/tools/sim/get_sim.sh (after the user approved it)"
    else miss "$what; this plugin carries no prebuilt simulator $(sim_version) (simulator/dist): an incomplete plugin" \
              "reinstall or update the plugin, then bash $REPO_ROOT/tools/sim/get_sim.sh"; fi
fi
if [ "$OS" = linux ]; then
    if have xvfb-run && have setsid; then ok "xvfb-run (hidden simulator runs)"
    else miss "xvfb-run (hidden simulator runs never open a window on the user's display)" "apt install xvfb / pacman -S xorg-server-xvfb"; fi
    # the prebuilt simulator's system libraries (its SDL3 comes with it)
    for lib in libOpenGL.so.0 libEGL.so.1 libbluetooth.so.3 libsystemd.so.0; do
        if ldconfig -p 2>/dev/null | grep -q "$lib"; then ok "$lib (the prebuilt simulator loads it)"
        else miss "$lib (the prebuilt simulator loads it)" "apt install libopengl0 libegl1 libbluetooth3 libsystemd0 (or your distribution's packages)"; fi
    done
fi

# --- device .oct build ----------------------------------------------------------------------------------
if [ -f "$REPO_ROOT/api/apps/CMakeLists.txt" ] && [ -f "$REPO_ROOT/api/include/oct_api.h" ]; then
    ok "public game API + module build (api/include, api/apps)"
else miss "api/include or api/apps (the public game API)" "the plugin is incomplete: reinstall or update it"; fi
for t in cmake ninja arm-none-eabi-g++; do
    if have "$t"; then ok "$t (ARM build)"; else miss "$t (ARM build)" "see the install line below"; fi
done
have uv && info "uv found (only octpack-build against an optional octavios checkout uses it)"

# --- assets ----------------------------------------------------------------------
if have python3 && ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    miss "python 3.11+ (python3 is older; the pinned numpy needs 3.11)" "see the install line below (python3, python3-venv, python3-pip), or uv python install 3.12"
elif have python3; then
    absent=$(python3 -c "import importlib.util as u; print(' '.join(m for m in ['PIL','numpy','pytoshop','psd_tools','requests','segno'] if u.find_spec(m) is None))")
    if [ -n "$absent" ]; then miss "python packages: $absent" "python3 -m venv ~/.wowcube/venv && . ~/.wowcube/venv/bin/activate && pip install -r <skills repo>/scripts/requirements.txt (a venv: Homebrew and Debian/Ubuntu Python refuse a global pip install, PEP 668; activate it before running the pipeline)"
    else ok "python3 + Pillow/numpy/pytoshop/psd-tools/requests/segno"; fi
else miss "python3 (3.11+)" "see the install line below (python3, python3-venv, python3-pip)"; fi
if have ffmpeg; then ok "ffmpeg (sound encoding)"; else miss "ffmpeg (sound encoding)" "see the install line below"; fi
if have ffprobe; then ok "ffprobe (video checks)"
elif have ffmpeg; then info "ffprobe not found next to ffmpeg: wowcube-demo-video checks its output with it (part of the ffmpeg package)"; fi

# --- informational -----------------------------------------------------------------
if have codex; then
    # the login probe never sees a provider key (same list as art_codex.codex_env: these names plus *_API_KEY /
    # *_API_TOKEN)
    unset_args=()
    for v in $(env | sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1/p'); do
        case " OPENAI_API_KEY CODEX_API_KEY OPENAI_BASE_URL OPENROUTER_API_KEY IMAGE_API GEMINI_API_KEY GOOGLE_API_KEY XAI_API_KEY ANTHROPIC_API_KEY DEEPSEEK_API_KEY FAL_KEY REPLICATE_API_TOKEN ELEVENLABS_API_KEY " in *" $(printf '%s' "$v" | tr '[:lower:]' '[:upper:]') "*) unset_args+=(-u "$v"); continue;; esac
        case "$(printf '%s' "$v" | tr '[:lower:]' '[:upper:]')" in *_API_KEY|*_API_TOKEN) unset_args+=(-u "$v");; esac
    done
    status=$(env ${unset_args[@]+"${unset_args[@]}"} codex login status 2>&1 | head -n 1)
    case "$status" in *ChatGPT*) info "Codex CLI logged in ($status): used only when the user says it is theirs and chooses it";;
                      *) info "Codex CLI not logged in with ChatGPT ($status): the user runs 'codex login'";; esac
else info "Codex CLI not found: sprites are the procedural style (agent-drawn in code, final quality) unless the user explicitly opts in to a paid image API (cube_asset-builder references/ART.md)"; fi
# optional: only the HTML prototype and demo video skills need Node.js + Playwright + Chromium. Playwright is never
# installed into the plugin folder: record_html.mjs and its probe (check_playwright.cjs) look in $WOWCUBE_NODE_DIR,
# ~/.wowcube/node, the workspace, then the recorder's folder (a global npm install does not count), and that
# Playwright's chromium.executablePath() must exist (Linux ~/.cache/ms-playwright, macOS
# ~/Library/Caches/ms-playwright, or PLAYWRIGHT_BROWSERS_PATH: Playwright knows).
if have node; then
    recdir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/skills/wowcube-html-prototype/scripts"
    pwrc=0; probe=$(cd "$WORKSPACE" 2>/dev/null && node "$recdir/check_playwright.cjs" 2>/dev/null) || pwrc=$?
    if [ "$pwrc" -eq 0 ]; then info "Node.js $(node --version) + Playwright + Chromium ($probe) (HTML prototypes, demo videos)"
    elif [ "$pwrc" -eq 3 ]; then info "Playwright found but its Chromium is not ($probe) (optional, prototypes/videos): npx --prefix ~/.wowcube/node playwright install chromium, after the user approved the download"
    else info "Node.js found, Playwright not installed (optional, prototypes/videos): npm i --prefix ~/.wowcube/node playwright && npx --prefix ~/.wowcube/node playwright install chromium, after the user approved the download (never into the plugin folder)"; fi
else info "Node.js not found (optional: only HTML prototypes and demo videos need Node.js + Playwright + Chromium)"; fi

echo ''
if [ "${#missing[@]}" -eq 0 ]; then echo "Toolchain OK."; exit 0; fi
echo "Missing ${#missing[@]} item(s)."
if [ "$OS" = macos ]; then
    echo "Install (macOS, Homebrew):  brew install python@3.12 cmake ninja sdl3 ffmpeg && brew install --cask gcc-arm-embedded"
elif have pacman; then
    echo "Install (Arch):  sudo pacman -S python python-pip cmake gcc sdl3 bluez bluez-libs systemd-libs arm-none-eabi-gcc arm-none-eabi-newlib ninja ffmpeg xorg-server-xvfb"
elif have apt; then
    echo "Install (Debian/Ubuntu):  sudo apt install python3 python3-venv python3-pip cmake g++ libbluetooth-dev libsystemd-dev gcc-arm-none-eabi libnewlib-arm-none-eabi ninja-build ffmpeg xvfb  (SDL3: libsdl3-dev where packaged, else built from source)"
fi
# Never pipe a downloaded script into a shell (curl ... | sh): install from the distro's package manager or pipx,
# after the user approved the download (skills/cube_orchestrator/references/AGENT_SAFETY.md).
echo "Python packages (in a venv; Homebrew and Debian/Ubuntu Python refuse a global pip install, PEP 668):"
echo "  python3 -m venv ~/.wowcube/venv && . ~/.wowcube/venv/bin/activate && pip install -r $REPO_ROOT/scripts/requirements.txt"
echo "After installing: restart Claude Code (close it and open it again in the same folder; activate the venv first), then re-run this check."
exit 2
