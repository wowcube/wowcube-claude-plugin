# Agent briefs (cube_orchestrator reference, Stage 4 and Mod mode)

All data between the orchestrator and its subagents is JSON. Read this file before
dispatching the first coder of a session. Engine facts and limits are in
`<skills>/templates/app_ai_template/API.md`; the API usage source of truth is
`<skills>/templates/app_ai_template/src/app_ai_template.h`.

## Safety block (top of EVERY subagent brief)

Coders, fixers, the code reviewers (Requirements, Template or Combined), the Playtest Agent and art
reviewers all get it, verbatim:

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

## Coding Task JSON (orchestrator → coder)

```json
{
  "task": "code",
  "game": "<game>",
  "prompt_number": 3,
  "prompt_title": "...",
  "total_prompts": 12,
  "instructions": "<the full prompt text>",
  "verification_criteria": "<what must be visible / must happen>",
  "platform_reminders": ["..."],
  "standing_rules": ["<lines from context/rules.md that apply>"],
  "profile": {"guidance": "autonomous", "experience": "cpp", "verification": "standard",
              "art": {"source": "codex", "provider": null}, "data_policy": {"may_leave_machine": ["prompts"]}},
  "test_hooks": {"autoplay": "<GAME>_DEBUG_AUTOPLAY", "mute": "<GAME>_MUTE", "plane_pin": "<GAME>_DEBUG_PLAYFIELD_FACE"},
  "asset_facts": {"music_loop_ticks": 309},
  "files_to_read": [
    "<skills>/templates/app_ai_template/src/app_ai_template.h",
    "<skills>/templates/app_ai_template/API.md",
    "<ws>/app_<game>/src/app_metadata.h",
    "<ws>/app_<game>/src/app_<game>_ids.h",
    "<ws>/app_<game>/src/app_<game>.h"
  ],
  "files_to_write": ["<ws>/app_<game>/src/app_<game>.h"],
  "scratch": "<ws>/.agent_scratch/p03",
  "compile_check": "<build_game command with -OutDir <ws>/.agent_scratch/p03/build>",
  "prior_context": [
    {"prompt": 1, "title": "...", "structs_added": [], "fields_added": {}, "functions_added": [],
     "globals_changed": [], "sprites_used": 0, "notes": "..."}
  ]
}
```

A prompt that adds saves or an optional callback also lists
`app_<game>/src/app_metadata.h` (the `APP_HAS_*` switch, `#include "app_save.h"`) and
`app_<game>/src/app_save.h` in `files_to_write`.

## Coder Response JSON (coder / fixer → orchestrator)

```json
{
  "status": "done|error",
  "prompt": 3,
  "files_modified": ["<ws>/app_<game>/src/app_<game>.h"],
  "summary": {"structs_added": [], "fields_added": {}, "functions_added": [], "globals_changed": [],
              "sprites_used": 0, "notes": "..."},
  "error": null
}
```

## Verification Task JSON (orchestrator → Requirements / Template / Playtest)

```json
{
  "task": "verify",
  "game": "<game>",
  "prompt_number": 3,
  "prompt_title": "...",
  "instructions": "<the original prompt text>",
  "verification_criteria": "...",
  "files_to_read": [
    "<ws>/app_<game>/src/app_<game>.h",
    "<ws>/plans/<game>_gdd.md",
    "<skills>/templates/app_ai_template/src/app_ai_template.h",
    "<skills>/templates/app_ai_template/API.md"
  ],
  "prior_context": [],
  "test_hooks": {"autoplay": "<GAME>_DEBUG_AUTOPLAY", "mute": "<GAME>_MUTE", "plane_pin": "<GAME>_DEBUG_PLAYFIELD_FACE"},
  "mod_request": null,
  "profile": {"guidance": "autonomous", "experience": "cpp", "verification": "standard",
              "art": {"source": "codex", "provider": null}, "data_policy": {"may_leave_machine": ["prompts"]}},
  "frames_dir": "<ws>/assets_<game>/qa/sim/p03-1",
  "playtest_port": 8177,
  "ends_at": "2026-11-02T10:45:00Z",
  "recheck": null
}
```

`mod_request` (Mod mode only, else `null`): the user's own words for this change, copied from the context's
`prompts[].request` (the orchestrator records it when it classifies the change, M2). Without a GDD the
reviewers score `gdd_alignment` against it (`cube_verifier`, "Mod mode without a GDD"); `files_to_read` then
lists no GDD.

