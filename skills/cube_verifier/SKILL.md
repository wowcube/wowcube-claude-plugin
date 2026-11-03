---
name: cube_verifier
description: >-
    Use when verifying WowCube game code after a coder agent completes
    implementation. Defines the Requirements Agent (completeness, GDD,
    regressions), the Template Agent (code against app_ai_template.h and API.md),
    the Combined Code Reviewer that replaces both in the lite verification tier,
    the mandatory Screen Review (all 24 screens of the hidden simulator's frame
    dump) and the Playtest Agent (drives the hidden simulator over its MCP
    control socket and scores what it sees). The orchestrator deploys each one
    separately.
---

# WowCube Code Verifier

Four checks gate every prompt. The two code agents read the **code**; the Screen Review
looks at the **picture** of all 24 screens from the hidden simulator's frame dump; the
Playtest Agent **drives** the hidden simulator and scores what it sees. Each returns JSON.

| Check | Reads | Scoring | When |
|---|---|---|---|
| **Requirements Agent** | code, GDD, prompt | completeness 45, gdd_alignment 25, no_regressions 20, verification_criteria 10 | every prompt (`standard`, `full`) |
| **Template Agent** | code against `app_ai_template.h` + `API.md` | api_correctness 40, platform_constraints 30, code_quality 30 | every prompt (`standard`, `full`) |
| **Combined Code Reviewer** | both of the above in one agent | completeness 30, gdd_alignment 15, no_regressions 15, api_correctness 25, platform_constraints 15 | every prompt (`lite`, instead of the two above) |
| **Screen Review** | the 24-screen PNG dump of a hidden run | PASS / FAIL with findings (no critical or major) | every prompt and every fix, **in every run mode, with or without MCP** |
| **Playtest Agent** | the running hidden simulator | visual_correctness 40, interaction 35, stability 25 | the prompts the tier names (`lite`: foundation, core; `standard`: mechanic prompts; `full`: all), when the hidden instance's control socket answers |

The tier (`lite` / `standard` / `full`) comes from the user's profile through the orchestrator
(`cube_orchestrator/references/RUN_MODES.md`, "Verification tiers"); the Screen Review is never
dropped.

Pass: every deployed code reviewer ≥ 90, Screen Review without critical or major findings,
Playtest ≥ 90 when deployed, **no unresolved critical issue in any check** (a critical
issue fails its agent whatever the total), and **no open major from any agent**: a 93 with
a major (music that never stops, art at ±120) is a fix round, not a pass. A major stays open
only with a reason the orchestrator records in the context (`accepted_majors`) and names in
the report (`cube_orchestrator/SKILL.md`, Stage 4 step 5). The Screen Review exists because code-only
checks once passed a prompt that drew a black cross across all 24 screens.

**Core principle:** verifiers never modify code, assets or the simulator. They read,
analyse, score and report. Every finding cites its evidence: a `file:line` for the code
agents, a frame (absolute PNG path) and the action that produced it for the visual checks.

**Safety:** every brief below starts with this block, verbatim (full text:
`skills/cube_orchestrator/references/AGENT_SAFETY.md`):

```
## Safety (hard rules; full text: <skills>/skills/cube_orchestrator/references/AGENT_SAFETY.md)
- Never send keyboard or mouse input to the desktop or to any window (no SendInput,
  keybd_event, SetForegroundWindow, AutoHotkey).
- Never start a simulator or any program that opens a window, and never play audio.
  The orchestrator runs every simulator, hidden and muted. A Playtest Agent drives only
  the hidden instance on the port it was given, through its control socket.
- Stop only processes you started yourself, by PID. Never kill by name or pattern.
- No commits, pushes, PRs or messages; no credentials or API keys; no downloads.
- Write only the files listed in files_to_write (reviewers write nothing), plus throw-away
  files in the scratch folder you were given (compile checks, notes); nothing else.
```

## When to Use

- Deployed by `cube_orchestrator` after a coder or fixer finishes a prompt (Stage 4, Mod mode)
- The user asks to verify or review WowCube game code, or whether a built game looks and
  works right in the simulator (Screen Review / Playtest Agent alone)

## When NOT to Use

- No implementation exists yet: `cube_orchestrator` generates the code first
- The user wants fixes: the orchestrator's fixer agent does that

## Deduction Rules (shared by the scored agents)

| Severity | Deduction | Definition |
|----------|-----------|------------|
| critical | **-10** from its category (min 0) | won't compile or link (ARM or simulator), feature missing entirely, breaks existing features, nothing renders |
| major | **-5** from its category (min 0) | wrong API usage, lockstep hazard, partially implemented, logic error, visibly wrong picture |
| minor | **-2** from its category (min 0) | style issue, cosmetic difference, non-functional concern |

Start each category at its max, deduct per issue, never below 0. Total = sum of categories.

**A critical issue fails the agent regardless of the score.** Its deduction still counts,
but `status` is `fail` while any critical issue stands, even at a total ≥ 90: a build that
does not compile, a feature missing entirely, a broken earlier feature, nothing rendered,
or a promised input that does nothing can never pass.

### Re-check rounds (after a fixer)

