# Public game API

What a WowCube game compiles against, and nothing else: no engine or simulator implementation is part of this
plugin. A game is compiled as a cube module (`OCT_APP_MODULE`): every engine call goes through the import table the
cube (or the simulator) fills when it loads the game, so the game needs only the declarations below.

| Path | What | Used by |
|---|---|---|
| `include/` | `oct_api.h` (the header games include) and the headers it pulls in: the import table and its call macros (`OCT_add`, `SND_play`, ...), the types (`octSprite_t`, `octTm_t`, ...), the constants and enums the calls take, and the module's libc stand-ins (`oct_freestanding.h`: `memset`, `snprintf` = `OCT_snprintf`, `sinf`, ...) | every build of a game |
| `apps/` | the device module glue: `src/app_module.cpp` (the export table: the game's callbacks), `src/app_module.ld` (the module's memory layout on the cube), `CMakeLists.txt` (the ARM build and its flags) | `scripts/build_device.*` |
| `plugin/` | the simulator's game-plugin glue: `sim_module.cpp` (the plugin's entry point) and `oct_sim_plugin.h` (the plugin ABI the prebuilt simulator checks) | `tools/sim/build_game.*` |
| `SOURCE` | the simulator version these files match and the sha256 of every file | `tools/sim/sim_path.*` |

`templates/app_ai_template/API.md` documents this surface: every call, type and constant it names is here, and the
engine's internal functions are not (they are not importable by a module anyway). The prebuilt simulator
(`simulator/dist`) is built from the same engine version as these files. The files are generated: never edit them
by hand.
