#pragma once
// [STANDALONE] The game-plugin ABI of the standalone WowCube simulator.
//
// A game is compiled ONCE as a shared library (<app_dir>/out/sim/<app>.dll|.dylib|.so) from plugin/sim_module.cpp,
// the simulator's analogue of apps/src/app_module.cpp: the game sees exactly what it sees on the cube (OCT_APP_MODULE,
// every engine call through OCT_APP_IMPORTS), plus TL = thread_local because the simulator runs the eight modules as
// eight threads (OCT_SIM_PLUGIN). The library exports one C symbol, OCT_SIM_ENTRY_SYMBOL, that returns the struct
// below. The simulator checks it, fills *imports with OCT_app_fill_imports (the same list the cube's binder uses) and
// binds the callbacks on each module thread when the engine starts the app (OctSimBindLinkedApp).
//
// Include after the engine types (oct_app_module.h + oct_shared.h): host side after oct.h, plugin side after
// oct_app_module.h.

#include <stdint.h>
#include <stddef.h>

#define OCT_SIM_PLUGIN_MAGIC    0x50534F57u     // "WOSP"
#define OCT_SIM_PLUGIN_VERSION  1u              // bump when this struct changes shape
#define OCT_SIM_ENTRY_SYMBOL    "oct_sim_game_entry"
#define OCT_SIM_HOST_SYMBOL     "oct_sim_host_imports"   // exported by the simulator: its filled import table (const octAppImports_t*)

// Layout fingerprint: the host compares every field with its own. Host and plugin are built by different compilers
// (MSVC host, clang-cl plugin on Windows), so the structs the two exchange by pointer must agree byte for byte.
typedef struct
{
    uint32_t ptr_size;          // sizeof(void*)
    uint32_t bool_size;         // sizeof(bool)
    uint32_t imports_size;      // sizeof(octAppImports_t)
    uint32_t tm_size;           // sizeof(octTm_t)
    uint32_t sprite_size;       // sizeof(octSprite_t)
    uint32_t sprite_align;      // alignof(octSprite_t)
    uint32_t bmpinfo_size;      // sizeof(octBmpInfo_t)
    uint32_t entryinfo_size;    // sizeof(octEntryInfo_t)
    uint32_t tapsource_size;    // sizeof(octTapSource_t)
    uint32_t cubepose_size;     // sizeof(octCubePose_t)
    uint32_t modulepose_size;   // sizeof(octModulePose_t)
    uint32_t stats_size;        // sizeof(octCubeStats_t)
    uint32_t diag_size;         // sizeof(octDiagnosticInfo_t)
    uint32_t imports_last_slot; // offsetof(octAppImports_t, cube_pose_visual)
} octSimLayout_t;

#define OCT_SIM_LAYOUT_INIT { (uint32_t)sizeof(void*), (uint32_t)sizeof(bool), (uint32_t)sizeof(octAppImports_t),      \
    (uint32_t)sizeof(octTm_t), (uint32_t)sizeof(octSprite_t), (uint32_t)alignof(octSprite_t),                           \
    (uint32_t)sizeof(octBmpInfo_t), (uint32_t)sizeof(octEntryInfo_t), (uint32_t)sizeof(octTapSource_t),                 \
    (uint32_t)sizeof(octCubePose_t), (uint32_t)sizeof(octModulePose_t), (uint32_t)sizeof(octCubeStats_t),               \
    (uint32_t)sizeof(octDiagnosticInfo_t), (uint32_t)offsetof(octAppImports_t, cube_pose_visual) }

typedef struct
{
    uint32_t            magic;              // OCT_SIM_PLUGIN_MAGIC
    uint32_t            version;            // OCT_SIM_PLUGIN_VERSION
    uint32_t            app_abi_version;    // OCT_APP_ABI_VERSION the game was compiled against
    uint32_t            entry_size;         // sizeof(octSimGameEntry_t)
    octSimLayout_t      layout;

    octAppImports_t*    imports;            // the plugin's OCT_APP_IMPORTS; the host fills it before any callback

    // octAppExports_t's callbacks, as native pointers (on_init and on_tick are required; the rest may be NULL)
    void (*on_init)       (void);
    void (*on_tick)       (void);
    void (*on_pretwisted) (int32_t twid);
    void (*on_twisted)    (int32_t twid, uint32_t disconnected_ms);
    void (*on_tap)        (int32_t tapid, int32_t count);
    void (*on_shake)      (int32_t shakeid);
    void (*on_proc_draw)  (uint16_t* back, int idx, float x, float y, int angle, int vid, int reserved);
    void (*on_save)       (void);
    void (*on_save_synced)(int32_t result);
    void (*on_dock)       (int32_t docked);

    // app_metadata.h, as the packer stamps it into the pack header
    const char*         app_name;           // the *.target stem the plugin was built for (OCT_SIM_APP_NAME)
    const char*         title;              // APP_TITLE or NULL
    uint64_t            guid1;              // APP_GUID1 (0 when undeclared)
    uint32_t            app_version;        // APP_VERSION
    uint32_t            categories;         // APP_CATEGORIES
    uint32_t            colors;             // APP_COLORS
    uint32_t            has_save_size;      // 1 when APP_SAVE_SIZE is declared
    uint32_t            save_size;          // APP_SAVE_SIZE
    uint32_t            reserved[8];        // [0]: 1 = the plugin pulled the imports before its constructors ran
} octSimGameEntry_t;

typedef const octSimGameEntry_t* (*octSimGameEntryFn)(void);
