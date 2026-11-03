// [STANDALONE] Game plugin entry point of the standalone simulator: the analogue of apps/src/app_module.cpp.
//
// Compiled with -DOCT_APP_MODULE -DOCT_SIM_PLUGIN -I<app>/src -I<simulator>/engine -I<simulator>/plugin into a shared
// library (tools/sim/build_game.ps1 | build_game.sh). OCT_APP_MODULE gives the game the cube's view of the engine
// (every call through OCT_APP_IMPORTS); OCT_SIM_PLUGIN makes TL thread_local, because the simulator runs the eight
// modules as eight threads that all call into this one library. The ABI is plugin/oct_sim_plugin.h.

#include "oct_app_module.h"

#include "oct_sim_plugin.h"

#if !defined(_WIN32)
#include <dlfcn.h>
#else
//kernel32, declared by hand: <windows.h> would collide with the engine's freestanding libc stand-ins
extern "C" __declspec(dllimport) void* __stdcall GetModuleHandleW(const wchar_t* name);
extern "C" __declspec(dllimport) void* __stdcall GetProcAddress(void* module, const char* name);
#endif

// One table for the whole process. On the cube the binder fills it BEFORE the module's C++ global constructors run
// (OCT_app_bind_module), so a constructor may call OCT_*. The loader runs a shared library's constructors inside
// LoadLibrary/dlopen, before the simulator could fill anything: so the plugin pulls the simulator's filled table
// itself, from its first dynamic initializer. It is defined here, ABOVE #include "app.h", and C++ initializes the
// non-inline variables of one translation unit in order of definition, so every app global initialized below already
// sees the imports. (TL globals are initialized per module thread on first use, after the app is bound: one copy per
// module, as on the cube.) The host fills the table again after loading (a plugin of an older host keeps working).
octAppImports_t OCT_APP_IMPORTS = {0};

static bool OCT_SIM_pull_imports()
    {
        typedef const octAppImports_t* (*hostFn)(void);
#if defined(_WIN32)
        hostFn fn = (hostFn)GetProcAddress(GetModuleHandleW(0), OCT_SIM_HOST_SYMBOL);
#else
        hostFn fn = (hostFn)dlsym(RTLD_DEFAULT, OCT_SIM_HOST_SYMBOL);
#endif
        const octAppImports_t* t = fn ? fn() : 0;
        if (t) memcpy(&OCT_APP_IMPORTS, t, sizeof(OCT_APP_IMPORTS));
        return t != 0;
    }
static const bool OCT_SIM_IMPORTS_AT_LOAD = OCT_SIM_pull_imports();

#include "app.h"

#ifndef OCT_SIM_APP_NAME
#error "build with -DOCT_SIM_APP_NAME=\"app_<name>\" (the *.target stem); tools/sim/build_game.* does"
#endif

#if defined(_WIN32)
#define OCT_SIM_EXPORT extern "C" __declspec(dllexport)
#else
#define OCT_SIM_EXPORT extern "C" __attribute__((visibility("default")))
#endif

#ifndef APP_VERSION
#define APP_VERSION OCT_APP_SEMVER(0, 0, 0)
#endif
#ifndef APP_GUID1
#define APP_GUID1 0
#endif
#ifndef APP_CATEGORIES
#define APP_CATEGORIES (APP_CATEGORY_GAME)
#endif
#ifndef APP_COLORS
#define APP_COLORS 0xFFFFFFFF
#endif

static const octSimGameEntry_t OCT_SIM_ENTRY =
    {
    OCT_SIM_PLUGIN_MAGIC,
    OCT_SIM_PLUGIN_VERSION,
    OCT_APP_ABI_VERSION,
    (uint32_t)sizeof(octSimGameEntry_t),
    OCT_SIM_LAYOUT_INIT,
    &OCT_APP_IMPORTS,
    on_init,
    on_tick,
    on_pretwisted,
    on_twisted,
    on_tap,
    on_shake,
#ifdef APP_HAS_PROC_DRAW
    on_proc_draw,
#else
    0,
#endif
#ifdef APP_HAS_ON_SAVE
    on_save,
#else
    0,
#endif
#ifdef APP_HAS_ON_SAVE_SYNCED
    on_save_synced,
#else
    0,
#endif
#ifdef APP_HAS_ON_DOCK
    on_dock,
#else
    0,
#endif
    OCT_SIM_APP_NAME,
#ifdef APP_TITLE
    APP_TITLE,
#else
    0,
#endif
    (uint64_t)(APP_GUID1),
    (uint32_t)(APP_VERSION),
    (uint32_t)(APP_CATEGORIES),
    (uint32_t)(APP_COLORS),
#ifdef APP_SAVE_SIZE
    1, (uint32_t)(APP_SAVE_SIZE),
#else
    0, 0,
#endif
    { OCT_SIM_IMPORTS_AT_LOAD ? 1u : 0u }   // reserved[0]: the imports were in place before the app's constructors
    };

OCT_SIM_EXPORT const octSimGameEntry_t* oct_sim_game_entry(void)
    {
        return &OCT_SIM_ENTRY;
    }
