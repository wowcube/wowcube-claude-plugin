// Public WowCube game API: generated from the engine sources (api/SOURCE).
// Only what a game compiled as a cube module (OCT_APP_MODULE) uses. Do not edit: regenerate.
#pragma once
#include <stdint.h>
#include "oct_pack_format.h"    //OCT_ASSET_NAME_MAXLEN, OCT_PACK_FORMAT_SUPPORTED, OCT_ENGINE_VERSION_*: the .oct wire format
#include "oct_shared.h"         //OCT_STATIC_ASSERT, OCT_CUBE_COUNT


#define OCT_SPRITES_CAP         5120                                                //Maximum allowed objects array capacity (the pool itself is the app's; this only caps what OCT_restart accepts)
#define OCT_SPRITES_QUAD_CAP    512                                                 //Per-quad cap of sprites that survive the gather cull (on-screen at once) -- already far above any real scene
#define OCT_LABELS_CAP          64                                                  //Maximum number of labels
#define OCT_LABEL_LEN           128                                                 //Maximum label text length

//ACTIVATION is the second BUILT-IN foreground, alongside SHELL: it names no pack and carries no GUID, and the
//apply binds the engine's own callbacks for it (OCT_launch_activation, oct.h). Appended, never inserted -- these
//values are on the wire, so a mixed-firmware mesh would read every one of them one place across.
typedef enum
{
    CMD_APP_ACTION_DEFAULT = 0, CMD_APP_ACTION_TEST = 1, CMD_APP_ACTION_SHELL = 2, CMD_APP_ACTION_DELETE = 3,
    CMD_APP_ACTION_ACTIVATION = 4
} octCmdAppAction_t;

//App-facing brightness mode for OCT_set_brightness(level, mode). TRANSIENT drives the LED rail only and is reverted to
//the system level when the app exits; PERSIST also updates the cached user level and writes NVDM. Apps must always pass
//TRANSIENT; only the settings app persists a user choice — so an app can never write a per-module dim that survives exit.
typedef enum { OCT_BRIGHTNESS_TRANSIENT = 0, OCT_BRIGHTNESS_PERSIST = 1 } octBrightnessMode_t;


//Pack/entry capability categories (OCT_CAT_* / APP_CATEGORY_*), in their own leaf header because an app's src/app_metadata.h names them and is compiled without the rest of this one
#include "oct_app_categories.h"


//Results of the save store (the engine's save store): what reading, writing and carrying an app's save across an update
//return. They live here rather than in that header because they reach the app verbatim once the store's read/write
//pair is in the app ABI, and this header is the one reachable by both the engine host and a loadable module.
//A read is the one exception to "0 means success": it returns the byte count it filled, and 0 means "no save
//stored", which is a normal answer and not a failure.
#define OCT_SAVE_OK              (0)    //Written
#define OCT_SAVE_NO_AREA        (-1)    //This app has no save area the engine may use: it declares no save size, its catalog record predates the declaration, its span has no room for a slot, or the area's header does not validate -- never initialised, or corrupt, and only initialising it again (at install) clears that
#define OCT_SAVE_BAD_SIZE       (-2)    //The range asked for is empty, or offset + size runs past the area the installed app declares
#define OCT_SAVE_BAD_BUFFER     (-3)    //A null buffer. The engine reads the caller's bytes inside the call, so any pointer it can read is legal -- a local included
#define OCT_SAVE_IO             (-4)    //The card refused a read or a write
#define OCT_SAVE_NOT_SYNCED     (-6)    //A cube-wide sync (OCT_save_sync) did not put the leader's bytes on every module: the transfer failed, was refused, or the leader never delivered a verdict. Mostly the ARGUMENT of on_save_synced; as a RETURN value it means the call was made outside the tick (a draw callback) and started nothing -- the same on all eight, since each refuses its own. What each module's area holds afterwards is what the transfer got as far as, which is why a game reads its range back rather than assuming
#define OCT_SAVE_RESET_PENDING  (-5)    //The dock has begun resetting the cube and the hold is already OCT_SAVE_RESET_CUTOFF_MS old, so no card write may start: what was stored before the hold stays, what this call carried is lost
#define OCT_SAVE_UNSUPPORTED    (-7)    //This cube's firmware predates the save calls: its import slot is NULL and nothing was read or written. The ENGINE never returns it -- it is answered by the app-side macros in oct_app_module.h, which is also the header that makes the constant visible to the app that can receive it. Its own code rather than an existing one because a game can do nothing about it, while every other refusal here describes something on THIS cube that a player or a developer could act on

#define COLORS_COUNT 20


//#define OCT_PACK_CAP (1024*1024 + 512*1024 + 128*1024)    //1.6 MB for now

const uint16_t COLOR_RED = 0xd882, COLOR_ORANGE = 0xfb42, COLOR_YELLOW = 0xffa2, COLOR_GREEN = 0x0e41, COLOR_CYAN = 0x0ddc, COLOR_BLUE = 0x0a3c, COLOR_VIOLET = 0x505c, COLOR_MAGENTA = 0xd836, COLOR_GRAY = 0x4a49, COLOR_BLACK = 0x0821;
const uint16_t COLOR_LIGHT_RED = 0xfb2d, COLOR_LIGHT_ORANGE = 0xfd4c, COLOR_LIGHT_YELLOW = 0xfff4, COLOR_LIGHT_GREEN = 0x9788, COLOR_LIGHT_CYAN = 0x87be, COLOR_LIGHT_BLUE = 0x8e1e, COLOR_LIGHT_VIOLET = 0x8adf, COLOR_LIGHT_MAGENTA = 0xf318, COLOR_LIGHT_GRAY = 0xa534, COLOR_WHITE = 0xf7de;
const uint16_t COLORS[COLORS_COUNT] = { COLOR_RED,        COLOR_ORANGE,       COLOR_YELLOW,       COLOR_GREEN,        COLOR_CYAN,         COLOR_BLUE,         COLOR_VIOLET,       COLOR_MAGENTA,          COLOR_GRAY,         COLOR_BLACK,
                                        COLOR_LIGHT_RED,  COLOR_LIGHT_ORANGE, COLOR_LIGHT_YELLOW, COLOR_LIGHT_GREEN,  COLOR_LIGHT_CYAN,   COLOR_LIGHT_BLUE,   COLOR_LIGHT_VIOLET, COLOR_LIGHT_MAGENTA,    COLOR_LIGHT_GRAY,   COLOR_WHITE };

