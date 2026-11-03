#!/usr/bin/env bash
# The demo's capture (copy into the game's scripts/): tests/capture.cpp plays a scripted session on the
# host -- the real rules and render, a robot at the controls -- and capture.h writes every frame to
# docs/demo/frames.jsonl (sprite mode) or renders it with the engine into docs/demo/net/ (net mode).
# render_demo.py makes the video from it.
# Needs the INTERNAL SDK: the host test shim tests/oct_test_shim.h of a WowCube developer's SDK checkout. The kit
# ships only the public game API (api/), no engine; external users make videos with method A (HTML prototype).
# Usage:  scripts/capture_demo.sh [path-to-SDK]          (default: the folder next to this game that has engine/oct_api.h
#                                                         and tests/oct_test_shim.h)
#         CAPTURE_NET=1 scripts/capture_demo.sh            net mode: pack the art first (index.bin + art/packed,
#                                                          e.g. build_pipeline.py pack --app-dir / repack_app.py)
#         CXX=g++-14 scripts/capture_demo.sh               another GNU g++ (default: g++)
set -eu
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
oct="${1:-}"
if [ -z "$oct" ]; then
    for d in "$here"/../*/; do
        if [ -f "$d/engine/oct_api.h" ] && [ -f "$d/tests/oct_test_shim.h" ]; then oct="${d%/}"; break; fi
    done
fi
[ -n "$oct" ] && [ -f "$oct/engine/oct_api.h" ] || { echo "the SDK is not next to this game: give its path" >&2; exit 2; }
[ -f "$oct/tests/oct_test_shim.h" ] || {
    echo "methods B/C need the internal SDK: $oct/tests/oct_test_shim.h not found (the kit's simulator/ does not" >&2
    echo "ship it). External users: record the HTML prototype instead (method A)." >&2
    exit 2; }
cxx="${CXX:-g++}"
net="${CAPTURE_NET:-0}"
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT
mkdir -p "$here/docs/demo"
if [ "$net" != "0" ]; then rm -rf "$here/docs/demo/net"; mkdir -p "$here/docs/demo/net"; fi
"$cxx" -std=c++20 -w -O2 -DOCTSIM -DTELEM_QUIET -DCAPTURE_NET="$net" -DCAPTURE_DIR="\"$here/docs/demo\"" \
    -I "$oct/tests" -I "$oct/engine" -I "$oct/sim/src" -I "$here/src" -I "$here/tests" \
    "$here/tests/capture.cpp" -lpthread -o "$out/capture"
(cd "$out" && ./capture "$here")
