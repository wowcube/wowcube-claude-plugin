// The template app's demo capture -- an EXAMPLE of a game's tests/capture.cpp on the skill's capture.h, sprite
// mode, written for the plugin's own templates/app_ai_template (copy the template to app_<name>, then this file to
// its tests/). The template's real callbacks run headless, the robot (bot.h) holds the cube; a script walks
// through a few of its demos: sprites, a tap to the next demo, the ring walk, engine tweens, the label that keeps
// upright while the cube is turned over, and a twist.
//
//   capture_demo.sh [path-to-SDK]    -> docs/demo/frames.jsonl
//
// What is the app's own here: the robot, the session (switchDemo and the demo ids), the captions.
// What every capture has: the includes, TestBegin, tick() = input -> on_tick -> capFrame, and a twist as the
// engine delivers it (on_pretwisted -> OCT_twist_sprites -> on_twisted -> capTwist).
// Sprite mode draws from a sprite dump (docs/demo/sprites/<name>.png, named as in src/app_ai_template_ids.h),
// exported from the template's art/assets.psd. The template has no RENDER_LABEL_HOOK, so its text labels come out
// empty; a game adds the hook next to its label calls (SKILL.md, method B).

#include "oct_test_shim.h"

#define MINIMP3_IMPLEMENTATION
#include "oct.h"

#include "oct_test.h"

#include "capture.h"                    // before app.h: its RENDER_LABEL_HOOK reaches the game's label calls

#define ATTR_RODATA_IN_TCM
#include "app.h"

#include "bot.h"

void TestBegin()
{
    Debug = new simDebug();
    Debug->Init("log_capture.txt");
    SET.TimeZero = SIM_now_ms();
    OCT_SHIM_init();
}

static Bot_t gBot;

// A tick of the app as the engine runs it, the robot holding the cube.
static void tick(void)
{
    botTick(&gBot);
    on_tick();                                                          // the engine's tick: the app, the render
    capFrame();
}

static void ticks(int n)
{
    for (int i = 0; i < n; i++) tick();
}

// A tap on `plane` as the engine delivers it: a double tap arrives as count 1, then as count 2.
static void tap(int plane, bool twice = false)
{
    on_tap(plane, 1);
    if (twice) on_tap(plane, 2);
}

// A full twist as the engine delivers it, marked for the renderer's turn. on_pretwisted gets the PLANE being
// turned, not the twist id (ids run TOP_CCW, TOP_CW, FRONT_CCW.., two per plane).
static void twist(int t)
{
    on_pretwisted((t % OCT_TWIST_HALF) / 2);
    OCT_twist_sprites((octTwistId_t)t);
    on_twisted(t, 0);
    capTwist(t);
}

static void capture(void)
{
    EXPECT(capOpen(), "cannot write the capture");
    if (!gCap.out) return;

    botInit(&gBot, OCT_PLANE_TOP);
    on_init();                                                          // the template's start: demo 0

    capShot("AI TEMPLATE", "The plugin's reference app: one part of the API per demo", CAPTURE_LEGEND_NONE,
            30.0f, 24.0f, 0.15f);
    ticks(50);

    capShot("Sprites on the cube", "Demo 0: arrows on the top face and one on the front", CAPTURE_LEGEND_NONE,
            37.5f, 24.0f);
    ticks(50);

    capShot("Tap any face: the next demo", "Demo 1 twists its arrows in code, no hands on the cube", 1, 37.5f, 24.0f);
    tap(OCT_PLANE_FRONT);
    ticks(60);

    capShot("The ring walk", "Demo 6: a sprite walks the cube's rings, a screen per second", CAPTURE_LEGEND_NONE,
            30.0f, 24.0f, 0.6f);
    switchDemo(DEMO_6);
    ticks(140);

    capShot("Engine tweens", "Demo 10: the engine moves the sprite; a chaser follows it", CAPTURE_LEGEND_NONE,
            37.5f, 24.0f);
    switchDemo(DEMO_10);
    ticks(120);

    capShot("Turn the cube over", "Demo 11: the label stays upright on the face that points up", 0, 30.0f, 30.0f);
    switchDemo(DEMO_11);
    ticks(30);
    botRoll(&gBot, OCT_PLANE_FRONT);
    ticks(BOT_ROLL_TICKS + 30);
    botRoll(&gBot, OCT_PLANE_RIGHT);
    ticks(BOT_ROLL_TICKS + 30);
    botRoll(&gBot, OCT_PLANE_TOP);
    ticks(BOT_ROLL_TICKS + 20);

    capShot("Twist", "Demo 12: the star is not twistable; the app carries it through the twist", 3, 37.5f, 24.0f);
    switchDemo(DEMO_12);
    ticks(30);
    twist(TOP_CW);
    ticks(40);
    twist(FRONT_CCW);
    ticks(40);

    capShot("Double tap: always moves on", "Even in the demos that use single taps themselves", 2, 30.0f, 24.0f);
    tap(OCT_PLANE_TOP, true);
    ticks(50);

    capClose();
}

TEST_MAIN(
    RUN(capture);
)