`profile` is the resolved snapshot (`wowcube-setup/references/PROFILE.md`, "Resolved snapshot"):
every brief carries the fields that matter to the agent (tier, data policy, `art`; `experience` for
anything the user will read). `test_hooks` is the context's record: the verifier checks those names. `frames_dir`, `playtest_port` and `ends_at` (the instance's `run_info.json`: when its `-Seconds` lifetime runs out) are for the Playtest Agent only. Every brief also names a
scratch folder (`<ws>/.agent_scratch/p<NN>/`) for throw-away files (every temporary image, script or log goes
there, never into `assets_<game>/`, `app_<game>/` or a folder nested under them; keep its full paths short, under
200 characters: Windows refuses longer ones, and Pillow then fails to write a PNG with "No such file or
directory"), and coder and fixer briefs carry
the `compile_check` command (below).

**Compile check (coders and fixers).** The one allowed compile is the pipeline's own build into the
scratch folder; it runs the cube's ARM `-Werror` device check, then the simulator plugin build, and
writes nothing into `app_<game>/`:

```
powershell -NoProfile -ExecutionPolicy Bypass -File <skills>\tools\sim\build_game.ps1 -AppDir <ws>\app_<game> -OutDir <ws>\.agent_scratch\p<NN>\build
<skills>/tools/sim/build_game.sh <ws>/app_<game> --out-dir <ws>/.agent_scratch/p<NN>/build
```

Exit 0 = `BUILD OK`; else the first errors are printed (logs in `<OutDir>/obj/`). Never hand-written
compiler lines, never an engine, SDK or octavios folder outside `<skills>/simulator/` (the only engine
the pipeline builds against). No compiler on the machine → say so in `notes`; the orchestrator's
visual gate build is the check then. The orchestrator fills `compile_check` with the real paths. `recheck` is set from the second check round on:
`{"previous_report": "<ws>/context/reports/p03_requirements_r1.json", "diff": "<ws>/context/reports/p03_fix_r1.diff"}`
(the agent's own last report and the fixer's unified diff of the game files; the
orchestrator writes both). The agent then re-checks narrowly (`cube_verifier`, "Re-check
rounds"). The agents' prompt
templates, categories and response JSON are defined in `cube_verifier`
(Requirements: completeness 45, gdd_alignment 25, no_regressions 20,
verification_criteria 10; Template: api_correctness 40, platform_constraints 30,
code_quality 30; Combined Code Reviewer, `lite` tier only: completeness 30, gdd_alignment 15,
no_regressions 15, api_correctness 25, platform_constraints 15; Playtest: visual_correctness 40,
interaction 35, stability 25; each
scored out of 100, pass at 90 **and no critical issue**: one critical issue fails the
agent whatever its total). Prepend the Safety block to each of them.

## Visual-gate finding (orchestrator → fixer)

```json
{"source": "visual_gate", "severity": "critical|major|minor",
 "category": "render|layout|scale|orientation|transparency|text|motion|stability|build",
 "description": "a black cross, about 36 px wide, between the screens of every face",
 "frame": "<ws>/assets_<game>/qa/sim/p01-1/<frame>.png", "where": "all six faces"}
```

## Coder Agent prompt template

```
You are a WowCube game coder. Implement exactly what the task describes.

<Safety block>

## Task
<Coding Task JSON>

## Rules
1. Read ALL files in files_to_read before writing code. app_ai_template.h is the source
   of truth for API usage (do not copy its demo code); API.md has the engine facts and
   limits.
2. Follow `instructions` exactly: no extra features, no refactoring of unrelated code.
   Respect platform_reminders and standing_rules. Use prior_context; break nothing that
   exists.
3. Explicit casts for every conversion between numeric types, pointers and enums.
   Fixed-width <stdint.h> types only (int8_t ... uint32_t, size_t); never plain int,
   short or long.
4. Callbacks as in the template: on_init, on_tick, on_tap(int32_t tapid, int32_t count),
   on_twisted(int32_t twid, uint32_t disconnected_ms), on_pretwisted(int32_t side) and
   on_shake(int32_t shakeid) always exist (on_shake is never called: a shake always exits
   to the launcher, so no gameplay on shake). Optional callbacks (on_proc_draw, on_save,
   on_save_synced) are bound only with their APP_HAS_* switch in app_metadata.h.
   Reference unused parameters to silence warnings.
5. Coordinates (API.md, "Coordinates and drawing"): engine calls take PLANE
   coordinates, origin = the face centre, X right, Y up, |X|,|Y| < 240 + 2*GAP. A face's
   four screens are quads centred at (+-120, +-120) when passed to OCT_add /
   OCT_add_label with plane 0..5 (they add the GAP themselves), but at
   (+-(120+GAP), +-(120+GAP)) for raw calls (OCT_TM_set/move/walk, tweens, direct Tm
   writes); one screen step = 240 + 2*GAP. Layout inside one screen is done as offsets
   from that screen's quad centre (1 unit = 1 on-screen pixel, a screen spans +-120),
   except screen-FILLING art (backgrounds, panorama pieces, edge-to-edge tiles): it goes at
   +-QUAD_FILL = +-119.5 (raw +-(119.5+GAP)), or a 2-px background line shows on the inner edges,
   then added to the quad centre of the right kind; name which kind every coordinate
   is. Sprites are authored at half size and drawn x2 (fullsize sprites 1:1): every
   position, bound, hitbox, spacing and grid step uses the ON-SCREEN extent, never the
   authored size.
6. Lockstep: the app runs as 8 identical copies, one per module. Game-state randomness
   only via OCT_random in on_init / on_tick / input callbacks; OCT_random_local for
   per-face decoration; nothing in on_proc_draw touches game state; never branch game
   logic on SND_play / SND_play_quad return values.
7. Keep the test hooks (test_hooks) compiling and off by default. When this prompt adds
   a mechanic, extend the autoplay bot so a hidden run exercises it; the bot varies per
   round (OCT_random or a round counter), never replays one fixed round.
8. Use only BMP_* / SND names that exist in the ids header and the manifest. Never
   create assets, never edit the _ids.h file.
9. Modular, readable code: state in structs, small functions, named constants; every
   pace number (speeds, intervals, cooldowns) in the tunables block.
10. Before replying, run `compile_check` (the device check + the plugin build into your scratch
    folder) until it prints BUILD OK. Compile nothing else, and never against engine or SDK paths
    outside <skills>/simulator.
11. Reply with the Coder Response JSON only.
```

## Fix Agent prompt template

```
You are a WowCube code fixer. Fix exactly the listed issues.

<Safety block>

## Task
{
  "task": "fix",
  "game": "<game>",
  "prompt_number": 3,
  "original_instructions": "<the prompt text>",
  "issues": [<union of the failing gates' issues: code reviewers, visual gate, Playtest>],
  "frames": ["<abs paths of the frames that show the visual issues>"],
  "build_log": "<compiler output when the build failed, else null>",
  "standing_rules": [],
  "test_hooks": {},
  "files_to_read": ["<ws>/app_<game>/src/app_<game>.h",
                    "<skills>/templates/app_ai_template/src/app_ai_template.h",
                    "<skills>/templates/app_ai_template/API.md"],
  "files_to_write": ["<ws>/app_<game>/src/app_<game>.h"],
  "scratch": "<ws>/.agent_scratch/p03_fix1",
  "compile_check": "<build_game command with -OutDir <ws>/.agent_scratch/p03_fix1/build>"
}

## Rules
1. Read the source file first, then open every frame in `frames`: each shows all 24
   screens as rendered by the hidden simulator.
2. Fix ONLY the listed issues: no refactors, no features.
3. For a visual issue, name the code that caused it in `notes`; a guess is not a fix.
4. Keep the test hooks compiling and off by default.
5. Run `compile_check` until it prints BUILD OK (nothing else, no engine paths outside
   <skills>/simulator).
6. Reply with the Coder Response JSON only.
```

After a fix every gate of the tier runs again: the code reviewers (diff re-check), the visual
gate and the Playtest Agent when the tier deploys it.

## Platform reminders (pick per prompt)

| If the prompt mentions | Reminder |
|---|---|
| init, scaffold, on_init | "Call OCT_restart((int*)gObjects, cap, (int32_t)sizeof(appObject_t)) first in on_init (without it on_tick never runs), then OCT_viewports_layout(SCHEME_CUBE, GAP, GAP) and OCT_background(rgb565): both persist from the previous app. Random draws right after OCT_restart repeat on every launch; generate random content in the first on_tick. Call OCT_restart ONLY in on_init: called from on_tap (a restart, a new level) it sets the RUNNING state again and the engine drops every tap for 1 s; reset a scene with OCT_del (the template's clearScene)." |
| global, TL, static | "Every mutable app global is TL (`TL static type name;`): the simulator runs the 8 modules as threads. Immutable `static const` tables and tunables need no TL." |
| iterate, loop, gObjects | "gObjects[0] is the pool's free-list head: iterate from 1 and skip dead slots (`obj->Idx == i`). Freed slots are reused at once; autokilled sprites vanish." |
| OCT_add, sprite, layer, pool, many | "OCT_add returns 0 when the pool is full: check it. The pool is the app's own array (SPRITES_CAP in the template; raise it if the scene needs more; engine max 5120, but code + data + the pool must fit the module's 256 KB). At most 512 sprites are drawn per screen. Bitmap angles: multiples of 90 only. GAP: OCT_add/OCT_add_label with plane 0..5 push x,y past the bezel themselves (pass +-120 for screen centres); OCT_TM_set/move/walk, tweens and direct Tm writes do NOT (screen centres at +-(120+GAP)) - say which one a coordinate is (API.md, Coordinates)." |
| label, text, font, glyph | "Toggle a label's child glyphs with it (`obj->Parent == label->Idx`). OCT_label_set / OCT_label_embed share 64 text slots (62 usable); static captions use OCT_label_static (no slot). Labels draw nothing if the font is not packed (font_ ids in _ids.h). Fonts draw x2: on screen FONT_1 capitals ~53 px wide, FONT_2 ~31, FONT_3 ~22 (a screen is 240); \n steps only 1x the line height, so use one label per line spaced 2x the line height (API.md, Fonts are drawn x2). A FULLSIZE picture on the same screen hides labels." |
| position, coordinate, centre, fit, bounds, edge | "Engine coordinates are plane coordinates: origin = the face centre, X right, Y up. Quad (screen) centres are (+-120, +-120) for OCT_add / OCT_add_label on plane 0..5 (GAP added for you) and (+-(120+GAP), +-(120+GAP)) for OCT_TM_set/move/walk, tweens and Tm writes. Lay out inside one screen as offsets from its quad centre (a screen spans +-120 on-screen pixels). Screen-filling art (backgrounds, panorama pieces, edge-to-edge tiles) goes at +-QUAD_FILL = +-119.5 (raw +-(119.5+GAP)): at +-120 a 2-px background line shows on the inner screen edges. A sprite's ON-SCREEN extent is 2x its authored size (fullsize: 1x): do all position, centring and edge-fit math with it." |
| collision, overlap, hit, distance, spacing, grid | "Hitboxes, overlaps, spacing and grid steps use the on-screen extent (2x authored, fullsize 1x); the authored size makes everything half as big as drawn." |
| walk, move, cross, plane, wrap | "Distance between neighbouring screens = 240.0f + 2.0f * GAP. OCT_TM_walk(tm, dir, fwd, left, true) is the preferred way to move across faces; OCT_TM_move adds and wraps; OCT_TM_change_plane refuses opposite planes." |
| sound, SND, audio, music | "int32_t id = SND_getAssetId(\"<name>.mp3\"); (cache it) then SND_play(id, volume 0..100). Up to 6 sounds per module play at once and add up; a 7th is refused. SND_play_quad(id, vol, quad) plays only on the module showing that scene quad. There is no stop or loop call: re-issue the music every music_loop_ticks ticks from on_tick. Never branch game state on the return value. Every sound goes through one helper that compiles to nothing under the mute hook." |
| animation, sequence, frame | "OCT_sequence(spr, from, to, framelen, OCT_SEQ_RESTART / OCT_SEQ_REVERSE / OCT_SEQ_REFRESH). A frame lasts Rate x framelen + 1 ticks (Rate 1 from our packer: framelen 0 = 20 fps, the hardware cap; framelen 1 = 10 fps)." |
| twist, twid, on_twisted, on_pretwisted | "Full twists: twid 0..11; half twists 12..23 (OCT_TWIST_HALF, nothing moved). A 180-degree twist arrives as two calls with the same twid. on_pretwisted gets the plane being turned, not a twist id, and may never be followed by on_twisted. CW/CCW are seen from outside the face." |
| tap, on_tap, screen | "on_tap(tapid, count): tapid is the face 0..5; count is the place in a series (60..536 ms apart). The exact screen comes from the template's appTapQuad(tapid) (OCT_tap_source; scene quad 0..23, -1 when unknown); always keep a per-face fallback." |
| tilt, gravity, orientation, up face | "OCT_TM_gravity_x/y/n(plane) are synced on all 8 modules (safe for logic; ~10 Hz at rest). OCT_TM_top_side() gives the up face. Use hysteresis on tilt thresholds." |
| save, high score, progress, settings | "Saves (API.md, Saves): app_save.h holds a record that starts with {uint32_t magic; uint16_t version; uint16_t size;}, fixed-width fields, a static_assert of sizeof(saveRecord_t) (the wire size) and #define APP_SAVE_SIZE sizeof(saveRecord_t) (<= 512 KB). on_init reads it with OCT_save_read and trusts it only when magic, version and size all match (a fresh area reads zeros), else defaults. When saved data drives game logic, OCT_save_sync(0, sizeof(rec)) in on_init and read back in on_save_synced; on a failed verdict every module starts from the same defaults and writes nothing until a sync succeeds. Write small records at safe moments and in on_save (APP_HAS_ON_SAVE). Until on_save_synced arrives, show a placeholder (BEST --), never the defaults as saved values. Sleep/wake and re-assembly relaunch the game to home, so progress must be saved." |
| angle, rotation, direction | "Angle a / Tm.A: degrees, positive = CCW, 0 = right (+X)." |
| random | "OCT_random(dmin, dmax): dmax exclusive, needs dmax > dmin." |
| transparency, fade | "Transp: 0 = opaque, OCT_TRANSP_MAX = invisible." |
| teleport, OCT_TM_set | "OCT_TM_set overwrites position, angle and plane at once (teleport, no animation)." |
| XSIGN, YSIGN, quad | "XSIGN / YSIGN are declared in oct_shared.h: do not redeclare." |
| background, colour | "Colours are RGB565." |

**Always include (every coding task, every mode):**
- "Use explicit type casts; never rely on implicit conversions between numeric types, pointers or enums."
- "Use only fixed-width types from <stdint.h>; never plain int, short or long."
- "Callbacks as in the template: the six mandatory ones always exist; optional ones only with their APP_HAS_* switch."
- "Sprites are drawn x2 (fullsize 1x): all layout and collision math uses the on-screen extent."
- "Keep the test hooks compiling and off by default; extend the autoplay bot for every new mechanic."
- "Never create assets or edit the _ids.h file; use only names from the manifest."

## Context file (`context/<game>_context.json`)

Saved after every passed prompt and at every stage change; the resume point of the
run. **This block is the one definition of the context's fields**; every other file
(the orchestrator's SKILL.md, `STAGE3_ASSETS.md`, the briefs) uses these names and shapes.

```json
{
  "game": "<game>",
  "run_mode": "autonomous|stepwise",
  "profile": {"resolved_at": "2026-11-02T10:00", "entry": "new", "role": "developer",
              "guidance": "autonomous", "experience": "cpp", "verification": "standard",
              "budget": {"usage": "normal", "hours": null, "images": 80, "fix_rounds": 3,
                         "rescopes": 3, "scope_cuts": "ask"},
              "art": {"source": "codex", "provider": null}, "sound": {"source": "cc0"},
              "data_policy": {"may_leave_machine": ["prompts"]}},
  "import": {"from": "<source path>", "mode": "update|fork", "app_dir": "app_<game>", "date": "2026-11-02",
             "rights": "yes|unsure", "art_extracted": "assets_<game>/extracted.json",
             "identity": {"guid1": "0x...", "title": "...", "version": "0.0.0",
                          "fork_of": {"app_dir": "app_<old>", "guid1": "0x..."}}},
  "spend": {"started": "2026-11-02T10:05", "images_used": 34, "rescopes_used": 0},
  "art_budget": {"images": 80, "minutes": null},
  "sdk": {"simulator": "~/.wowcube/sim/<version>/<os>/wowcube-sim", "version": "<wowcube-sim --version line>",
          "check_env": "ok"},
  "infra": "ok",
  "style_lock": {"status": "pending|approved|waived|user_art", "anchors": ["assets_<game>/style/anchors/hero_idle_00.png"], "date": "2026-10-28"},
  "art_source": "codex|own|procedural|provider|placeholder|original",
  "sound": {"source": "cc0|synth", "music_loop_ticks": 309, "credits": "app_<game>/sound/CREDITS.md"},
  "test_hooks": {"autoplay": "FF_DEBUG_AUTOPLAY", "mute": "FF_MUTE", "plane_pin": "FF_DEBUG_PLAYFIELD_FACE"},
  "sim_mcp": "wire|absent",
  "playtest_port": 8177,
  "playtest_seconds": 1500,
  "last_completed_prompt": 3,
  "total_prompts": 12,
  "prompts": [
    {"prompt": 1, "title": "Scaffold and backdrop",
     "structs_added": ["appObject_t fields: type, state"], "fields_added": {"appVars_t": ["gameState"]},
     "functions_added": ["initGame"], "globals_changed": [], "sprites_used": 24,
     "scores": {"requirements": 97, "template": 95, "playtest": 92},
     "visual_gate": {"verdict": "pass", "frames": "assets_<game>/qa/sim/p01-2", "findings": []},
     "fix_rounds": 1, "notes": "black backdrop on all faces"}
  ],
  "cuts": [],
  "accepted_majors": [{"prompt": 3, "finding": "...", "reason": "..."}],
  "accepted_minors": [{"asset": "glow_ring_03", "finding": "..."}],
  "not_checked_visually": [],
  "delivery": {"oct": "dist/app_<game>.oct", "builder": "python|octpack", "version": "1.0.3",
               "store_consent": "2026-10-28",
               "store": {"url": "https://store.wowcube.com/uploads/<id>?password=<pw>",
                         "qr": "dist/app_<game>_qr.png", "date": "2026-10-28T23:10", "version": "1.0.3",
                         "sha256": "..."},
               "report": "context/<game>_report.md"},
  "balance_passes": [],
  "pending": [{"request": "<the user's words>", "date": "2026-11-03", "note": "waits for the boss"}],
  "history": [{"n": 1, "label": "prompt 1", "kind": "change|pre_undo|undo", "date": "2026-11-03T10:05:00",
               "dir": ".history/001_prompt_1", "assets": false, "request": null, "undone": null}]
}
```

- `profile` is rewritten at every entry from the profile files (`wowcube-setup/references/PROFILE.md`,
  "Resolved snapshot": the project file's shape with every limit filled); `spend` counts against
  `profile.budget` (RUN_MODES.md, failure policy). `run_mode` is rewritten at every entry by the one
  rule in RUN_MODES.md (request, else `profile.guidance`).
- `art_source` is what the art really is (it falls back to `procedural` when the asked source cannot
  draw); `profile.art.source` is what the profile asked for.
- `import` exists only for a game that came in through Mod mode M0; its presence means M0 is done.
  `identity` is written for a fork only: the new GUID, title and version (`scripts/fork_app` prints it),
  and the game it was forked from. `rights` is the profile's `source.rights` (`unsure` = private testing
  only, never published); `art_extracted` names the listing when M0 extracted the game's packed art.
- `delivery.store` is the last store upload (`scripts/store_upload.py`: the install link with its
  `?password=`, the QR PNG); `store_consent` is the date of the user's one yes to uploading this game.
  `delivery.report` is the end-of-run report file Stage 5 writes. There is no `cube` field (nothing goes to
  a cube from this computer; an older context's `cube` is ignored).
- `pending` holds requests the user mentioned but did not start (RUN_MODES.md, "Interrupts"): shown on
  the next entry, removed when done or dropped.
- `history` is written by `scripts/history.py` (a snapshot before every change, the undo records); never
  by hand.
- `style_lock` is always an object: the intake writes `{"status": "pending"}`; Stage 3 sets
  `status` to `approved` (with `anchors` and `date`), `waived` or `user_art`. Stage
  detection reads `style_lock.status`.
- `sound.music_loop_ticks` is the music retrigger period printed by `sound_kit.py loop`
  (Stage 3); there is no top-level `music_loop_ticks`. A coding brief copies it into its
  `asset_facts.music_loop_ticks`.
- `playtest_seconds` is the playtest instance's `-Seconds` lifetime (default 1500 when absent; raise it
  for a long game). `spend.images_used` is written by the image ledger (`art.py` / the paid path,
  `cube_art-director/scripts/art_budget.py`: `context/<game>_images.json` holds every request), never
  counted by hand.
