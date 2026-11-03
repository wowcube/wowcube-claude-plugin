
/* Link module to fixed address in VRAM with exports table at offset 0. Module MUST fit within 256KB. */

OUTPUT_FORMAT("elf32-littlearm", "elf32-littlearm", "elf32-littlearm")
OUTPUT_ARCH(arm)

/* Module memory region - top 256KB of VRAM */
MEMORY                      
{
    APP (rwx) : ORIGIN = 0x103C0000, LENGTH = 256K
}

/* Entry point (not really used, but required) */
ENTRY(OCT_APP_EXPORTS)

SECTIONS
{
    /* Exports table MUST be at offset 0 */
    .app_exports ORIGIN(APP) :
    {
        KEEP(*(.app_exports))
    } > APP
    
    /* Imports table follows exports (at offset 0x64) */
    . = ORIGIN(APP) + 0x64;
    .app_imports :
    {
        KEEP(*(.app_imports))
    } > APP
    
    /* Code section */
    . = ALIGN(4);
    .text :
    {
        *(.text)
        *(.text*)
        *(.glue_7)
        *(.glue_7t)
        
        /* ARM exception handling - usually not needed */
        *(.eh_frame)
        
    } > APP
    
    /* Read-only data */
    . = ALIGN(4);
    .rodata :
    {
        *(.rodata)
        *(.rodata*)
    } > APP
    
    /* ARM unwinding tables */
    .ARM.extab :
    {
        *(.ARM.extab*)
    } > APP
    
    .ARM.exidx :
    {
        __exidx_start = .;
        *(.ARM.exidx*)
        __exidx_end = .;
    } > APP
    
    /* C++ global constructors (.init_array / .ctors) collected so the host binder can iterate and call them before on_init.
       Bounds are exported via init_array_start / init_array_end in octAppExports_t. */
    . = ALIGN(4);
    .init_array :
    {
        __init_array_start = .;
        KEEP(*(.init_array*))
        KEEP(*(.ctors*))
        __init_array_end = .;
    } > APP

    /* Initialized data */
    . = ALIGN(4);
    .data :
    {
        __data_start__ = .;
        *(.data)
        *(.data*)
        . = ALIGN(4);
        __data_end__ = .;
    } > APP
    
    /* Zero-initialized data */
    . = ALIGN(4);
    .bss (NOLOAD) :
    {
        __bss_start__ = .;
        *(.bss)
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        __bss_end__ = .;
    } > APP
    
    /* End of module */
    _end = .;
    
    /* Verify module fits in allocated space */
    ASSERT(. <= (ORIGIN(APP) + LENGTH(APP)), "ERROR: Module exceeds 256KB limit!")

    /* GNU build-id note (from -Wl,--build-id). Claimed here so the /DISCARD/
       *(.note*) rule below does not drop it, and KEEP'd so --gc-sections cannot.
       It stays a real SHT_NOTE section (readelf -n and the .oct packer's
       SIM_extract_gnu_build_id both scan SHT_NOTE); the (INFO)/(NOLOAD) type
       overrides that would drop SHF_ALLOC turn it into PROGBITS, which those
       readers no longer recognise. It is therefore allocatable and appears in
       the ELF's PT_LOAD, but the CMake post-build strips it from the loadable
       .bin with objcopy -R .note.gnu.build-id, so it never reaches the device
       image. Telemetry reads the build-id from the .elf; the packer copies it
       into octPackHeader_t.BuildId. */
    .note.gnu.build-id :
    {
        KEEP(*(.note.gnu.build-id))
    }

    /* Last point at which the location counter still describes the module: every
       section below is non-loadable and parks '.' at its own fixed VMA (0 for the
       tag sidecar), so the trailing __module_end / __module_size must be computed
       from THIS, not from a bare '.' after the SECTIONS block. */
    __module_alloc_end = .;

    /* CDEFMT log metadata — non-loadable (INFO), so it lives in app.elf for the
       host decoder but never reaches app.bin or the device.

       VMA 0x80000000 is not arbitrary: the decoder splits a record's log_id by
       that value (wow_telemetry VMA_APP_BASE) to decide whether the format
       string comes from the firmware ELF or from an app module ELF. Firmware
       metadata is based at 0x20000000 (telemetry/cdefmt_sections.ld), so the
       two ranges never collide and one telemetry stream can carry both.

       The input order below is load-bearing: the CDEFMT parser requires the
       init record to sit at offset 0 of the section, so .cdefmt.init must be
       placed before .cdefmt.metadata. Mirrors telemetry/cdefmt_sections.ld;
       keep the two in step. */
    .cdefmt 0x80000000 (INFO) :
    {
        KEEP(*(.cdefmt.init))
        KEEP(*(.cdefmt.init.*))
        KEEP(*(.cdefmt.metadata))
        KEEP(*(.cdefmt.metadata.*))
        KEEP(*(.cdefmt))
        KEEP(*(.cdefmt.*))
    }

    /* Telemetry tag sidecar — maps CDEFMT counters to semantic tags/levels for
       the decoder. Non-loadable for the same reason as .cdefmt above. */
    .wow_telemetry.tags 0 (INFO) :
    {
        KEEP(*(.wow_telemetry.tags))
        KEEP(*(.wow_telemetry.tags.*))
    }

    /* Discard sections we don't need. .debug* is KEPT: the telemetry decoder
       resolves log argument types from DWARF. It is non-ALLOC, so it stays in
       the .elf and never reaches the .bin. */
    /DISCARD/ :
    {
        *(.comment)
        *(.note*)
    }
}

/* Symbols for runtime (if needed).
   Based on __module_alloc_end, captured inside SECTIONS while the location
   counter still tracked the module: a bare '.' here would read whatever the
   last non-loadable metadata section left behind, not the module's real end. */
__module_start = ORIGIN(APP);
__module_end = __module_alloc_end;
__module_size = __module_alloc_end - ORIGIN(APP);
