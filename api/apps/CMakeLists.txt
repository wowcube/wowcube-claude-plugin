# Universal OCT App Module Build 
#
# Invoked from each app folder via:
#   cmake -G Ninja -S ../octavios/apps -B out
#   cmake --build out
#
# - APP_DIR is the parent of the build directory (= the app folder)
# - APP_NAME is the basename of the single <APP_DIR>/*.target marker file
#   (e.g. app_example/app_example.target -> APP_NAME=app_example)
#
# Output: <APP_DIR>/out/<app_name>.bin

cmake_minimum_required(VERSION 3.13 FATAL_ERROR)

# Toolchain configuration
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_VERSION 1)
set(CMAKE_SYSTEM_PROCESSOR arm)

set(CMAKE_C_COMPILER arm-none-eabi-gcc)
set(CMAKE_CXX_COMPILER arm-none-eabi-g++)
set(CMAKE_ASM_COMPILER arm-none-eabi-gcc)
set(CMAKE_AR arm-none-eabi-ar)
set(CMAKE_OBJCOPY arm-none-eabi-objcopy)
set(CMAKE_OBJDUMP arm-none-eabi-objdump)
set(CMAKE_SIZE arm-none-eabi-size)

set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)


# Project (derive APP_DIR from build dir parent, APP_NAME from <APP_DIR>/*.target)
get_filename_component(APP_DIR "${CMAKE_BINARY_DIR}" DIRECTORY)
file(GLOB _TARGET_FILES RELATIVE "${APP_DIR}" "${APP_DIR}/*.target")
list(LENGTH _TARGET_FILES _TARGET_COUNT)
if(_TARGET_COUNT EQUAL 0)
    message(FATAL_ERROR "No *.target marker file found in ${APP_DIR} - expected one file like app_<name>.target or scr_<name>.target (invoke cmake with -B <app_folder>/out)")
elseif(NOT _TARGET_COUNT EQUAL 1)
    message(FATAL_ERROR "Multiple *.target marker files found in ${APP_DIR}: ${_TARGET_FILES} - expected exactly one")
endif()
get_filename_component(APP_NAME "${_TARGET_FILES}" NAME_WE)
if(NOT APP_NAME MATCHES "^[a-z][a-z][a-z]_[A-Za-z0-9_]+$")
    message(FATAL_ERROR "Invalid APP_NAME '${APP_NAME}' from marker ${_TARGET_FILES} - expected <3 lowercase letters>_<alphanumeric_or_underscore>, e.g. app_my_game or scr_my_saver")
endif()
project("${APP_NAME}" LANGUAGES CXX)
set(ELF_TARGET "${APP_NAME}.elf")

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Output directory (inside the app folder, not the shared infra)
set(OUT_DIR "${APP_DIR}/out")
file(MAKE_DIRECTORY "${OUT_DIR}")
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${OUT_DIR}")
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${OUT_DIR}")
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${OUT_DIR}")

# Includes
include_directories(
    ${APP_DIR}/src                             # App source
    ${CMAKE_CURRENT_SOURCE_DIR}/../include     # Public game API (api/include)
)

# Sources (shared module entry point)
set(SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/src/app_module.cpp
)



# Compiler flags:  Cortex-M4 with hardware FPU
#
# -ffreestanding  
# tells GCC this is NOT a hosted environment - prevents it from assuming standard library semantics 
# or silently emitting calls to libc helpers (__aeabi_memcpy4, snprintf, etc.)
#
# -fno-builtin    
# extra guard - prevents GCC from recognising ANY standard function by name, so the compiler won't substitute built-in implementations

set(CPU_FLAGS "-mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16")

# Optimization: -Os (size). The hot render loop lives in firmware, not in the
# app module, so aggressive speed tuning here brings no visible gain.

set(CMAKE_CXX_FLAGS "${CPU_FLAGS} -std=c++20 -Os -Wall -Werror=float-conversion -Werror=double-promotion -Werror -ffreestanding -fno-builtin")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fsingle-precision-constant")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fmerge-all-constants -ffunction-sections -fdata-sections -flto")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fno-exceptions -fno-rtti -fno-threadsafe-statics")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fno-use-cxa-atexit")
# The telemetry decoder reads argument types from DWARF: without -g a
# WLOG_*("...{}", x) resolves its format string but cannot fill the {}.
# Debug info is non-ALLOC, so it stays in the .elf and never reaches the device.
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -g")

# Enable module build mode for engine's sources
add_definitions(-DOCT_APP_MODULE)

# Linker flags
set(LINKER_SCRIPT "${CMAKE_CURRENT_SOURCE_DIR}/src/app_module.ld")

