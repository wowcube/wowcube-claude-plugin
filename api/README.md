# Public game API

What a WowCube game compiles against, and nothing else: no engine or simulator implementation is part of this
plugin. A game is compiled as a cube module (`OCT_APP_MODULE`): every engine call goes through the import table the
cube (or the simulator) fills when it loads the game, so the game needs only the declarations below.

| Path | What | Used by |
|---|---|---|
| `include/` | `oct_api.h` (the header games include) and the headers it pulls in: the import table and its call macros (`OCT_add`, `SND_play`, ...), the types (`octSprite_t`, `octTm_t`, ...), the constants and enums the calls take, and the module's libc stand-ins (`oct_freestanding.h`: `memset`, `snprintf` = `OCT_snprintf`, `sinf`, ...) | every build of a game |
| `apps/` | the device module glue: `src/app_module.cpp` (the export table: the game's callbacks), `src/app_module.ld` (the module's memory layout on the cube), `CMakeLists.txt` (the ARM build and its flags) | `scripts/build_device.*` |
| `plugin/` | the simulator's game-plugin glue: `sim_module.cpp` (the plugin's entry point) and `oct_sim_plugin.h` (the plugin ABI the prebuilt simulator checks) | `tools/sim/build_game.*` |
| `SOURCE` | the commit of the (private) engine sources these files were generated from, the simulator version they match, and the sha256 of every file | `tools/sim/sim_path.*`, `tools/sim/stage_dist.py`, tests |

`templates/app_ai_template/API.md` documents this surface: every call, type and constant it names is here, and the
engine's internal functions are not (they are not importable by a module anyway). The prebuilt simulator
(`simulator/dist`) is built from the same commit of the sources (`tests/test_sim_dist.py`).

## For maintainers

The files are generated, never edited by hand. With a checkout of the private sources repository
(wowcube/OCT_cube-sim-sources) at the commit whose simulator `simulator/dist` carries:

```
python tools/api/gen_api.py --sources <checkout>            # write api/ (records the commit in api/SOURCE)
python tools/api/gen_api.py --sources <checkout> --check    # compare only
python tools/api/check_api_parity.py --sources <checkout> --template [--app <packed game> ...] [--host]
```

`gen_api.py` keeps only the headers a module build includes, resolves their conditionals for a module build
(`OCT_APP_MODULE` defined, `OCTSIM` not), and keeps a declaration only when the public surface needs it: the names
API.md documents, the names the template and `src/app_structure_example.h` use, the names the glue uses, and,
transitively, what those need. `check_api_parity.py` is the proof that nothing a game needs was lost: it builds each
game against the full engine and against `api/` and requires the same ARM image (`out/<app>.bin`, byte for byte), the
same `.oct` except the build id and the CRC, and (`--host`) the same simulator-plugin machine code.
