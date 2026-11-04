//OCT App Module Entry Point
//
//This file defines the import/export tables for the dynamically loaded module.
//It is compiled with OCT_APP_MODULE define, causing the app to use ABI wrappers.

#ifdef APP_TELEMETRY
#include "telemetry.h"
#endif

#include "oct_app_module.h"

#include "app.h"

//Imports table populated by host binder before on_init is called
__attribute__((section(".app_imports"), used)) octAppImports_t OCT_APP_IMPORTS = {0};


#ifdef APP_TELEMETRY
#include "telemetry_octavios_module.cpp"
#endif


//Linker-provided bounds of the .init_array section (C++ global constructors).
//The host binder iterates these and calls each entry before on_init.
extern "C" 
{
    extern void (*__init_array_start[])(void);
    extern void (*__init_array_end[])(void);
}


//Exports table - set at compile time with module's callback addresses. The simulators bind the same exports
//from the simulator's app binder; a new optional export goes into both lists.
extern "C" 
{

__attribute__((section(".app_exports"), used)) octAppExports_t OCT_APP_EXPORTS = 
    {
    .magic          = OCT_APP_ABI_MAGIC,
    .version        = OCT_APP_ABI_VERSION,
    .init_array_start = (uint32_t)__init_array_start,
    .init_array_end   = (uint32_t)__init_array_end,
    .on_init        = on_init,
    .on_tick        = on_tick,
    .on_pretwisted  = on_pretwisted,
    .on_twisted     = on_twisted,
    .on_tap         = on_tap,
    .on_shake       = on_shake,
    #ifdef APP_HAS_PROC_DRAW
    .on_proc_draw   = on_proc_draw,
    #else
    .on_proc_draw   = 0,
    #endif
    #ifdef APP_HAS_ON_SAVE
    .on_save        = on_save,
    #else
    .on_save        = 0,
    #endif
    #ifdef APP_HAS_ON_SAVE_SYNCED
    .on_save_synced = on_save_synced,
    #else
    .on_save_synced = 0,
    #endif
    #ifdef APP_HAS_ON_DOCK
    .on_dock        = on_dock,
    #else
    .on_dock        = 0,
    #endif
    .reserved       = {0}
    };

}