set(CMAKE_EXE_LINKER_FLAGS "${CPU_FLAGS}")
set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -T \"${LINKER_SCRIPT}\"")
set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -nostdlib -nostartfiles")
# Only where the linker knows it (binutils >= 2.39): the flag just silences the RWX-segment
# warning, and older toolchains (e.g. gcc-arm-none-eabi 10.3) hard-fail on the unknown option.
# Ask the LINKER, not the driver: `gcc -Wl,--help` prints collect2's own usage, so it never mentions the option and
# the test would be permanently false -- silently dropping the flag even on a new-enough binutils.
execute_process(COMMAND ${CMAKE_C_COMPILER} -print-prog-name=ld
                OUTPUT_VARIABLE OCT_LD_PATH OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
execute_process(COMMAND ${OCT_LD_PATH} --help OUTPUT_VARIABLE OCT_LD_HELP ERROR_QUIET)
if (OCT_LD_HELP MATCHES "no-warn-rwx-segments")
    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -Wl,--no-warn-rwx-segments")
endif()
# Emit a 20-byte sha1 GNU build-id note (matches CDEFMT_GNU_BUILD_ID_SIZE) so the
# .oct packer can stamp it into octPackHeader_t.BuildId for telemetry ELF matching.
# app_module.ld KEEPs the note in the .elf; the post-build objcopy -R strips it
# from the loadable .bin (see below).
set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -Wl,--build-id")
set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -Wl,--gc-sections")
set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -Wl,--print-memory-usage")
set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -Wl,-Map=\"${OUT_DIR}/${APP_NAME}.map\"")
set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -Os -flto")

# Build target
add_executable(${ELF_TARGET} ${SOURCES})

# ---- Telemetry (opt-in) --------------------------------------------------
#
# Adds the module-side telemetry bridge, so this app's WLOG_*/WCOUNT records
# reach the host through the telemetry_enqueue / telemetry_level import slots
# and ride the cube's normal RAM -> SD -> dock path.  APP_TELEMETRY also
# reaches the app's own sources, which gate their instrumentation on it.
#
# An app asks for it by declaring APP_HAS_TELEMETRY in src/app_metadata.h, and
# octpack-build, which reads that header, passes APP_TELEMETRY=ON or OFF here.
# By hand:
#
#   cmake -G Ninja -S ../octavios/apps -B out -DAPP_TELEMETRY=ON
#
# A telemetry build that cannot find the library fails instead of quietly
# building without it: on the cube the two look the same until no records
# arrive.  The telemetry repo is expected next to octavios (../../telemetry),
# which holds both for a standalone checkout and for the mtk_bsp submodule
# layout; -DTELEMETRY_DIR=<path> points anywhere else.
option(APP_TELEMETRY "Build this app module with telemetry support" OFF)
if(APP_TELEMETRY)
    if(NOT TELEMETRY_DIR)
        set(TELEMETRY_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../telemetry")
    endif()
    if(NOT EXISTS "${TELEMETRY_DIR}/cmake/TelemetryOctaviosModule.cmake")
        message(FATAL_ERROR
            "APP_TELEMETRY=ON but the telemetry repo was not found at ${TELEMETRY_DIR}. "
            "Check it out next to octavios or pass -DTELEMETRY_DIR=<path>. To build without "
            "telemetry, drop APP_HAS_TELEMETRY from src/app_metadata.h (octpack-build) or "
            "pass -DAPP_TELEMETRY=OFF.")
    endif()
    include("${TELEMETRY_DIR}/cmake/TelemetryOctaviosModule.cmake")
    Telemetry_AddOctaviosModuleSupport(${ELF_TARGET} "${TELEMETRY_DIR}")
    target_compile_definitions(${ELF_TARGET} PRIVATE APP_TELEMETRY)
    message(STATUS "${APP_NAME}: telemetry ENABLED")
else()
    message(STATUS "${APP_NAME}: telemetry disabled")
endif()

# Post-build: Generate binary file.
# -R .note.gnu.build-id keeps the (allocatable) build-id note out of the loadable
# .bin the device runs, while it stays in the .elf for telemetry ELF matching.
add_custom_target(${APP_NAME}.bin ALL
    COMMAND ${CMAKE_OBJCOPY} -O binary -R .note.gnu.build-id $<TARGET_FILE:${ELF_TARGET}> "${OUT_DIR}/${APP_NAME}.bin"
    DEPENDS ${ELF_TARGET}
    COMMENT "Generating ${APP_NAME}.bin"
)

# Post-build: Show size
add_custom_target(size ALL
    COMMAND ${CMAKE_SIZE} $<TARGET_FILE:${ELF_TARGET}>
    DEPENDS ${ELF_TARGET}
    COMMENT "Module size:"
)

# Post-build: Generate disassembly (optional, for debugging)
add_custom_target(${APP_NAME}.lst ALL
    COMMAND ${CMAKE_OBJDUMP} -d -S $<TARGET_FILE:${ELF_TARGET}> > "${OUT_DIR}/${APP_NAME}.lst"
    DEPENDS ${ELF_TARGET}
    COMMENT "Generating ${APP_NAME}.lst"
)

# Post-build: Check for undefined / external symbols
# arm-none-eabi-nm -u lists symbols the ELF references but does not define.
# With -nostdlib these would be unresolved at link time, but GCC builtins can slip through. Dump them so the developer sees them in the build log.
add_custom_command(TARGET ${ELF_TARGET} POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E echo "--- undefined symbols, should be empty: ---"
    COMMAND arm-none-eabi-nm -u $<TARGET_FILE:${ELF_TARGET}> || ${CMAKE_COMMAND} -E true
    COMMENT "Checking for undefined symbols"
)
