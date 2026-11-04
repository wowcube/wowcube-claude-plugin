#!/usr/bin/env bash
# Build a game's simulator plugin on Linux or macOS: <app_dir>/out/sim/<app>.so | <app>.dylib
#
#   tools/sim/build_game.sh <app_dir> [-D NAME=VALUE ...] [--define NAME=VALUE,NAME=VALUE] [--debug]
#                           [--arm-gcc <arm-none-eabi-g++>] [--no-device-check] [--out-dir <dir>]
#                           [--allow-double-literals] [--api-dir <dir>]
#
# Compiles api/plugin/sim_module.cpp with the game's src/app.h, against the public game API (api/include), as a shared
# library the standalone simulator loads with --game <app_dir>: the game compiled as on the cube (OCT_APP_MODULE, every engine call through the import
# table) with TL = thread_local (OCT_SIM_PLUGIN). Compiler: $CXX, else c++ (macOS: Apple clang; Linux: g++ or clang++).
# Defines (as tools/sim/build_game.ps1 -Define): the whole "#define NAME ..." (continuation lines included) in a snapshot
# of src/ (<app_dir>/out/sim/obj/src) is replaced by the literal value, so unguarded test hooks are overridden too; a
# NAME no source defines becomes -DNAME=VALUE.
# Device check (default; --no-device-check skips it): the snapshot is first compiled with arm-none-eabi-g++ and the
# cube's flags (api/apps: -Werror, -Werror=double-promotion, -Werror=float-conversion, -fsingle-precision-constant),
# syntax only, so a game that would not build for the cube fails here. g++ plugins also get -fsingle-precision-constant
# (the cube's float semantics); clang has no such flag (unsuffixed literals are double there), see simulator/README.md.
# --api-dir (maintainers): compile against another header tree (include/ or engine/, plugin/, apps/src/) instead of
# <plugin>/api: an API parity check passes a sources checkout to compare the two builds.
# Source rules (tools/sim/game_lint.py, always): an unsuffixed floating literal (0.5, not 0.5f) fails the build - the
# cube reads it as float, clang as double; --allow-double-literals skips that rule for old games. Static constructors
# (__attribute__((constructor)), init_priority) are refused: they may run before the plugin's imports are bound.
# --out-dir: where the library, snapshot and logs go (default <app_dir>/out/sim); a coder's compile check passes its
# scratch folder (<ws>/.agent_scratch/pNN/build) and leaves the app folder untouched.
# The app folder is only read, except <app_dir>/out/sim/. Starts nothing.
# Exit codes: 0 ok; 1 any other failure (the C++ compiler, game_lint, the plugin compile); 3 arm-none-eabi-g++ not found
# (device check); 4 the game fails the device check (arm-none-eabi-g++, the cube's -Werror flags).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
app_dir=""; defs=(); opt=(-O2); arm_gcc=""; device_check=1; out_dir=""; allow_double=0; api_dir=""

while [ $# -gt 0 ]; do
    case "$1" in
        -D) defs+=("$2"); shift ;;
        -D*) defs+=("${1#-D}") ;;
        --define|-Define) IFS=',' read -r -a more <<< "$2"; defs+=(${more[@]+"${more[@]}"}); shift ;;
        --debug) opt=(-O0 -g) ;;
        --arm-gcc) arm_gcc="$2"; shift ;;
        --no-device-check) device_check=0 ;;
        --allow-double-literals) allow_double=1 ;;
        --out-dir) out_dir="$2"; shift ;;
        --api-dir) api_dir="$2"; shift ;;
        -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
        -*) echo "ERROR: unknown option $1" >&2; exit 1 ;;
        *) app_dir="$1" ;;
    esac
    shift
