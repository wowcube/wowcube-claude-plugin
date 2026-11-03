#pragma once
// A robot player for the demo capture (tests/capture.cpp) of the plugin's template app
// (templates/app_ai_template): it handles the cube the way a person would -- it holds it still, or turns it
// over slowly until another face points up. The tilt is the engine's gravity (Gf), the input the template reads
// (OCT_TM_gravity_*, OCT_TM_top_side, its playfieldPlane), so the template's own code runs untouched.
// Taps are not the robot's: the script delivers them as the engine does (on_tap), see capture.cpp.

#include <cmath>

#define BOT_ROLL_TICKS      40          // ticks a roll from one face up to the next takes

// Gravity with each face up, in cube space (x right, y up, z towards the viewer).
static const float BOT_UP[OCT_PLANES_MAX][3] = {
    { 0.0f, -1.0f,  0.0f},              // TOP up: the cube stands on its bottom face
    { 0.0f,  0.0f, -1.0f},              // FRONT up
    {-1.0f,  0.0f,  0.0f},              // RIGHT up
    { 0.0f,  0.0f,  1.0f},              // BACK up
    { 1.0f,  0.0f,  0.0f},              // LEFT up
    { 0.0f,  1.0f,  0.0f},              // BOTTOM up
};

typedef struct {
    float    from[3];                   // gravity when the current roll started
    float    to[3];                     // gravity at its end
    uint32_t ticks;                     // ticks into the current roll
    bool     rolling;                   // false: the cube is held still at `to`
} Bot_t;

static void botGravitySet(const float v[3])
{
    Gf[0] = v[0];                       // cube space -> engine, as capture.h records it back
    Gf[1] = v[1];
    Gf[2] = -v[2];
}

static void botInit(Bot_t* b, int up)
{
    memset(b, 0, sizeof(*b));
    for (int i = 0; i < 3; i++) b->from[i] = b->to[i] = BOT_UP[up][i];
    botGravitySet(b->to);
}

// Start turning the cube over until `up` points up (BOT_ROLL_TICKS ticks).
static void botRoll(Bot_t* b, int up)
{
    for (int i = 0; i < 3; i++) {
        b->from[i] = b->to[i];
        b->to[i] = BOT_UP[up][i];
    }
    b->ticks = 0;
    b->rolling = true;
}

// One tick: the gravity of the cube in the robot's hands, eased along the roll and kept a unit vector.
static void botTick(Bot_t* b)
{
    if (!b->rolling) {
        botGravitySet(b->to);
        return;
    }
    b->ticks++;
    const float k = (float)b->ticks / (float)BOT_ROLL_TICKS;
    const float e = k * k * (3.0f - 2.0f * k);                       // smoothstep: a hand speeds up, then slows
    float v[3], n = 0.0f;
    for (int i = 0; i < 3; i++) {
        v[i] = b->from[i] + (b->to[i] - b->from[i]) * e;
        n += v[i] * v[i];
    }
    n = sqrtf(n);
    for (int i = 0; i < 3; i++) v[i] = n > 0.0f ? v[i] / n : b->to[i];
    botGravitySet(v);
    if (b->ticks >= BOT_ROLL_TICKS) b->rolling = false;
}