When the task carries `recheck` (`previous_report` + `diff`), do not review the whole
file from scratch. Read your previous report and the diff, then: (1) confirm every
earlier finding is fixed, still open, or fixed differently; (2) review every changed
hunk with its callers and the state it touches (the regressions a fix causes live
there); (3) re-run the verification criteria the fix could affect. Score from the
previous report: give back deductions for fixed findings, add new findings. Do a full
review instead when the diff changes more than ~150 lines, rewrites a system (state
machine, layout, data structures) or the previous round had a critical issue in
`no_regressions` / `api_correctness`. Say which mode you used in `summary`.
On a real run (one foundation prompt, one fix round) the full re-review cost two more
6-10 minute, ~300k-token agents per round; a re-check covers the same risk for a
fraction of that. The Playtest Agent and the visual gate always run in full.

---

## Requirements Agent

Checks the implementation against the prompt's instructions, the GDD, prior context and
the prompt's verification criteria.

### How to Verify

1. **Read the game code** and **the GDD**
2. **Read `prior_context`** to understand what existed before this prompt
3. **Compare the implementation to the prompt's `instructions`**: is every instruction implemented?
4. **Compare it to the GDD**: mechanics, visuals, behaviour, the screen map. Genre rules apply only
   where the GDD has the thing they are about: threat wind-ups when the game has threats, hit
   feedback when it has hits, a timing window when it has rhythm. A rule the GDD records as a
   deliberate exception (Design Assumptions) is not a finding
5. **Check for regressions**: features from earlier prompts still intact?
6. **Check the verification criteria**: does the implementation meet the prompt's test requirements?

