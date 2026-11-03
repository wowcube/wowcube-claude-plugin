// The template app's twist capture -- an EXAMPLE of a game's tests/capture.cpp on the skill's capture.h, net
// mode, written for the plugin's own templates/app_ai_template: the real engine renders all 24 screens from the
// packed art on every frame, and every twist is marked for render_demo.py, which turns the half of the cube in 3D
// between the frames around it.
//
//   CAPTURE_NET=1 capture_demo.sh [path-to-SDK]   -> docs/demo/frames.jsonl + docs/demo/net/*.png
//
// Pack the app first (index.bin + art/packed + sound/assets): repack_app.py --app-dir <app> --skip-device.
// What is the app's own here: startApp / showDemo (the template's demos 1 and 12), the twists, the captions.
// What every net capture has: shotInit + shotLoadPack, tick() = on_tick -> capFrame,
// twist() = on_pretwisted -> OCT_twist_sprites -> on_twisted -> capTwist.

#include "oct_test_shim.h"

#define MINIMP3_IMPLEMENTATION
#include "oct.h"

#include "capture.h"                    // before app.h (its label hook is not used in net mode)

#define ATTR_RODATA_IN_TCM
#include "app.h"

#include "shot.h"                       // after app.h: the engine's render of every screen

#define DEMO_SETTLE_TICKS   20          // ticks after on_init that are not filmed: gravity settling
#define DEMO_TWIST_GAP      16          // frames between two twists: the turn reads
#define DEMO_HOLD           40          // frames a finished scene is held

void TestBegin()
{
    Debug = new simDebug();
    Debug->Init("log_capture.txt");
    SET.TimeZero = SIM_now_ms() - 100000u;
    OCT_SHIM_init();
}

static void setGravity(float x, float y, float z) { Gf[0] = x; Gf[1] = y; Gf[2] = -z; }   // cube space -> engine

static void ticks(int n)
{
    for (int i = 0; i < n; i++) {
        on_tick();
        capFrame();
    }
}

// A twist as the engine delivers it, marked for the renderer's turn. on_pretwisted gets the PLANE being
// turned (0..5, the engine's OCT_TWIST_PRE + plane), not the twist id: ids run TOP_CCW, TOP_CW, FRONT_CCW..
// two per plane, half twists repeating them from OCT_TWIST_HALF.
static void twist(int t)
{
    on_pretwisted((t % OCT_TWIST_HALF) / 2);
    OCT_twist_sprites((octTwistId_t)t);
    on_twisted(t, 0);
    capTwist(t);
}

// The template started, the cube standing on its bottom face.
static void startApp(void)
{
    shotQuietEngine();
    setGravity(0.0f, -1.0f, 0.0f);
    on_init();
    for (int i = 0; i < DEMO_SETTLE_TICKS; i++) on_tick();
}

static void showDemo(demoId_t demo)
{
    switchDemo(demo);
    ticks(DEMO_HOLD);
}

static void twists(const int* list, int count)
{
    for (int i = 0; i < count; i++) {
        twist(list[i]);
        ticks(DEMO_TWIST_GAP);
    }
}

int main(int argc, char** argv)
{
    const std::string app = (argc > 1) ? argv[1] : "..";
    TestBegin();
    shotInit();
    if (!shotLoadPack(app) || !capOpen()) return 1;

    capShot("AI TEMPLATE", "Twists, rendered screen by screen by the engine", CAPTURE_LEGEND_NONE, 30.0f, 24.0f, 0.15f);
    startApp();
    ticks(DEMO_HOLD);

    capShot("Twistable sprites", "Demo 1: the arrows ride with their screens, the tiles stay put", 0, 30.0f, 24.0f);
    showDemo(DEMO_1);
    const int ride[] = {FRONT_CW, TOP_CCW, RIGHT_CW};
    twists(ride, 3);
    ticks(DEMO_HOLD);

    capShot("Undone twist by twist", "The same twists the other way, the last one first", 0, 36.0f, 26.0f);
    const int back[] = {RIGHT_CCW, TOP_CW, FRONT_CCW};
    twists(back, 3);
    ticks(DEMO_HOLD);

    capShot("Carried by hand", "Demo 12: the star is not twistable; the app moves it with OCT_TM_twist", 1,
            24.0f, 30.0f, 0.2f);
    showDemo(DEMO_12);
    const int carry[] = {TOP_CW, FRONT_CCW, LEFT_CW};
    twists(carry, 3);
    ticks(DEMO_HOLD);

    capClose();
    return 0;
}
