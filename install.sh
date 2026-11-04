#!/usr/bin/env bash
# WowCube Create: one-command install for macOS and Linux.
#   curl -fsSL https://raw.githubusercontent.com/wowcube/wowcube-create/main/install.sh | bash
# Installs (or upgrades) the Claude Code plugin and every tool a game build needs: on macOS with Homebrew (python,
# cmake, ninja, sdl3, ffmpeg, the ARM toolchain; the ARM toolchain's installer asks for your password), on Linux it
# checks the system packages first and prints the one apt line that needs your password; then the Python packages
# in ~/.wowcube/venv and the build checker (get_sim.sh). Up to about 4 GB and 30-60 minutes on a clean computer.
# Running this command is the user's yes to those installs: it records install_consent in ~/.wowcube/config.json.
# The whole script is one function called on the last line, so a download cut short runs nothing.
set -u

wowcube_install() {
    local REPO=wowcube/wowcube-create
    local MARKET=wowcube-skills
    local PLUGIN="wowcube@$MARKET"
    local CONF="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
    say()  { printf '\033[36m==> %s\033[0m\n' "$*"; }
    fail() { printf '\033[31mSTOPPED: %s\033[0m\n' "$*"; exit 1; }
    have() { command -v "$1" >/dev/null 2>&1; }

    local OS
    OS=$(uname -s)
    if [ "$OS" = Darwin ]; then
        say "Setting up WowCube Create: up to about 4 GB and 30-60 minutes on a clean computer. Homebrew asks for your password once, for the cube's ARM compiler; after that you can leave it running."
    else
        say "Setting up WowCube Create: up to about 4 GB and 30-60 minutes on a clean computer. You can leave it running."
    fi

    have claude || fail "Claude Code is not installed. Install it first (https://claude.com/claude-code), then run this command again."

    if [ "$OS" = Darwin ]; then
        if ! xcode-select -p >/dev/null 2>&1; then
            xcode-select --install >/dev/null 2>&1 </dev/null || true
            fail "Apple's developer tools are needed: finish the installer window that just opened, then run this command again."
        fi
        have brew || fail "Homebrew is needed: install it from https://brew.sh (it asks for your password), then run this command again."
    fi
    if ! have git; then
        if [ "$OS" = Darwin ]; then say "Installing git"; brew install git </dev/null || fail "git did not install."
        else fail "git is missing: install it (e.g. sudo apt install git), then run this command again."; fi
    fi

    # Linux: the system packages come first (they need the user's password, so the script cannot install them)
    local PY=""
    if [ "$OS" != Darwin ]; then
        local missing="" c t lib ldc tmp
        for c in python3.13 python3.12 python3.11 python3; do
            if have "$c" && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' </dev/null 2>/dev/null; then
                PY=$c; break
            fi
        done
        if [ -z "$PY" ]; then
            missing="$missing python3(3.11+)"
        else
            tmp=$(mktemp -d)
            "$PY" -m venv "$tmp/v" >/dev/null 2>&1 </dev/null || missing="$missing python3-venv"
            rm -rf "$tmp"
        fi
        for t in g++ cmake ninja ffmpeg arm-none-eabi-g++ xvfb-run; do have "$t" || missing="$missing $t"; done
        ldc=""
        if have ldconfig; then ldc=ldconfig; elif [ -x /sbin/ldconfig ]; then ldc=/sbin/ldconfig; fi
        if [ -n "$ldc" ]; then
            for lib in libOpenGL.so.0 libEGL.so.1 libbluetooth.so.3 libsystemd.so.0; do
                "$ldc" -p 2>/dev/null | grep -q "$lib" || missing="$missing $lib"
            done
        fi
        if [ -n "$missing" ]; then
            echo
            echo "Missing:$missing"
            echo "These need your password; run this line, then run the install command again:"
            echo "  sudo apt install python3 python3-venv python3-pip g++ cmake ninja-build ffmpeg gcc-arm-none-eabi libnewlib-arm-none-eabi xvfb libopengl0 libegl1 libbluetooth3 libsystemd0"
            echo "(Fedora (dnf) or Arch (pacman): install the same programs with your package manager; the package names differ a little."
            echo " If your python3 is older than 3.11, also install python3.12 and python3.12-venv or newer.)"
            exit 1
        fi
    fi
    # system Python for reading the CLI's JSON (macOS: the one Apple's developer tools bring)
    local JPY="${PY:-python3}"
    have "$JPY" || JPY=""

    say "Installing the WowCube plugin for Claude Code"
    # is the marketplace there, and does it point at $REPO? (ours / other / absent / unknown)
    local mstate="unknown"
    if [ -n "$JPY" ]; then
        mstate=$(claude plugin marketplace list --json </dev/null 2>/dev/null | "$JPY" -c '
import json, os, sys
name, repo, known = sys.argv[1], sys.argv[2].lower(), sys.argv[3]
entry = None
try:
    for m in json.load(sys.stdin):
        if m.get("name") == name:
            entry = m; break
    else:
        print("absent"); sys.exit(0)
except Exception:
    try:   # older CLI without --json: the config file it keeps
        with open(known, encoding="utf-8") as f:
            data = json.load(f)
        if name not in data:
            print("absent"); sys.exit(0)
        entry = dict(data[name].get("source") or {})
    except Exception:
        print("unknown"); sys.exit(0)
src = str(entry.get("source", "")).lower()
where = str(entry.get("repo") or entry.get("url") or "").lower().rstrip("/")
if where.endswith(".git"):
    where = where[:-4]
ok = (src == "github" and where == repo) or (src in ("git", "url") and where.endswith("github.com/" + repo))
print("ours" if ok else "other")' "$MARKET" "$REPO" "$CONF/plugins/known_marketplaces.json")
    fi
    case "$mstate" in
        ours)
            claude plugin marketplace update "$MARKET" </dev/null || fail "could not update the plugin marketplace (see above).";;
        other)
            say "The '$MARKET' plugin source on this computer points somewhere else; replacing it with $REPO."
            claude plugin marketplace remove "$MARKET" </dev/null || fail "could not remove the old plugin source (see above)."
            claude plugin marketplace add "$REPO" </dev/null || fail "could not add the plugin marketplace (see above).";;
        absent)
            claude plugin marketplace add "$REPO" </dev/null || fail "could not add the plugin marketplace (see above).";;
        *)
            claude plugin marketplace update "$MARKET" </dev/null 2>/dev/null || claude plugin marketplace add "$REPO" </dev/null \
                || fail "could not add the plugin marketplace (see above).";;
    esac

    # installed already (user scope) -> update it to the latest version, else install it
    local plist installed="no"
    plist=$(claude plugin list --json </dev/null 2>/dev/null)
    if [ -n "$JPY" ]; then
        installed=$(printf '%s' "$plist" | "$JPY" -c '
import json, sys
try:
    print("yes" if any(p.get("id") == sys.argv[1] and p.get("scope", "user") == "user" for p in json.load(sys.stdin)) else "no")
except Exception:
    print("no")' "$PLUGIN")
    fi
    if [ "$installed" = yes ]; then
        claude plugin update "$PLUGIN" </dev/null || fail "could not update the plugin (see above)."
    else
        claude plugin install "$PLUGIN" </dev/null || fail "could not install the plugin (see above)."
    fi

    # the plugin's folder, read fresh after the install or update: installPath from the plugin list, else the
    # marketplace clone (the plugin is its root)
    local ROOT=""
    if [ -n "$JPY" ]; then
        ROOT=$(claude plugin list --json </dev/null 2>/dev/null | "$JPY" -c '
import json, sys
try:
    rows = [p for p in json.load(sys.stdin) if p.get("id") == sys.argv[1]]
    rows.sort(key=lambda p: p.get("scope", "user") != "user")
    print(rows[0].get("installPath", "") if rows else "")
except Exception:
    pass' "$PLUGIN")
    fi
    [ -n "$ROOT" ] && [ -f "$ROOT/scripts/check_env.sh" ] || ROOT="$CONF/plugins/marketplaces/$MARKET"
    [ -f "$ROOT/scripts/check_env.sh" ] || fail "the plugin is installed but its folder was not found ($ROOT). Open Claude Code and say: install the WowCube plugin and everything it needs."

    say "Installing the tools that build and check games"
    if [ "$OS" = Darwin ]; then
        say "Homebrew now asks for your password for the cube's ARM compiler."
        brew install python@3.12 cmake ninja sdl3 ffmpeg </dev/null && brew install --cask gcc-arm-embedded </dev/null \
            || fail "a Homebrew install failed (see above)."
        PY=$(brew --prefix python@3.12)/bin/python3.12
    fi

    # running this command is the yes to these installs: record it for the WowCube setup (merge, never clobber)
    mkdir -p "$HOME/.wowcube"
    "$PY" - "$HOME/.wowcube/config.json" <<'PYEOF' || say "Could not record the install consent in ~/.wowcube/config.json; the WowCube setup will ask once."
import datetime, json, os, sys
path = sys.argv[1]
data = {}
if os.path.exists(path):
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)          # an unreadable file is left alone (the script says so)
    if not isinstance(data, dict):
        sys.exit(1)
data.setdefault("schema_version", 1)
data["install_consent"] = {"answer": "yes", "date": datetime.date.today().isoformat()}
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
os.replace(tmp, path)
PYEOF

    say "Installing the Python packages (in ~/.wowcube/venv)"
    "$PY" -m venv "$HOME/.wowcube/venv" </dev/null \
        && "$HOME/.wowcube/venv/bin/pip" install -q -r "$ROOT/scripts/requirements.txt" </dev/null \
        || fail "the Python packages did not install (see above)."

    say "Installing the build checker"
    bash "$ROOT/tools/sim/get_sim.sh" </dev/null || fail "the build checker did not install (see above)."

    say "Checking everything"
    if PATH="$HOME/.wowcube/venv/bin:$PATH" bash "$ROOT/scripts/check_env.sh" </dev/null; then
        echo
        printf '\033[32mDone. Close Claude Code if it is open, open it in a folder for your games, start a new session and say "I want to make a game for my WowCube".\033[0m\n'
    else
        echo
        echo "Almost done: some items above are still missing. Install them, or open Claude Code and say:"
        echo '"install the WowCube plugin and everything it needs".'
    fi
}

wowcube_install "$@"