**Mod mode without a GDD.** A modded game often has no `plans/<game>_gdd.md`. Then the task JSON carries
`mod_request` (the user's own words for this change, recorded by the orchestrator in the context) and
`gdd_alignment` is scored against it, never left at 0 or deducted for the missing GDD: the change does what
the user asked (the mechanic, where it shows, how it reacts), and nothing the user did not ask for changed
the game's existing look or rules (that part overlaps `no_regressions`: deduct once, there). Say in the
summary that the request stood in for the GDD.

### Categories

| Category | Max | What to check |
|----------|-----|---------------|
| **completeness** | 45 | Every instruction in the prompt is implemented; nothing missing, nothing extra |
| **gdd_alignment** | 25 | The implementation matches the game design document (mechanics, visuals, behaviour). Mod mode without a GDD: the recorded mod request (below) |
| **no_regressions** | 20 | Features documented in `prior_context` still work; nothing broken |
| **verification_criteria** | 10 | The prompt's own verification/test requirements are met |

### Prompt Template

```
<the Safety block above, verbatim>

You are a WowCube requirements verifier. Your job is to check whether the
game code implements what was asked - completely, correctly, and without
breaking existing features.

## Task
<insert Verification Task JSON>

## Rules
1. Read the game code, GDD, and prior_context BEFORE scoring
2. Check every instruction in `instructions` - is it implemented?
3. Check the GDD - does the implementation match the design?
4. Check prior_context - are previous features still intact?
5. Check verification_criteria - are test requirements met?
6. Do NOT check API correctness or template compliance - another agent handles that
7. Score ONLY these categories: completeness (max 45),
   gdd_alignment (max 25), no_regressions (max 20),
   verification_criteria (max 10)

## Deduction Rules
- critical (-10): feature entirely missing, breaks existing feature
- major (-5): partially implemented, wrong behavior, GDD mismatch
- minor (-2): cosmetic difference, minor deviation
- any critical issue = status "fail", whatever the total

## Response
Return ONLY this JSON - no markdown, no explanation:
{
  "agent": "requirements",
  "prompt": N,
  "scores": {
    "completeness": <0-45>,
    "gdd_alignment": <0-25>,
    "no_regressions": <0-20>,
    "verification_criteria": <0-10>
  },
  "total": <sum of above, 0-100>,
  "status": "pass if total >= 90 and no critical issue, else fail",
  "issues": [
    {
      "severity": "critical|major|minor",
      "category": "completeness|gdd_alignment|no_regressions|verification_criteria",
      "description": "...",
      "location": "file:line or function name",
      "deduction": N
    }
  ],
  "summary": "one sentence assessment"
}
```

---

## Template Agent

Reads `templates/app_ai_template/src/app_ai_template.h` (the annotated API: every
`Short:` / `Declaration:` / `Comment:` / `Critical Comment:` / `Warn:` line and the
INSTRUCTIONS block) and `templates/app_ai_template/API.md` (the engine facts: layout,
callbacks, lockstep, coordinates, limits, art tiers, pitfalls), then checks the game code
against both. When they disagree with an older habit, they win.

### How to Verify

1. **Read `app_ai_template.h` and `API.md` in full**
2. **Read the game code** (`src/app_<game>.h`, and `src/app.h`, `src/app_metadata.h`,
   `src/app_save.h` when the prompt touched them)
3. **For each API call**: find its `Declaration:` and check parameter count, types and
   order, then every `Comment:` / `Critical Comment:` / `Warn:` attached to it
4. **For coding patterns** check the rules below
5. **Cite** the template annotation or the API.md section for every issue

### Rules to check (the bundled engine; details in API.md)

- **App layout.** `src/app.h` = `#include "app_metadata.h"` first, the game header, `APP_DIR`.
  The pack-header defines (`APP_VERSION` as `OCT_APP_SEMVER(...)` over
  `APP_VERSION_MAJOR/MINOR/PATCH`, `APP_GUID1`, `APP_TITLE`, `APP_CATEGORIES`, `APP_COLORS`;
  `APP_SAVE_SIZE` through `app_save.h`) live only in `app_metadata.h`, a leaf header (it may
  include only `oct_app_version.h`, `oct_app_categories.h`, `app_save.h`). A second,
  different definition elsewhere: **critical** (the ARM build fails). `APP_GUID1` changed
  or zeroed by the code prompt: **major**. Code never hand-edits `_ids.h` or `index.bin`.
- **Callbacks.** Six are always exported, with exactly these signatures: `on_init()`,
  `on_tick()`, `on_pretwisted(int32_t side)` (a SIDE 0..5, not a twist id; may never be
  followed by `on_twisted`), `on_twisted(int32_t twid, uint32_t disconnected_ms)` (0..11 full,
  12..23 half twists that moved nothing; a 180° twist = two calls; `disconnected_ms` is a
  timestamp, not a duration), `on_tap(int32_t tapid, int32_t count)` (count 1 always
  arrives first), `on_shake(int32_t shakeid)` (never called: a shake always exits). Missing
  or wrong signature: **critical**. Optional ones (`on_proc_draw`, `on_save`,
  `on_save_synced`) exist only together with their `APP_HAS_*` define in
  `app_metadata.h`: a define without the function is **critical** (build fails); a function
  without its define is never called (**major** when the game relies on it, e.g. a save
  that is never written). No unconditional `on_proc_draw` stub is required.
- **`on_init` order.** `OCT_restart(...)` first (else `on_tick` never runs: **critical**), then
  `OCT_viewports_layout(...)` and `OCT_background(...)` (both persist from the previous app).
  `OCT_restart` anywhere else (a restart or new level from `on_tap`/`on_tick`) is **major**: it sets
  the RUNNING state again and the engine then drops every tap and shake for 1 s; reset a scene with
  `OCT_del` (the template's `clearScene`).
- **Lockstep (8 copies of the game).** Every mutable global `TL` (**major** otherwise);
  immutable `static const` / `constexpr` tables and tunables need no `TL` (never flag them).
  `OCT_random` only in `on_init`, `on_tick` and input callbacks, never in `on_proc_draw`;
  random content rolled in `on_init` after `OCT_restart` repeats every launch (seed reset).
  `OCT_random_local` only for cosmetics, never for state or for whether a sprite exists.
  Per-module values (`SND_play`/`SND_play_quad` return values, `OCT_random_local`,
  `OCT_acc_visual_*`, `OCT_screen_quad`, `OCT_save_read` before a sync, anything in
  `on_proc_draw`) never feed game logic. Each violation **major**.
- **Pool and sprites.** `OCT_add` returns 0 on a full pool: check `> 0` before indexing
  (slot 0 is the free-list head); never keep a pointer past `OCT_del` or to an Autokill
  sprite. `SPRITES_CAP` is the app's pool inside the 256 KB module image (engine max
  `OCT_SPRITES_CAP` 5120; ≤ 512 sprites drawn per screen). Sprite references are stored as
  `appObject_t*` (pointers, `NULL` = none), not raw indices: **major** per field.
- **Coordinates.** `OCT_add` / `OCT_add_label` with plane 0..5 already push x, y outward by
  GAP (pass ±120 for quad centres); `OCT_TM_set/move/walk`, tweens and direct `Tm` writes are
  raw (quad centres at ±(120+GAP), one screen step 240+2·GAP). GAP added twice or forgotten:
  **major**. Screen-filling art (backgrounds, panorama pieces, edge-to-edge tiles) placed at ±120
  instead of ±`QUAD_FILL` (119.5; raw ±(119.5+GAP)): **major** (a thin background cross on every face). Angles 0/90/180/270 only; opposite-plane conversions terminate.
- **Upscale-aware sizes.** Sprites without `flags.fullsize` are authored at half size and
  drawn ×2: layout, collision, spacing and bounds must use the on-screen extent (2× the
  authored size). Code using the authored size for coordinates: **major**. FULLSIZE sprites
  (palette or full colour) are 1:1. Every FULLSIZE bitmap draws above all half-res content,
  so a FULLSIZE background hides half-res sprites on that screen (**major** when it does).
- **Per-screen taps.** `OCT_tap_source()` is a normal import on dev (it reads 0 on firmware
  without it): per-screen taps go through the template's `appTapQuad(tapid)`, called from
  `on_tap`, and every caller handles `-1` with the GDD's per-face fallback (missing
  fallback: **major**). It needs no compile switch in `app_metadata.h`; do not ask for one.
- **Sound.** Every sound goes through one play helper that compiles to nothing under
  `<GAME>_MUTE` (a direct `SND_play` bypassing it: **minor**); `SND_play_quad` for sounds
  that belong to a place; music retriggered from `on_tick` (no loop API); no branching on
  `SND_play`'s return value (**major**).