done
[ -n "$app_dir" ] || { echo "usage: build_game.sh <app_dir> [-D NAME=VALUE ...]" >&2; exit 1; }
[ -d "$app_dir" ] || { echo "ERROR: app folder not found: $app_dir" >&2; exit 1; }
app_dir="$(cd "$app_dir" && pwd)"
shopt -s nullglob
targets=("$app_dir"/*.target)
[ ${#targets[@]} -eq 1 ] || { echo "ERROR: $app_dir must hold exactly one *.target marker (found ${#targets[@]})" >&2; exit 1; }
app="$(basename "${targets[0]}" .target)"
[[ "$app" =~ ^[a-z]{3}_[A-Za-z0-9_]+$ ]] || { echo "ERROR: invalid app name '$app'" >&2; exit 1; }
[ -f "$app_dir/src/app.h" ] || { echo "ERROR: $app_dir/src/app.h not found" >&2; exit 1; }
command -v perl >/dev/null || { echo "ERROR: perl not found (it rewrites the -D defines in the source snapshot)" >&2; exit 1; }
# the public game API: the headers a game compiles against (api/include), the plugin entry point (api/plugin) and the
# device module glue (api/apps); no engine or simulator source
if [ -n "$api_dir" ]; then api="$(cd "$api_dir" && pwd)"; else api="$repo/api"; fi
inc="$api/include"; [ -f "$inc/oct_api.h" ] || inc="$api/engine"
[ -f "$inc/oct_api.h" ] && [ -f "$api/plugin/sim_module.cpp" ] || {
    echo "ERROR: public game API not found ($api: include/oct_api.h, plugin/sim_module.cpp) - incomplete plugin" >&2; exit 1; }

case "$(uname -s)" in
    Darwin) ext=dylib; shared=(-dynamiclib -Wl,-undefined,error) ;;
    Linux)  ext=so;    shared=(-shared -Wl,--no-undefined -ldl) ;;
    *) echo "ERROR: unsupported OS $(uname -s) (Windows: tools/sim/build_game.ps1)" >&2; exit 1 ;;
esac
cxx="${CXX:-c++}"
command -v "$cxx" >/dev/null || { echo "ERROR: C++ compiler '$cxx' not found (set CXX)" >&2; exit 1; }

if [ -n "$out_dir" ]; then mkdir -p "$out_dir"; out="$(cd "$out_dir" && pwd)"; else out="$app_dir/out/sim"; fi
obj="$out/obj"; snap="$obj/src"
rm -rf "$snap"; mkdir -p "$obj"
cp -R "$app_dir/src" "$snap"

dflags=()
for d in ${defs[@]+"${defs[@]}"}; do
    [ -n "$d" ] || continue
    n="${d%%=*}"; v="1"; [[ "$d" == *=* ]] && v="${d#*=}"
    [[ "$n" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || { echo "ERROR: bad define '$d'" >&2; exit 1; }
    hit=0
    while IFS= read -r -d '' f; do
        if grep -Eq "^[[:space:]]*#[[:space:]]*define[[:space:]]+$n([[:space:]]|$)" "$f"; then
            # the value goes in literally (no regex/replacement syntax), the whole continued definition is replaced
            DEF_NAME="$n" DEF_VALUE="$v" perl -0pi -e \
                's/^([ \t]*#[ \t]*define[ \t]+\Q$ENV{DEF_NAME}\E)\b(?!\()(?:[^\n]*\\\r?\n)*[^\r\n]*/$1 . " " . $ENV{DEF_VALUE} . "   \/\/ [build_game -D]"/gme' "$f"
            echo "    $n = $v  (in $(basename "$f"))"; hit=1
        fi
    done < <(find "$snap" -type f \( -name '*.h' -o -name '*.hpp' -o -name '*.c' -o -name '*.cpp' \) -print0)
    [ $hit -eq 1 ] || { dflags+=("-D$n=$v"); echo "    $n = $v  (compiler -D)"; }
done

# source rules: float literals as the cube reads them, no early static constructors
# the pipeline Python on Linux/macOS is ~/.wowcube/venv (install.sh makes it): system Pythons lack the packages
[ -x "$HOME/.wowcube/venv/bin/python3" ] && PATH="$HOME/.wowcube/venv/bin:$PATH"
PY=python3; command -v python3 >/dev/null 2>&1 || PY=python
command -v "$PY" >/dev/null 2>&1 || { echo "ERROR: python not found: build_game checks the sources with tools/sim/game_lint.py" >&2; exit 1; }
lint_args=("$here/game_lint.py" "$snap")
[ "$allow_double" -eq 0 ] || { lint_args+=(--allow-double-literals); echo "    float literals: not checked (--allow-double-literals)"; }
"$PY" "${lint_args[@]}" || { echo "ERROR: the game's sources break a simulator/cube parity rule (above; file:line in src/)" >&2; exit 1; }

if [ "$device_check" -eq 1 ]; then
    [ -n "$arm_gcc" ] || arm_gcc="$(command -v arm-none-eabi-g++ || true)"
    [ -n "$arm_gcc" ] && [ -x "$arm_gcc" ] || {
        echo "ERROR: arm-none-eabi-g++ not found: the device check compiles the game as the cube does (install the Arm GNU" >&2
        echo "       Toolchain / gcc-arm-none-eabi, or pass --arm-gcc; --no-device-check skips it and lets device-only errors through)" >&2
        exit 3; }
    echo "==> device check: $(basename "$arm_gcc") -Werror (api/apps flags, syntax only)"
    if ! "$arm_gcc" -mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16 -std=c++20 -Os -Wall \
            -Werror=float-conversion -Werror=double-promotion -Werror -ffreestanding -fno-builtin -fsingle-precision-constant \
            -fno-exceptions -fno-rtti -fno-threadsafe-statics -fno-use-cxa-atexit -DOCT_APP_MODULE -fsyntax-only \
            ${dflags[@]+"${dflags[@]}"} -I"$snap" -I"$inc" "$api/apps/src/app_module.cpp" > "$obj/device_check.log" 2>&1; then
        head -n 40 "$obj/device_check.log" >&2
        echo "ERROR: the game does not compile for the cube (arm-none-eabi-g++, device flags, -Werror) - fix it before simulating; log: $obj/device_check.log" >&2
        exit 4
    fi
fi

# float semantics: g++ can take the cube's single-precision literals; clang cannot (it reports the promotions instead)
fpflags=(-Wdouble-promotion -Wfloat-conversion)
if "$cxx" --version 2>/dev/null | grep -qiE 'gcc|g\+\+|free software foundation'; then fpflags+=(-fsingle-precision-constant); fi

lib="$out/$app.$ext"
echo "==> compiling $lib ($cxx)"
rm -f "$lib"
set +e
"$cxx" -std=c++20 "${opt[@]}" -fPIC -fvisibility=hidden -fno-builtin -fno-exceptions -fno-rtti \
    -Wall -Wno-unused-parameter -Wno-unused-function -Wno-unused-variable -Wno-missing-field-initializers "${fpflags[@]}" \
    -DOCT_APP_MODULE -DOCT_SIM_PLUGIN "-DOCT_SIM_APP_NAME=\"$app\"" ${dflags[@]+"${dflags[@]}"} \
    -I"$snap" -I"$inc" -I"$api/plugin" \
    "$api/plugin/sim_module.cpp" "${shared[@]}" -o "$lib" > "$obj/build.log" 2>&1
rc=$?
set -e
cat "$obj/build.log"
[ "$rc" -eq 0 ] && [ -f "$lib" ] || { echo "ERROR: plugin build failed - log: $obj/build.log" >&2; exit 1; }
echo "BUILD OK: $lib"
[ -z "$out_dir" ] || exit 0   # a compile check: the simulator loads only <app_dir>/out/sim
. "$here/sim_path.sh"
echo "  run: $(sim_exe) --game $app_dir [--headless --mute --seconds 20 --frames <dir>]"
exit 0
