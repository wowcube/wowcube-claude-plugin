#!/usr/bin/env bash
# Fork a working app into a NEW game: copy app_<old> to app_<new> with the marker, headers, includes and APP_DIR
# renamed, a fresh random APP_GUID1, the new APP_TITLE and version 0.0.0 (the first repack_app ships 0.1.0). The source is never changed.
# Linux/macOS entry point of scripts/fork_app.py (one implementation for every OS; the same rename rules new_app.sh
# applies to the template). Builds nothing and starts nothing: afterwards rebuild the plugin (tools/sim/build_game.sh)
# and repack (scripts/repack_app.py). assets_<old>/ and plans/<old>_* next to the source are copied when present.
#
# Usage: fork_app.sh --source <path>/app_<old> --name <new> [--workspace <ws>] [--title "New Title"] [--json]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# the pipeline Python on Linux/macOS is ~/.wowcube/venv (install.sh makes it): system Pythons lack the packages
[ -x "$HOME/.wowcube/venv/bin/python3" ] && PATH="$HOME/.wowcube/venv/bin:$PATH"
PY=python3; command -v python3 >/dev/null 2>&1 || PY=python
exec "$PY" "$SCRIPT_DIR/fork_app.py" "$@"