- **Test hooks.** Once the prompt that adds them is done, the game header carries the three
  hooks named in the brief's `test_hooks` (the context's record): `autoplay`
  (`<GAME>_DEBUG_AUTOPLAY`, default 0), `mute` (`<GAME>_MUTE`, default 0) and `plane_pin`
  (`<GAME>_DEBUG_PLAYFIELD_FACE`, or `<GAME>_DEBUG_ROOM_PLANE` in an older game that recorded it;
  default -1), each `#ifndef`-guarded, with the defaults in the source. A name that differs from
  the recorded one, missing, unguarded, or left at a test value: **major** (the visual gate and the
  shipped build depend on them).
- **Builds on both targets.** ARM: `-Werror`, no `double`, no `%f`/`%x` or floats in
  `snprintf`/`OCT_text`, no libc string functions; a warning is **critical**. Windows
  simulator: the macros API.md lists under "Simulator vs cube" (`OCT_get_volume`,
  `OCT_set_volume_transient`, `OCT_screen_quad`, `OCT_link_status`) only inside `#ifdef OCT_APP_MODULE` (**critical** otherwise: the
  simulator build and the visual gate fail). `SIM_SINGLE_THREAD` never defined (**major**).
  New imports that crash on older firmware (`OCT_label_static`, `OCT_tint`, `SND_play_quad`)
  are fine on current firmware; flag them **minor** only when the GDD targets older cubes.
- **Saves** (when `app_save.h` is included; API.md "Saves"): the record starts with
  `{uint32_t magic; uint16_t version; uint16_t size;}`, has fixed-width fields, one
  `static_assert` of `sizeof(saveRecord_t)` (the wire size: the fallback `.oct` builder
  reads `APP_SAVE_SIZE` through it) and `#define APP_SAVE_SIZE sizeof(saveRecord_t)`;
  a missing header field or assert is **major**. A load trusts the bytes only when magic,
  version and size all match (else defaults: **major** otherwise). `on_save` only writes
  (no animation, sound or sync). `OCT_save_sync` belongs in `on_init` (required when saved
  data drives game logic) and at safe boundaries such as a level end, never per tick
  (**major**); after a failed verdict every module uses the same defaults and nothing is
  written until a sync succeeds.
- **Animation placement (guideline (unconfirmed), informational only).**
  At most one animated FULLSIZE / full-screen picture per physical module. A face's four
  screens sit on four different modules; adjacent faces share the two modules along their
  common edge; opposite faces share none. Two animated fullsize pictures whose screens land
  on the same module: a note in `summary`, never an issue and never a deduction (the rule is
  unconfirmed). Small half-res animations are not affected. A full-colour
  animation the GDD/manifest does not mark as explicitly requested: **minor**.
- **Code quality.** No demo code copied from sections marked `Demo: do not copy-paste`; no
  template annotation comments (`Short:` / `Declaration:` / `Comment:` / `Warn:`) in the game;
  explicit casts on narrowing and cross-type assignments; fixed-width types; `appVars_t`
  grouped into `_t` sub-structs per domain (flat bag: **major** per ungrouped domain); small
  focused functions; named constants (tunables in one block at the top).

### Categories

| Category | Max | What to check |
|----------|-----|---------------|
| **api_correctness** | 40 | Every API call matches the template's Declaration / Comment / Critical Comment / Warn annotations and API.md (callbacks, coordinates, sound, saves) |
| **platform_constraints** | 30 | App layout and metadata, the six callbacks + optional ones under `APP_HAS_*`, `on_init` order, lockstep rules, pool limits, upscale-aware sizes, test hooks, saves, both targets build (animation placement is a note only, see above) |
| **code_quality** | 30 | No copied demo code or template comments; grouped sub-structs; `appObject_t*` references; small functions; named constants |

### Prompt Template

