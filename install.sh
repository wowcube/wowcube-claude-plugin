#!/usr/bin/env bash
# WowCube Create: one-command install for macOS and Linux.
#   curl -fsSL https://raw.githubusercontent.com/wowcube/wowcube-create/main/install.sh | bash
# Installs the Claude Code plugin and every tool a game build needs: on macOS with Homebrew (python, cmake, ninja,
# sdl3, ffmpeg, the ARM toolchain), on Linux it prints the one apt line that needs your password; then the Python
# packages in ~/.wowcube/venv and the build checker (get_sim.sh). Running this command is the user's yes to those
# installs.
set -u

REPO=wowcube/wowcube-create
MARKET=wowcube-skills
PLUGIN="wowcube@$MARKET"
say()  { printf '\033[36m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[31mSTOPPED: %s\033[0m\n' "$*"; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

say "Setting up WowCube Create: a few GB on a clean computer, 20-60 minutes. You can leave it running."
OS=$(uname -s)

have claude || fail "Claude Code is not installed. Install it first (https://claude.com/claude-code), then run this command again."

if [ "$OS" = Darwin ]; then
    if ! xcode-select -p >/dev/null 2>&1; then
        xcode-select --install >/dev/null 2>&1 || true
        fail "Apple's developer tools are needed: finish the installer window that just opened, then run this command again."
    fi
    if ! have brew; then
        fail "Homebrew is needed: install it from https://brew.sh (it asks for your password), then run this command again."
    fi
fi
if ! have git; then
    if [ "$OS" = Darwin ]; then say "Installing git"; brew install git || fail "git did not install."
    else fail "git is missing: install it (e.g. sudo apt install git), then run this command again."; fi
fi

say "Installing the WowCube plugin for Claude Code"
if claude plugin marketplace list 2>/dev/null | grep -q "$MARKET"; then claude plugin marketplace update "$MARKET"
else claude plugin marketplace add "$REPO"; fi || fail "could not add the plugin marketplace (see above)."
claude plugin install "$PLUGIN" || fail "could not install the plugin (see above)."

# the plugin's folder: installPath from the plugin list, else the marketplace clone (the plugin is its root)
ROOT=""
if have python3; then
    ROOT=$(claude plugin list --json 2>/dev/null | python3 -c '
import json, sys
try:
    for p in json.load(sys.stdin):
        if p.get("id") == sys.argv[1] or p.get("name") == sys.argv[1]:
            print(p.get("installPath", "")); break
except Exception:
    pass' "$PLUGIN")
fi
[ -n "$ROOT" ] && [ -f "$ROOT/scripts/check_env.sh" ] || ROOT="$HOME/.claude/plugins/marketplaces/$MARKET"
[ -f "$ROOT/scripts/check_env.sh" ] || fail "the plugin is installed but its folder was not found ($ROOT). Open Claude Code and say: set up everything the WowCube plugin needs."

say "Installing the tools that build and check games"
if [ "$OS" = Darwin ]; then
    brew install python@3.12 cmake ninja sdl3 ffmpeg && brew install --cask gcc-arm-embedded \
        || fail "a Homebrew install failed (see above)."
    PY=$(brew --prefix python@3.12)/bin/python3.12
else
    if ! { have cmake && have ninja && have ffmpeg && have arm-none-eabi-g++ && have python3; }; then
        echo
        echo "These need your password; run this line, then run the install command again:"
        echo "  sudo apt install python3 python3-venv python3-pip cmake g++ libbluetooth-dev libsystemd-dev gcc-arm-none-eabi libnewlib-arm-none-eabi ninja-build ffmpeg xvfb"
        exit 1
    fi
    PY=python3
fi

say "Installing the Python packages (in ~/.wowcube/venv)"
mkdir -p "$HOME/.wowcube"
"$PY" -m venv "$HOME/.wowcube/venv" && "$HOME/.wowcube/venv/bin/pip" install -q -r "$ROOT/scripts/requirements.txt" \
    || fail "the Python packages did not install (see above)."

say "Installing the build checker"
bash "$ROOT/tools/sim/get_sim.sh" || fail "the build checker did not install (see above)."

say "Checking everything"
if PATH="$HOME/.wowcube/venv/bin:$PATH" bash "$ROOT/scripts/check_env.sh"; then
    echo
    printf '\033[32mDone. Open Claude Code in a folder for your games and say: "I want to make a game for my WowCube".\033[0m\n'
    echo "(If Claude Code was already open, close it and open it again first.)"
else
    echo
    echo "Almost done: some items above are still missing. Install them, or open Claude Code and say:"
    echo '"set up everything the WowCube plugin needs".'
fi