//The I2S output frame is STEREO and stays that way even though a module has one speaker -- mono was
//tried on hardware and came out noisy twice. The reasoning and both attempts are recorded at the
//channel_number line in OCT_PCM_init (the engine's mixer) and in AUDIO_NOTES.md.

//───── Sound mixer ────────────────────────────────────────────────────────────
//How many sounds may sound AT ONCE on one module. Every voice carries its own MP3 decoder, so this
//is the constant that costs memory, and cached .bss is nearly full -- a firmware link reports
//"VRAM overflow into app module region" the moment this is raised without freeing something first.
//Per voice: sizeof(mp3dec_t) ~6.5 KB + holdover ~3.4 KB + window 4 KB = 14 264 bytes exactly
//(measured by diffing firmware builds). Headroom checked on hardware builds:
//   4 voices -> 58 096 B of cached .bss free      6 voices -> 29 568 B free
//   8 voices ->  1 040 B free (links, but nothing may be added after it)   9 -> does not link
//CPU is the other ceiling and it is NOT measured: every voice needs 38.3 mp3 frames a second,
//decoded sequentially by one task.
#define OCT_SND_VOICES_MAX      6
#define OCT_GESTURE_STATE_SETTLE_MS 1000    //A fused gesture reaches the app only once the engine state has held this long, so none lands mid-transition
//Max fixed-step ticks one frame executes. A longer backlog is not skipped while an app runs: the rest carries to the
//next frames, so a blocked module replays every tick its siblings ran (OCT_tick_budget). ~1s at OCT_FRAME_MS=50.
#define OCT_MAX_CATCHUP_TICKS 20


//Used as table of constants
typedef struct
{
    int      QuadsDisk[4];
    int      QuadsRing1[4];
    int      QuadsRing2[4];
    uint32_t RingsMask;         //Affected quads in both rings; marked as 1 in [0]..[23] bits
    int      VirtAxisId;        //Mapping to 3 virtual axes
    int      VirtAxisDir;       //...and their direction
    int      Invariant;         //Twist index of a topological invariant
    int      Impulse[6];        //Impulse direction in plane space for each plane; unaffected plane marked with 360; rotating plane contains just -270 (CCW) or -90 (CW)
} octTwist_t;

//4-quad loops for screens remapping on any twist possible; CW and CCW are defined looking from outside of the cube (following the right-hand rule; just like one usually see the cube in real world)
const octTwist_t OCT_TWISTS[12] = { {{0, 1, 2, 3},      {5, 9, 13, 17},     {4, 8, 12, 16},     0x00033330,  1, +1, 10, {-270,    0,    0,    0,    0,  360}},      //Top   side CCW, CW
                                    {{3, 2, 1, 0},      {16, 12, 8, 4},     {17, 13, 9, 5},     0x00033330,  1, +1, 11, { -90,  180,  180,  180,  180,  360}},
                                    {{4, 5, 6, 7},      {16, 21, 10, 3},    {19, 20, 9, 2},     0x0039060C,  2, -1, 6,  { 180, -270,   90,  360,  270,    0}},      //Front side CCW, CW
                                    {{7, 6, 5, 4},      {2, 9, 20, 19},     {3, 10, 21, 16},    0x0039060C,  2, -1, 7,  {   0,  -90,  270,  360,   90,  180}},
                                    {{8, 9, 10, 11},    {0, 4, 20, 14},     {3, 7, 23, 13},     0x00906099,  0, +1, 8,  { 270,  270, -270,   90,  360,  270}},      //Right side CCW, CW
                                    {{11, 10, 9, 8},    {13, 23, 7, 3},     {14, 20, 4, 0},     0x00906099,  0, +1, 9,  {  90,   90,  -90,  270,  360,   90}},
                                    {{12, 13, 14, 15},  {1, 8, 23, 18},     {0, 11, 22, 17},    0x00C60903,  2, +1, 2,  {   0,  360,  270, -270,   90,  180}},      //Back  side CCW, CW
                                    {{15, 14, 13, 12},  {17, 22, 11, 0},    {18, 23, 8, 1},     0x00C60903,  2, +1, 3,  { 180,  360,   90,  -90,  270,    0}},
                                    {{16, 17, 18, 19},  {12, 22, 6, 2},     {15, 21, 5, 1},     0x00609066,  0, -1, 4,  {  90,   90,  360,  270, -270,   90}},      //Left  side CCW, CW
                                    {{19, 18, 17, 16},  {1, 5, 21, 15},     {2, 6, 22, 12},     0x00609066,  0, -1, 5,  { 270,  270,  360,   90,  -90,  270}},
                                    {{20, 21, 22, 23},  {19, 15, 11, 7},    {18, 14, 10, 6},    0x000CCCC0,  1, -1, 0,  { 360,  180,  180,  180,  180, -270}},      //Bottom side CCW, CW
                                    {{23, 22, 21, 20},  {6, 10, 14, 18},    {7, 11, 15, 19},    0x000CCCC0,  1, -1, 1,  { 360,    0,    0,    0,    0,  -90}}
                                };