```
<the Safety block above, verbatim>

You are a WowCube template compliance verifier. Read the annotated API and the
engine reference, then check the game code against EVERY instruction,
annotation, rule and pitfall in them.

## Task
<insert Verification Task JSON>

## Rules
1. Read app_ai_template.h and API.md FIRST - they are your source of truth
   (API.md wins over habits from older engines)
2. Read the game code (src/app_<game>.h; src/app.h, src/app_metadata.h and
   src/app_save.h when the prompt touched them)
3. For each API call find its Declaration and check it against ALL attached
   Comment / Critical Comment / Warn lines
4. Check the "Rules to check" list of the cube_verifier skill: app layout and
   metadata, the six mandatory callbacks with exact signatures, optional ones
   only with their APP_HAS_* define, OCT_restart first, lockstep (TL on every
   mutable global; static const tables need none; OCT_random vs
   OCT_random_local, no per-module values in logic), OCT_add returning 0, GAP
   pushed only by OCT_add/OCT_add_label, x2 sizes for non-fullsize sprites,
   appTapQuad with a -1 fallback, sound through one play helper, the test hooks
   named in test_hooks (<GAME>_DEBUG_AUTOPLAY / <GAME>_MUTE / <GAME>_DEBUG_PLAYFIELD_FACE,
   or the recorded legacy <GAME>_DEBUG_ROOM_PLANE; #ifndef-guarded, defaults 0 / 0 / -1), ARM and Windows-simulator build breakers, saves (the
   magic/version/size header, the static_assert of the wire size,
   OCT_save_sync in on_init or at safe boundaries, never per tick), no
   SIM_SINGLE_THREAD
5. Struct organisation: appVars_t grouped into _t sub-structs (major per
   ungrouped domain); sprite references stored as appObject_t*, not indices
   (major per field)
6. No copied demo code, no template annotation comments in the game
7. Animation placement: two animated FULLSIZE/full-screen pictures on one
   physical module = a note in summary only (guideline (unconfirmed),
   informational only): no issue, no deduction
8. Score ONLY these categories: api_correctness (max 40),
   platform_constraints (max 30), code_quality (max 30)
9. Cite the template annotation or the API.md section for every issue

## Deduction Rules
- critical (-10): won't compile or link on ARM or in the simulator, breaks the
  engine contract, data loss
- major (-5): wrong API usage, lockstep hazard, missing cast, wrong param type
- minor (-2): style issue, non-functional concern
- any critical issue = status "fail", whatever the total

## Response
Return ONLY this JSON - no markdown, no explanation:
{
  "agent": "template",
  "prompt": N,
  "scores": {
    "api_correctness": <0-40>,
    "platform_constraints": <0-30>,
    "code_quality": <0-30>
  },
  "total": <sum of above, 0-100>,
  "status": "pass if total >= 90 and no critical issue, else fail",
  "issues": [
    {
      "severity": "critical|major|minor",
      "category": "api_correctness|platform_constraints|code_quality",
      "description": "...",
      "location": "file:line or function name",
      "template_rule": "the annotation, instruction or API.md section violated",
      "deduction": N
    }
  ],
  "summary": "one sentence assessment"
}
```

---

## Combined Code Reviewer (`lite` tier)

One agent instead of the Requirements and Template agents, for the `lite` verification tier
(`cube_orchestrator/references/RUN_MODES.md`). It reads the same files as both and applies both
rule sets: the Requirements Agent's "How to Verify" and the Template Agent's "Rules to check". Style
findings (`code_quality`) are reported as minor notes without a deduction; everything that breaks a
build, the engine contract or the design is scored. The visual gate still runs on every prompt.

### Categories

| Category | Max | What to check |
|----------|-----|---------------|
| **completeness** | 30 | every instruction of the prompt is implemented, nothing extra |
| **gdd_alignment** | 15 | mechanics, visuals and behaviour match the GDD; in Mod mode without a GDD, the recorded `mod_request` (Requirements Agent, "Mod mode without a GDD") |
| **no_regressions** | 15 | features from `prior_context` still work |
| **api_correctness** | 25 | every call matches the template's annotations and API.md |
| **platform_constraints** | 15 | app layout, callbacks, `on_init` order, lockstep, pool, sizes, test hooks, saves, both targets build |

### Prompt Template

```
<the Safety block above, verbatim>

You are the WowCube code reviewer (lite tier). You check BOTH whether the code
implements what was asked and whether it uses the engine correctly.

## Task
<insert Verification Task JSON>

## Rules
1. Read app_ai_template.h, API.md, the game code, the GDD and prior_context
   BEFORE scoring
2. Requirements: every instruction implemented, the GDD matched, earlier
   features intact, the verification criteria met
3. Engine: apply the Template Agent's "Rules to check" list of the
   cube_verifier skill (callbacks, OCT_restart first, TL, OCT_random vs
   OCT_random_local, OCT_add returning 0, GAP, x2 sizes, appTapQuad with a -1
   fallback, one sound helper, the three test hooks with their defaults, ARM
   and Windows-simulator build breakers, saves)
4. Style issues: minor notes in summary, no deduction
5. Score ONLY: completeness (max 30), gdd_alignment (max 15),
   no_regressions (max 15), api_correctness (max 25), platform_constraints (max 15)
6. Cite file:line and, for engine issues, the annotation or API.md section

## Deduction Rules
- critical (-10): won't compile or link, feature entirely missing, breaks an
  existing feature, breaks the engine contract
- major (-5): partially implemented, GDD mismatch, wrong API usage, lockstep hazard
- minor (-2): cosmetic difference, small deviation
- any critical issue = status "fail", whatever the total

## Response
Return ONLY this JSON - no markdown, no explanation:
{
  "agent": "code_review",
  "prompt": N,
  "scores": {"completeness": <0-30>, "gdd_alignment": <0-15>, "no_regressions": <0-15>,
             "api_correctness": <0-25>, "platform_constraints": <0-15>},
  "total": <sum, 0-100>,
  "status": "pass if total >= 90 and no critical issue, else fail",
  "issues": [{"severity": "critical|major|minor", "category": "...", "description": "...",
              "location": "file:line or function name", "rule": "prompt line, GDD section, annotation or API.md section",
              "deduction": N}],
  "summary": "one sentence assessment; say full review or re-check"
}
```

Re-check rounds work as for the other code agents ("Re-check rounds").

---

## Screen Review (mandatory, every prompt)

The picture check that runs with or without MCP. The orchestrator builds the game's
plugin with the test hooks, runs the bundled simulator hidden and hands over the frame
folder (`frames_dir`; procedure in `cube_orchestrator/references/VISUAL_GATE.md`, tools in
`tools/sim`). The orchestrator may do the review itself or give it to a fresh
read-only reviewer with this brief; either way somebody opens the PNGs.

Frames are `frame_<index>_<ms>.png`: the six faces as an unfolded cross (TOP above FRONT;
LEFT, FRONT, RIGHT, BACK in a row; BOTTOM below), 2×2 screens per face. The simulator
first shows the engine's boot intro (the eyes on the up face, the other screens near-black): each
module leaves it on its own, about 4-4.5 s in on a desktop and later on a slow machine. Judge only
frames in which no screen still shows it (normally from about 8 s on;
`cube_orchestrator/references/VISUAL_GATE.md`, step 2).

### How to Review

1. Open the first frame after the intro, one from the middle and the last; for motion a
   contact sheet or every 10th frame.
2. Check each item below against the GDD's screen map and this prompt's Verification.
3. A finding names the frame (absolute path), where (face, screen) and what is wrong.

| # | Check | Typical cause |
|---|---|---|
| V1 | Every screen that should show something does: no black, garbage or magenta screens, **no black bars or crosses** between or across screens | pivots, palette alpha, missing assets, a palette backdrop |
| V2 | **Nothing drawn on a wrong face or screen**; the GDD's playfield, HUD and backdrop where the screen map puts them | wrong plane or quad, GAP added twice |
| V3 | On-screen sizes as designed | the ×2 rule ignored (half-size sprites), fullsize misuse |
| V4 | Side faces upright; panoramas continuous around the four side faces; **unique objects (sun, moon, boss) exactly once on the cube** | per-screen tiling, rotation, an object added per face |
| V5 | Clean edges: no boxes, fringes or key colour around sprites | keying, alpha |
| V6 | **HUD and text readable**: spelled right, upright, not cut by a bezel, not under a FULLSIZE layer | fonts not packed, label slots exhausted, layering |
| V7 | Motion between frames: what should move moved (autoplay), what should hold held, no flicker | tick logic, sequences |
| V8 | Stability: the run lasted its time, every frame written, no `terminate`/assert lines in the log tail run_hidden printed | crashes, pool overflow |
| V9 | This prompt's Verification items that can be seen | the prompt |

Severity: a broken or blank picture, a crash, or content on the wrong face = **critical**;
wrong scale, a duplicated unique object, an unreadable HUD, black bars = **major**;
small offsets and fringes = **minor**. Pass = no critical or major finding.

### Prompt Template (fresh reviewer)

```
<the Safety block above, verbatim>

You review the picture of a WowCube game: PNG dumps of all 24 screens from a
hidden simulator run. You only read files; you start nothing.

## Task
<insert Verification Task JSON, including "frames_dir">

## Rules
1. List frames_dir; open the first frame in which no screen still shows the boot intro
   (the eyes on the up face, near-black screens; about 4.5 s on a desktop, later on a slow machine),
   one from the middle and the last (Read tool), more when motion matters
2. Read the GDD's screen map and this prompt's verification_criteria
3. Check V1-V9 of the cube_verifier Screen Review table on every face
4. Every finding names the frame path, the face/screen and what is wrong
5. Report only what the frames show; sound, feel and balance are out of scope

## Response
Return ONLY this JSON:
{
  "agent": "screen_review",
  "prompt": N,
  "verdict": "pass|fail",
  "frames_opened": ["absolute paths"],
  "findings": [
    {"source": "visual_gate", "severity": "critical|major|minor",
     "category": "render|layout|scale|orientation|transparency|text|motion|stability|build",
     "description": "...", "frame": "absolute path", "where": "face / screen"}
  ],
  "summary": "one sentence"
}
```

---

## Playtest Agent

Deployed when the hidden instance's control socket answers (`sim_mcp` = `wire`,
`cube_orchestrator/SIM_MCP.md`). It **launches nothing**: the orchestrator builds a
playtest plugin (`tools/sim/build_game.*` with autoplay off, playfield pin -1, still muted:
the agent's taps, twists and tilts are the only input), starts the bundled simulator hidden
with `tools/sim/run_hidden.ps1 ... -Seconds <playtest_seconds> -EveryMs 0 -McpPort 8177 -AllowEarlyStop`
(Linux/macOS `tools/sim/run_hidden.sh ... --seconds <playtest_seconds> --every-ms 0 --mcp-port 8177`; window
never shown, no audio device; `playtest_seconds` from the context, default 1500: real playtests took 10-20 min,
the old 300 s lifetime ended instances mid-playtest), checks `ping`, and hands over
`playtest_port`, `frames_dir` and `ends_at` (from `run_info.json`: when the instance closes itself)
(`cube_orchestrator/references/VISUAL_GATE.md`). A save check ("a relaunch shows it") needs a second
instance on the first one's work dir (`run_hidden -WorkDir <first OutDir>\work`, `--work-dir`): every run
with a new `-OutDir` starts with empty saves. The orchestrator starts both; the agent reports which run it
judged. The agent
connects, drives the game and scores **what it sees**; the orchestrator stops the instance
by its PID afterwards.

Read `cube_orchestrator/SIM_MCP.md` before the first command: observation script, aiming,
the camera-vs-cube distinction, what a playtest can and cannot judge. Two rules decide
whether a run is worth anything: `cube` / `turn` rotate the **cube** (gravity follows and
the game reacts) while `camera` / `orbit` / `face` only move the viewer; and `shake` exits
to the launcher, so it is a final deliberate check, never a probe.

**Capture with `screens faces <abs.png>`**: the byte-exact six faces
from the 24 framebuffers. `shot` / `screenshot` reads the window's back buffer, which is
unreliable for a window that is never shown; use it at most to read window pixels for
aiming a tap. Commands go through
`tools/sim/mcp.ps1 -Port <playtest_port> "<command>" ...` (Windows) or `simcmd`
(Linux/macOS, SIM_MCP.md).

### How to Verify

1. **Connect.** `info` must name `app_<game>`; anything else: stop and report. Note
   `ends_at` from the brief: plan to finish well before it.
1b. **Reach an interactive state first.** Within the first minutes, bring the game to where it
   takes input (title, a running round) and prove one input produces a visible response
   (`screens faces` before and after). A game that never gets there is a finding (critical:
   no promised input reachable); an instance that stops answering `ping` before `ends_at` is a
   stability finding with the log tail; after `ends_at` it is the lifetime running out, not a
   crash: say so in `not_observed`, never deduct for it.
2. **Idle.** `screens faces` → does it render, right backdrop, no blank faces.
3. **This prompt's mechanic**, with `verification_criteria` as the script: `twist`,
   `tap quad <n>` on the screen the criterion names (n = face·4 + quad, numbered off a
   `screens faces` picture as SIM_MCP.md "Aiming taps" shows; no camera aiming needed),
   `cube` poses for gravity games; after each action `idle`, `sleep 150` (mcp.ps1's own
   pause), then `screens faces`: a capture sent right after `ok twist` still shows the
   pre-twist picture. A tap's reply comes after its strike and the cube's verdict (it can
   take ~0.6 s: the spacing below), and the bundled simulator shows no white tap flash (dev
   firmware's `OCT_DEBUG_TAP_FLASH` is off, SIM_MCP.md "Captures after a tap"), so the
   capture shows the game's own answer. Only a simulator whose version line ends in
   `, tap flash` paints the struck screen white from ~80 to ~180 ms after the tap's reply
   (where `sleep 150` lands): there wait `sleep 300`, and a screen fully white in one capture right after a tap is that indicator,
   never a finding. **Read every tap reply**: `match 1 delivered 1` means the game's
   `on_tap` got the tap on that screen, so a missing response is the game's; `match 0`,
   `err tap_dropped` or `err tap_unconfirmed` mean the tap never reached that screen, so it
   is not a game finding: retry once, then note it. Taps need no `sleep` between them: the
   simulator spaces them itself (each waits until 600 ms after the previous click, so each is a
   fresh single tap, `series 1`), and a double tap is one command, `tap quad <n> double`
   (reply `series 2`). The log shows the same per tap
   (`[sim] tap: screen ...`, then `[gesture] tap fused: module M screen S ...` or
   `tap dropped: ...`): quote those lines as evidence for a tap finding.
4. **Motion.** `record 20 100 <abs prefix>`: compare frames; `<prefix>meta.txt` shows
   whether and when sounds started (`snd`/`sndq`), never how they sound.
5. **Orientation** (games reading gravity): `cube 0 0 0`, `cube 0 0 90`, `cube 0 90 0`, each
   followed by `screens faces`; then `cube 0 0 0` before judging anything else.
6. **Survival.** `ping` still answers, a final `screens faces`, `log` tail without
   `terminate`/assert lines.
7. **Score** only what the frames support.

### Categories

| Category | Max | What to check |
|----------|-----|---------------|
| **visual_correctness** | 40 | It renders what this prompt promised: right art on the right face and screen, nothing off-screen or clipped, right scale (half-size sprites are the classic ×2 bug), no palette garbage, no blank faces |
| **interaction** | 35 | Every input the prompt claims to handle produces a visible response: taps on the specified faces/screens, twists, and tilting with `cube` for gravity games. No response where one was promised: critical |
| **stability** | 25 | It renders and survives the whole playtest. Death mid-playtest or a frozen picture: critical, with the log tail as evidence |

### Scoring discipline

- **Not observable = not a finding.** Sound quality, exact timing, balance, RNG outcomes,
  memory and the physical cube go into `not_observed`, never into deductions.
- **Bring the game to the state you must judge before you judge it.** A round that started
  at boot and ended before you connected (lost with nobody playing) is restarted through the
  game's own flow (tap on the result screen, the title) and played; only a criterion the game
  offers no way to reach goes into `not_observed`. Report `criteria_observed` ("4/6"): a
  score built on two observed criteria out of six says little, and the orchestrator reads it.
- **Never deduct for what the code agents own** (API misuse, casts, style).
- **`err no_screen` is an aiming error**, not a game defect: re-aim at the middle of a quad, or
  use `tap quad <n>`. Likewise a tap whose reply is not `match 1 delivered 1` never reached the
  game on that screen: not a game defect. One exception to read for: `match 1 ... delivered 0` on
  ordinary taps sent within ~1 s of a delivered one (they alternate 1 / 0, a double tap's second is 0)
  means the game calls `OCT_restart` on each tap and so restarts the engine's 1 s tap settle window
  (SIM_MCP.md "Lost taps after a restart"): a player loses those taps on the cube too, so report it
  once as a responsiveness finding. After a tap that restarts the game or changes level by design it
  is expected: `sleep 1100`, tap again, no deduction.
- **Judge layout only with the cube upright** (`cube 0 0 0`).
- **The launcher after a `shake` is correct behaviour**, not a crash.
- **A flaw that predates this prompt** is a regression only if the prompt was meant to fix it;
  otherwise mention it in `summary`.
- When in doubt between a deduction and uncertainty, choose uncertainty.

### Prompt Template

```
<the Safety block above, verbatim>

You are a WowCube playtester. A HIDDEN, muted simulator is already running the
game built from the current source, with autoplay off and the playfield not
pinned: your inputs are the only ones. You never start, show or stop it. Drive
it through its control socket and score what you see.

## Task
<insert Verification Task JSON, including "playtest_port" and "frames_dir">

## Rules
1. Read <skills>/skills/cube_orchestrator/SIM_MCP.md FIRST (observation
   script, aiming, camera vs cube, limits)
2. Use the wire protocol on playtest_port:
   powershell -NoProfile -ExecutionPolicy Bypass -File <skills>/tools/sim/mcp.ps1 -Port <playtest_port> "<command>"
   (Linux/macOS: the simcmd function in SIM_MCP.md)
3. `info` must name app_<game> before anything is scored; the instance closes itself at
   ends_at (in the Task): first bring the game to an interactive state and prove one
   input works, then follow the script, and finish before ends_at
4. Capture every observation with `screens faces <absolute png in frames_dir>`
   Do not judge from `shot`/`screenshot`
5. Follow the observation script: idle -> this prompt's verification_criteria
   with twist/tap/cube -> record for motion -> orientation (gravity games) ->
   survival (ping, final screens faces, log tail)
6. Every finding names the action and the frame that shows it. No frame, no finding
7. Not observable (how it sounds, timing, balance, RNG, the physical cube) goes
   into not_observed with NO deduction
8. Do not read or score the source code
9. Tap a screen with `tap quad <n>` (n = face*4 + quad: faces top 0, front 1, right 2, back 3,
   left 4, bottom 5; in each face of a `screens faces` picture quad 0 top-right, 1 top-left,
   2 bottom-left, 3 bottom-right). Its reply says where the tap went: only
   `match 1 delivered 1` reached the game's on_tap on that screen; `match 0`, `err tap_dropped`
   or `err tap_unconfirmed` = the tap never arrived (retry once, then note it, no deduction).
   `tap_dropped` = the cube's leader decided it was no tap (too few modules' rows agreed);
   `tap_unconfirmed` = it decided nothing for that click (rows absorbed into a tap struck within
   50 ms before it, a twist opening or settling, or modules not running); neither means the game
   is broken. Send taps back to back, no `sleep`: each `tap` waits until 600 ms after the previous
   click before it strikes (so a reply can take ~0.6 s), and is always a single tap (`series 1`).
   For a double tap send ONE command, `tap quad <n> double`: two clicks 200 ms apart, the reply
   says `series 2`. Two separate `tap` commands never make a double tap.
   Quote the log's `[gesture] tap fused` / `tap dropped` lines as evidence for any tap finding.
   `tap <x> <y>` (window pixels) also works; its `err no_screen` = your aim missed
10. cube/turn rotate the CUBE (gravity follows); camera/orbit/face only move the
    viewer. Stand the cube upright with `cube 0 0 0` before judging layout
11. Never `shake` unless this prompt is about shake-to-exit, and then only last
12. Score ONLY: visual_correctness (max 40), interaction (max 35), stability (max 25)

## Deduction Rules
- critical (-10): does not render, crashes or freezes, a promised input does
  nothing at all
- major (-5): renders but visibly wrong - wrong face/screen, wrong scale, cut
  off, a response that happens but not as described
- minor (-2): cosmetic offset, small misalignment, non-functional oddity
- any critical issue = status "fail", whatever the total

## Response
Return ONLY this JSON - no markdown, no explanation:
{
  "agent": "playtest",
  "prompt": N,
  "scores": {
    "visual_correctness": <0-40>,
    "interaction": <0-35>,
    "stability": <0-25>
  },
  "total": <sum of above, 0-100>,
  "status": "pass if total >= 90 and no critical issue, else fail",
  "issues": [
    {
      "severity": "critical|major|minor",
      "category": "visual_correctness|interaction|stability",
      "description": "...",
      "observed_via": "the command, e.g. 'twist 3' then 'screens faces .../p03_after_twist.png'",
      "frame": "absolute path of the screens faces PNG that shows it",
      "deduction": N
    }
  ],
  "not_observed": ["what could not be checked and why"],
  "criteria_observed": "<observed>/<total verification criteria>",
  "frames": ["absolute paths of the PNGs written"],
  "summary": "one sentence assessment"
}
```
