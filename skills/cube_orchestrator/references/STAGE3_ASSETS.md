# Stage 3: assets (cube_orchestrator reference)

Style lock, art, sound, launcher icon, fonts, pack. The work is done by
`cube_asset-builder`, whose Codex path is `cube_art-director`; this file is the
orchestrator's order of steps and its gates. Read `cube_art-director/SKILL.md`,
`cube_art-director/references/QA_RULES.md` and `cube_art-director/references/CODEX.md`
before the first generation.

Per-game workspace `<ws>/assets_<game>/` (never one shared `assets/`):

| Path | Holds |
|---|---|
| `style/` | `STYLE.md` (style bible), `anchors/` (the lock), `candidates/`, `profile.json`, `palette.png`, `mock.png` |
| `raw/` | Codex output, prompts and keys used |
| `art/` | final exact-size PNGs; the pack reads them from here |
| `original/`, `extracted.json`, `icon.png` | Mod mode only: a packed game's own art as `scripts/extract_art.py` decoded it (never edited; `keep` sprites are copied from here), its listing and its launcher icon |
| `qa/` | QA sheets (`all.png`: every final at device scale; `sets.png` + GIFs when the manifest has sets) and `qa/sim/` simulator frames |
| `review.html`, `fixes.json` | the review page; every correction (a regeneration replays them) |
| `sound_src/` | approved downloads (one folder per source), `recipes.json` |
| `wav/assets/` | engine mp3s; the pack copies them into `app_<game>/sound/assets/` |
| `fonts/` | BMFonts copied in by the pack |

Art tool, run from `<ws>`: `python <skills>/skills/cube_art-director/scripts/art.py <command> plans/<game>_assets.json`
(it finds `assets_<game>/` itself). Commands below abbreviate it as `art.py <command> <manifest>`.

The infra gate has already scaffolded `app_<game>/` (the pack writes into it).

## 1. Gate the manifest (before any generation)

Return to Stage 2 (`technical_prompter`) when a check fails; never patch the manifest
yourself (Build mode; in Mod mode the orchestrator creates and edits it, `cube_orchestrator/SKILL.md`
"Who writes the manifest"). Tiers, sizes and limits are in `<skills>/templates/app_ai_template/API.md`.

First the provider-free check (it never generates and never touches the network; exit 0
= valid, 2 = errors, each printed):

```
python <skills>/scripts/build_pipeline.py validate --manifest plans/<game>_assets.json
```

It covers the schema, names, sizes against the tier limits, the `background` field, the
`launcher_icon` entry, the Codex prompt rules it can check, an empty manifest (no game sprites:
an error) and the **image budget**: it prints how many images the draw still needs (sprites
without a PNG in `assets_<game>/raw/` or `art/`; one per panorama with an undrawn piece) against
the budget (`art_budget.images` / the profile's `budget.images` / the tier), warns above 60% and
fails above 100% or above what is left of it (back to Stage 2 to cut drawn images, or ask the user
for more budget). Drawn sprites cost nothing, so a Mod-mode edit counts only its new sprites. **Rerun it after every edit of the
manifest**, by anyone (a Stage 2 return, a simplified asset in §3, a Mod-mode change, a hand fix):
exit 2 stops everything until the manifest is fixed; never generate or pack from a manifest that
did not pass it since its last change. Then look at what it
cannot judge (sizes that read like on-screen pixels, panoramas, the sound plan):

- **Names**: `[a-z][a-z0-9_]*` (a letter first), at most 23 characters, unique, not
  reserved (`pal`, `0`, `icon`, `zero`, `none`, `last`, `ico`, `ico_idle`, `ahover`,
  `bmp_none`, `bmp_last`, `bmp_0`, `map_none`, `map_last`), not shaped like a packer font
  glyph (`font_<x>_<5 digits>`) and not an animation's alias (`<base>`, `<base>_end`).
  The launcher icon is e.g. `launcher_icon`.
- **Sizes** are authored pixels: every sprite without `flags.fullsize` at most 120×120
  (drawn ×2); only `flags.fullsize` sprites go up to 240×240 (drawn 1:1). A sprite sized in on-screen
  pixels (a quarter-screen hero at `[60, 60]` instead of `[30, 30]`) is a sizing error. Typical sizes per
  role and the check: `cube_art-director/references/SIZES.md` (`art.py sizes plans/<game>_assets.json`
  flags a size that cannot work or is unusual for its role).
- **Opaque backgrounds** are `color: "full"` (a palette `bg` sprite once rendered magenta).
- **`background`, the backdrop decision**: every sprite states `"key"` (a cut-out:
  characters, props, effects, UI, text) or `"opaque"` (a full-frame picture:
  backgrounds, tiles, panorama pieces, every `color: "full"` or `flags.bg` sprite).
  art.py wraps each prompt itself: the style block, a square canvas with one subject and
  a clear margin, and for `key` sprites a flat `#FF00FF` backdrop (`#00FF00` when the
  subject is pink or magenta) that it keys away afterwards. Opaque pictures get no
  backdrop and are never keyed.
- **`gen_prompt` describes the subject only** (`technical_prompter` Step 4a): what it
  is, its colours, which way it faces, the framing, frame phases, "no characters" for
  effects, holes that must stay solid described as dark. It never names a backdrop
  colour (except `#00FF00` to force the green key on a pink subject), never says
  "transparent background" and never gives a pixel size (the model cannot; fitting to
  `size` is processing). Later animation frames are drawn from the first frame.
- **Edges (`alpha`)**: a cut-out's edge is binary by default: `art.py process` makes every pixel fully
  opaque or fully transparent and `qa` fails semi-transparent pixels (crisp pixel art, no dark halo).
  `"alpha": "soft"` on a palette sprite with `flags.alpha` keeps anti-aliased or translucent edges (a
  glow, smoke, a soft shadow, a modded game's original art whose edges were soft); the packer stores
  them in the alpha palette. Not for `color: "full"` (no transparency at all).
- **Carried-through sprites (`keep`)**: `"keep": true` marks a finished sprite that is never drawn or
  reprocessed, normally a modded game's own art extracted by `scripts/extract_art.py` (Mod mode). It
  needs no `gen_prompt` and costs no image; `art.py gen` skips it, `art.py process` copies its original
  (`assets_<game>/original/<name>.png`) byte for byte into `art/`, and `art.py qa` checks only its size,
  that it is a PNG and that it is still the original (an edited "kept" sprite fails: drop `keep` and it
  is checked like drawn art). A manifest written by `extract_art.py` carries `_origin` and needs no
  `launcher_icon` entry (the game's packed icon is `assets_<game>/icon.png`). Packing such a manifest
  re-encodes nothing that is unchanged: a sprite whose PNG still shows the extracted pixels and whose
  entry keeps its size, colour, flags and pivot is written back from its original record byte for byte
  (palette, flags, compression; `scripts/carry_art.py`), so changing an entry's flags re-encodes it.
  A kept sprite may carry the game's own (upper-case) name.
- **Across faces**: scenery that spans faces is one panorama split per screen,
  continuous and upright around the four side faces; unique objects (sun, moon)
  appear exactly once on the cube.
- **Animation from video** (optional): only when the user named an image-to-video service at setup
  (`art.animation: "video"`) or asks for it, the profile's `data_policy.may_leave_machine` contains
  `animation_frames` (the base picture and the motion description go to the service; never under
  `may_leave_machine: []`), its connector's tools are in the session and they agreed to the quoted
  credits once for this run. Then looping idles, walk/run cycles and short in-place actions are
  animated from the approved first frame and cut with `scripts/video_to_frames.py`; the frames get
  `"fit": "canvas"` and the same `process` / `qa` / review. A video job counts in the image budget as the
  frames it replaces: `art.py budget M --video <anim> --quote` (checks it fits, records nothing), the
  user's yes to the quoted credits, then `art.py budget M --video <anim> --credits <C>` once, right before
  the job is submitted (`--drop` for a recorded job that was never submitted). The service's own image
  models draw a base picture only when the user named it as their picture tool too, its GPT image model
  never when the user has ChatGPT. `cube_art-director/references/ANIMATION_VIDEO.md`.
- **Animation**: 20 fps is the hardware cap; there is no pack-size or clip-length
  budget (many frames, even video sequences, are fine). "One animated full-screen
  (fullsize) picture per physical module" is a guideline (unconfirmed), informational
  only: mention it, never block or send the manifest back for it.
- **Sounds**: one entry per event moment plus a music loop (unless the GDD explicitly
  says "no music"), same naming rules.
- **Launcher icon**: one sprite `launcher_icon` (`icon` is reserved), `[160, 160]`,
  `color: "palette"` + `flags.fullsize`, `background: "key"`: a square picture in the
  game's style, cut into the launcher's standard hexagon by `scripts/icon_badge.py make`
  (never a drawn hexagon: it comes out bigger or smaller than every other icon). The **packed** tier comes from
  the manifest's top-level `icon` object: the default (full colour, 160) is RAW565, so
  the corners render black on the dark launcher; transparent corners need
  `"icon": {"color": "palette", "side": 120}` (drawn ×2) or `240` (fullsize). Details:
  `cube_asset-builder/references/ART.md` "Launcher icon".

## 2. Style lock: the one creative checkpoint

Runs in every mode. Only an explicit user waiver ("skip the style approval") or the
`YOLO` token skips the user's approval. The source comes from the profile (`art.source`): Codex
art, the user's own art (§8), PSDs from an artist (§9), the procedural style (below) or a provider;
*(stepwise)* ask only when the profile leaves it open.

**Procedural style** (`art.source: procedural`): the agent draws every sprite in code (Pillow) in one
deliberate style written into STYLE.md like any other (flat shapes, clean outlines of a fixed width, a
palette of 8-16 named colours, simple shading rules). It is a final style, not placeholders: it goes
through the style lock (the frame and the mock), `art.py process`, `qa` and the review like generated
art, and the report says it was drawn in code on purpose. Nothing leaves the machine.

**Procedural steps P1-P5** (they replace `candidates`, `gen` and `build_pipeline.py generate`, which would look for
Codex or a provider; everything else in §2-§3 applies unchanged). They apply to the procedural style
only; the style-lock steps 1-6 below apply to every source (for the procedural style, step 2's
"style frames" are P5's leaders):

- P1. **One script**, `assets_<game>/procedural/draw.py`: reads the manifest, one function per family,
   the STYLE.md palette as named constants, rerunnable (`python assets_<game>/procedural/draw.py
   plans/<game>_assets.json [names...]`). A fix is a change to the script, recorded in `fixes.json` as
   a note, then a rerun; never a hand edit of a PNG.
- P2. **Output**: `assets_<game>/raw/<name>.png` for every sprite (never `art/`: `process` writes `art/`).
   `background: "key"` sprites: RGBA on a **transparent** canvas (no key colour), the manifest's aspect,
   4-8x its `size` (supersampled; `process` box-downscales, binary alpha by default). `background:
   "opaque"` sprites: a full RGB picture at the manifest's aspect. Never an exact-size drawing without
   `"fit": "canvas"`: the default fit crops to the object and scales it up to fill the frame. (Mod mode's
   edited originals are the exception: edited at their exact size with `"fit": "canvas"`, cube_orchestrator
   SKILL.md, "Raw images for `process`".)
- P3. **Animations**: draw every frame of one animation on the same canvas size with the subject's
   anchor at the same place. Frames whose geometry is the content (a draining timer ring, a progress
   bar, a growing burst) need `"fit": "canvas"` in the manifest (or `@fixed_canvas` in `fixes.json`):
   `process` then scales the whole canvas as drawn. Without it frames are cropped, rescaled to one
   shared scale and centred on their centre of mass (`@pose_exempt` only relaxes the QA numbers).
- P4. `art.py process M` → `assets_<game>/art/`. It records the backdrop decision of every keyed raw in
   `raw/keys.json` (`none` for a transparent drawing, else the key colour) and `art.py qa M` checks
   the same key. Never write `keys.json` by hand unless a raw really is on `#FF00FF` / `#00FF00`.
- P5. Style lock: the leaders drawn by the script are the style frames; the mock as usual; then
   `art.py anchor M --only <leaders>` and `art.py style M`. Images cost no budget.
- P0 (before P1-P5, when the user gave no style reference of their own): **two or three directions**.
   The user is never asked about the look in words up front, so the style stop must offer a real choice,
   not one finished look to approve (two real runs: the agent picked the style alone and showed only it,
   and the tester's note was "it never asked me about the graphics style"). Draw the hero and one
   playfield piece in 2-3 clearly different directions that all fit the GDD's Art Style (e.g. flat with
   thick outlines / soft shaded with no outline / pixel art at the sprite's real size; or three palettes
   with different moods), each as a small one-screen mock, into `assets_<game>/style/directions.png`
   side by side, labelled A, B, C with a 3-6 word name each. Cheap: one function per direction in a
   throw-away script under `.agent_scratch/`. The chosen one becomes STYLE.md and P1's script.

**Style-lock steps 1-6** (every source):

1. **Style bible.** Copy `<skills>/skills/cube_art-director/references/STYLE_TEMPLATE.md`
   to `assets_<game>/style/STYLE.md` and fill it from the GDD's art direction and any
   references the user gave (references in `<ws>/refs/`, their drawings in
   `<ws>/drawn/`). Its `## Prompt block` is injected into every prompt.
2. **Style frames.** With references: `art.py candidates <manifest> --subject "<a representative scene of this game>" --n 3`.
   Without: draw the family leaders (the hero, the main backdrop, one prop or UI
   piece) with `art.py gen <manifest> --only <leaders>`, then
   `art.py process <manifest> --only <leaders>` and `art.py qa <manifest> --only <leaders>`.
   A leader whose set-mates have no raw image yet is fitted on its own and `process`
   prints `partial set: refit when the family is complete`: expected here; the whole
   set is refitted at one shared scale once the family is drawn (§3). `candidates` and
   `gen` need Codex; without it see the fallbacks at the end of §3.
3. **In-game mock at cube resolution.** Compose one face (four 240×240 screens with
   the 18 px gaps) from the leaders exactly as the game will draw them: palette
   sprites scaled ×2 nearest-neighbour, fullsize ones 1:1, a HUD line. Save it as
   `assets_<game>/style/mock.png` (a few lines of Pillow).
4. **Sound list** (§4.1) prepared at the same time, so the user answers once: only when the user chose
   real recordings (`sound.source: cc0`); synthesized sound (the default) has no list.
5. **Show the user, one short message**: the style frame(s), the mock, the one-line
   style summary from STYLE.md, and (recordings only) the sound list with licences and sizes. Ask which
   frame, what to change, and (recordings only) whether to download the sounds. Iterate until the style is
   approved; corrections go into STYLE.md. With no reference from the user (P0, and `candidates --n 3`
   for generated art), this is a **choice**, not a yes/no: one question with the directions as options
   (A, B, C by their names, "something else: describe it") on `directions.png`; then draw the chosen
   direction's leaders and mock and confirm them in the same stop ("This is direction B on the whole
   face: lock it, or change something?"). The autonomous run's style stop is still one stop: the choice
   and its confirmation are its two questions.
6. **Lock it.** First re-read STYLE.md against the approved frame, rule by rule (outline,
   tone steps, light, palette roles, Do/Don't): where they disagree, rewrite STYLE.md and its
   Prompt block (and the manifest's `_style`, rerun `validate`) to describe the approved frame,
   or redraw the frame; never lock an anchor that contradicts the bible (a real run did: every
   later asset was held to both, and reviewers kept flagging majors no redraw could fix). Colours
   a legitimate variant uses besides the anchors' (other ship or team colours) go under
   `## Variant colours` in STYLE.md (hex + role) before `style` runs.
   Put the approved images into `assets_<game>/style/anchors/` (generated
   assets: `art.py anchor <manifest> --only <names>`), run `art.py style <manifest>`
   (profile + palette swatch), record in the context:
   `"style_lock": {"status": "approved", "anchors": [...], "date": "..."}` (shape:
   `AGENT_BRIEFS.md`, "Context file").
   One profile covers the whole set, so anchor one leader of **every** family together.
   Anchoring a single family (the stone pad) made every other family fail the measured
   palette score when STYLE.md gives each family its own colour role (gold basket, cyan
   orb). With all leaders anchored, `style` may warn that the anchors "may not be one
   style": expected for deliberate colour roles; the thresholds widen to cover them
   (capped at 2x). A colour variant of an anchored object (the blue ship next to the red one)
   is declared under STYLE.md's `## Variant colours`, not exempted: its palette is then measured
   like the rest. Only an object that leaves the style on purpose (a logo, a photographic
   backdrop) goes to `@style_exempt` + "Approved exceptions".

Before the lock nothing can be measured (`art.py qa` reports style as UNCHECKED until `art.py style` has a
profile): the style frames are judged by eye against STYLE.md, the GDD's Art Style and the mock.
Waiver: dispatch a fresh reviewer (§10, style-frame variant) on the candidates against STYLE.md, lock the
best one, record `"status": "waived"`; the final report says the user did not approve
the style. User-supplied art: `"status": "user_art"` (their art is the lock).

## 3. Generate and review (strict)

Through `cube_asset-builder`:

1. **Family leaders first**: one asset per family (character, prop group, UI kit,
   effects): `gen --only <leader>`, `process --only <leader>` (the partial-set warning
   above is expected), `qa --only <leader>`, look, fix, then
   `art.py anchor <manifest> --only <leader>`. The rest of the family uses the leader as
   `subject_ref` and is held to the grown profile.
2. **The batch**: `python <skills>/scripts/build_pipeline.py generate --manifest <manifest>
   --workspace assets_<game> --jobs 3`, then `art.py qa <manifest>` and `art.py review <manifest>`.
   `generate` first gives every later animation frame a subject reference to its first frame in
   `fixes.json`, then runs `art.py gen` and `art.py process` and writes placeholder sounds for
   sounds not built yet (`cube_asset-builder` Step 3). Its `process` refits every now-complete set
   at one shared scale, leaders included: look at the leaders again in `qa/sets.png` (the anchors
   keep the approved look). Redraw rounds after it call art.py directly (step 3); `art.py all`
   (gen, process, qa, review) is the shortcut for one.
3. **The loop**, for every batch: look at three views of each asset (raw output, final
   ×4, in context at device scale) plus `assets_<game>/qa/sets.png` and the set GIFs.
   Every numeric FAIL (`style`, `fill`, `set_centroid` / `set_area` / `set_height` /
   `set_colour`) is a question answered by the picture: real -> fix; false (a back view
   no anchor shows, two different monsters in one `set`, a squash frame, a broken brick
   that should not fill its cell) -> `art.py waive <manifest> --only <asset> --check <id>
   --reason "<what the picture shows>"`: `qa` reports `WAIVED`, does not count it, and
   drops the waiver when the image changes (cube_art-director `references/QA_RULES.md`).
   Never add anchors, split sets or drop rules only to silence a check (a QA run spent
   ~25 min doing that, and removing one anchor broke the palette check of every yellow
   sprite). Technical checks (size, cut-out, key, alpha, opaque, missing, empty, kept-file) cannot be waived.
   Every real FAIL gets a cause-level fix (a prompt line in `fixes.json`, a better subject
   reference, the green key, `fill`; exemptions only for intended changes) and a redraw
   of what failed plus the set partners that must match. A correction of the **look**
   (outline, shading, palette, light) edits where the look is written: the asset's
   `gen_prompt` in the manifest (then `validate`) or STYLE.md's rules and Prompt block (plus
   `_style`) for every asset. A `fixes.json` note is only appended to the prompt and never
   overrides contradicting words in it; `art.py gen` warns when a note rules out something
   the prompt still asks for (QA_RULES.md S6):
   `art.py gen <manifest> --only <names> --force`, then `process` and `qa`.
   **Repeat until every rule in QA_RULES.md passes or is waived** (`art.py qa` clean: every
   numeric FAIL fixed or, after a look at the picture, waived as false with `art.py waive`; no critical or
   major reviewer finding open; minors follow the §10 exit rule). There is no "accept
   after N rounds" for hard failures. Escalate only when a rule genuinely cannot be met, saying what was tried:
   *(stepwise)* ask the user; autonomous: simplify the asset within its manifest entry
   (same name and size: fewer distinct poses, a simpler subject; rerun `validate` after the
   edit) and list it in the
   final report.
   **A budget ends the redraws, not the rules.** The art is capped by `art_budget:
   {"images": N, "minutes": M}` in the context: the profile's `budget.images`, else the tier's
   default (`lite` 30, `standard` 80, `full` 200; `references/RUN_MODES.md`). The tools count it:
   every Codex request (each attempt of a sprite, each panorama picture, each style candidate) and
   every paid-provider call is recorded before it is made in `context/<game>_images.json` and
   mirrored into the context's `spend.images_used` (`cube_art-director/scripts/art_budget.py`);
   `art.py gen` / `candidates` and `build_pipeline.py generate` print `spent / budget` and refuse a run
   that does not fit in what is left (art.py exit 4, nothing drawn). `art.py budget <manifest>` prints
   the state; `--over-budget` draws past it only on the user's explicit yes. The procedural style and
   the user's own art cost none. Once it is spent: no more
   redraws; fix what processing can fix (`process` options, `@post`), then accept each
   real style or set FAIL still left **under budget**, a path distinct from waiving a false FAIL:
   per asset with `art.py waive <manifest> --only <asset> --check <id> --under-budget --reason
   "accepted under budget: <the finding>"` (recorded as `accepted_under_budget`, apart from waivers), or for a
   whole class with `fixes.json` `@style_exempt` / `@colour_exempt` / `@pose_exempt` / `@fill`
   (plus the line under "Approved exceptions" in STYLE.md, with the finding). This is the **one
   sanctioned exception** to "never drop rules to silence a check" above: only once the image budget
   is spent, and every one with a recorded finding in the context's `accepted_under_budget`
   (`AGENT_BRIEFS.md`, "Context file"), listed in the final report apart from the false FAILs waived
   after a look; then pack and go on to Stage 4 (a spent image budget never stops the
  run, `RUN_MODES.md` failure policy 3). A hard failure no key waives (wrong size, key colour left,
   an empty frame) is a processing problem: fix it with `process`; if one remains, Stage 3
   is not done (*(stepwise)* ask; autonomous: report it and stop before packing). On a real run three
   fresh reviews of 9 sprites took ~42 min and ~580k tokens, longer than all the drawing (about
   12–15 min per review; `RUN_MODES.md`, "Estimate", counts them in every row): say so when the user
   sets a tight cap.
4. **Fresh-agent consistency review** (§10) before anyone sees the batch; its findings
   go through the same loop. A read-only Codex pass (`cube_art-director/references/CODEX.md`)
   is a useful second opinion when you and the reviewer disagree.
5. **Review page**: `art.py review <manifest>` writes `assets_<game>/review.html`.
   *(stepwise)* The user marks OK / Fix and presses "Copy feedback"; save it to a file,
   run `art.py feedback <manifest> --file <fb.json>` (notes become `fixes.json`
   entries), redraw, re-review until all OK. Autonomous: link the page in the final
   report.

**Fallbacks**, only when Codex cannot draw:
- by default, the procedural style (agent-drawn in code, final quality) (above): a deliberate style that goes through the same
  style lock, QA and review as generated art; the report says, in plain words, that the pictures were
  drawn in code on purpose and that signing in to ChatGPT's drawing tool brings generated pictures if
  wanted (the command, `codex login`, only when the user asks how). Temporary placeholders only when the profile
  says `art.source: placeholder`;
- a paid image API only when the user, in this run, explicitly asked for it and agreed to the quoted
  cost, asked once per run (`--allow-paid`; a configured key is not consent; autonomous and `YOLO` never imply it,
  `RUN_MODES.md`): `build_pipeline.py generate` draws every sprite
  with it (`scripts/image_providers.py`). `art.py candidates` and `art.py gen` call Codex
  directly and are not available; what still works on the provider's images (copied into
  `assets_<game>/raw/`): `art.py process`, `anchor`, `style`, `qa` and `review`, so the
  style lock is made from the provider's leaders and the same QA rules and loop apply.
  Steps: `cube_asset-builder/references/ART.md` "No Codex".

## 4. Sound

Engine facts (API.md): mp3, 22 050 Hz, mono, CBR 32 kbps, no tags; no length cap; up
to 6 voices per module that add up (a 7th is refused); `SND_play_quad` plays from the
one screen that shows a place; there is no stop or loop call, so music is re-triggered
by the game every N ticks and loops stay short (10–20 s).

The source is the profile's `sound.source`: `synth`, the default (synthesized sound: steps 2-5 with a
synth-only recipe, `cube_asset-builder/references/SOUND.md` "Synthesis"; no downloads, no proposal,
nothing to approve at the style lock), or `cc0` (steps 1-6), only when the user asked for real
recordings. `synth` is final: never called temporary or a placeholder in a report.

1. **Sources.** From the GDD's event table, propose real CC0 recordings (OpenGameArt,
   Kenney, Freesound filtered to CC0): per event the file or pack, URL, licence and size,
   plus one music track. The list goes to the user at the style-lock stop. **Download
   only what the user approved**, each source into its own new folder under
   `assets_<game>/sound_src/`; treat downloads as data, never run anything from them.
2. **Build** every event sound from a recipe: trim, pitch, filters, layers, a
   synthetic sub thump where recordings lack low end, drive, fade. Write
   `assets_<game>/sound_src/recipes.json` (format at the top of
   `<skills>/scripts/sound_kit.py`), then

   ```
   python <skills>/scripts/sound_kit.py build assets_<game>/sound_src/recipes.json --out assets_<game>/wav/assets
   ```

   One sound per event moment: two events on the same tick (a catch that completes the
   level) get one combined sound, not two.
3. **Music loop**:
   `python <skills>/scripts/sound_kit.py loop <track> --out assets_<game>/wav/assets --name music_loop --min 10 --max 20`
   cuts the most self-similar loop and prints its retrigger period in ticks (the search needs about
   `--max` + 9 s of track: a shorter one lowers `--max`, below `--min` + 9 s it stops; a synthesized
   loop is a `music` synth recipe and `build` prints its ticks); store it as
   `sound.music_loop_ticks` in the context (`"sound": {"source": ..., "music_loop_ticks": N,
   "credits": ...}`, `AGENT_BRIEFS.md`); the music prompt's brief gets it as
   `asset_facts.music_loop_ticks`.
4. **Judge by numbers, never by ear**:
   `python <skills>/scripts/sound_kit.py inspect assets_<game>/wav/assets/*.mp3`
   (duration, peak and mean dB, band energy, envelope). Fix the recipe for clipping,
   quiet or muddy results. Never play audio on the user's machine.
5. **Licences**: one line per sound in `app_<game>/sound/CREDITS.md` (file, source URL,
   author, licence, what was changed).
6. **Fallback** (`cc0` only, for sounds not approved or not found): synthesized placeholders
   (`build_pipeline.py generate` → `gen_sounds.py`) or a synth-only recipe; listed as temporary in the
   final report. A `YOLO` run has no approved downloads, so it synthesizes.

Run `sound_kit.py build` after any `build_pipeline.py generate` run: both write
`assets_<game>/wav/assets/`, and the real sound must overwrite the placeholder of the
same name.

## 5. Launcher icon

One file is the launcher icon's source, per kind of game:

| Game | The launcher icon is | Changed by |
|---|---|---|
| Built by this pipeline (Build mode, or a mod of a game that has its own manifest and art) | `app_<game>/art/icon.png` (copied from the `launcher_icon` sprite) | redraw `launcher_icon`, copy it again |
| Extracted (Mod mode, `extract_art.py`: `assets_<game>/extracted.json` exists) | `assets_<game>/icon.png`: the packed `ico_idle` as it ships, carried through byte for byte while unchanged | editing or replacing that PNG (square; packed at the manifest's `icon` tier) |

In an extracted game `app_<game>/art/icon.png` (a source the app folder happened to carry) and a sprite named
`launcher_icon` in `assets_<game>/art/` (an in-game sprite record of the original pipeline) are **not** the launcher
icon: `repack_app.py` and `build_pipeline.py pack` take `assets_<game>/icon.png` and print which file they used.

- Generated with the set (the manifest entry from §1) and held to the same QA.
- Copy `assets_<game>/art/<icon entry>.png` to `app_<game>/art/icon.png`; the pack gets
  `--icon app_<game>/art/icon.png`. The pack warns when the template icon would ship;
  that warning blocks delivery.
- The PNG's transparent corners survive only with a palette `icon` tier (120 or 240,
  §1); with the default full-colour icon they render black on the launcher.
- Stage 5 checks that the `.oct` carries the `ico` map the launcher looks for.

## 6. Fonts

- The template's `font_1..3` (BMFont binary v3 + `font_<n>_0.png`, in `app_<game>/art/`)
  cover ASCII. Every pack syncs them into `assets_<game>/fonts/` (a changed `.fnt` or
  atlas is copied again, stale pages are replaced) and fails when `_ids.h` lacks the
  `font_` glyphs (every label would draw nothing).
- Another font only when the GDD asks: BMFont binary v3, one page, ASCII 0x20–0x7F,
  `font_<n>.fnt` + `font_<n>_0.png` (n = 1..3) in `app_<game>/art/`.

## 7. Pack

The repo's python packer packs the AI-manifest path (it reproduced a shipped game's
pack byte for byte, and it understands the manifest tiers). From `<ws>`:

```
python <skills>/scripts/build_pipeline.py pack --game <game> --workspace assets_<game> --src-dir app_<game>/src --app-dir app_<game> --manifest plans/<game>_assets.json --icon app_<game>/art/icon.png
```

Before writing anything it refuses an incomplete set: every manifest sprite needs
`assets_<game>/art/<name>.png` and every manifest sound an mp3 in
`assets_<game>/wav/assets/` or `app_<game>/sound/assets/` (it names what is missing).
It then clears its intermediates (`assets_<game>/packed/`, `assets_<game>/exported/`),
so frames retired from the manifest cannot linger in the pack, syncs the fonts (§6), and
writes `app_<game>/index.bin`, `art/packed/*.raw` + `*.pal`, `sound/assets/*.mp3`,
`src/app_<game>_ids.h` (record index = asset id; `BMP_`/`MAP_`/`SND_` enums) and
`app_<game>/.pack_inputs.json` (sha1 of the manifest, every input PNG and mp3, the fonts
and the icon). PNGs of sprites no longer in the manifest are still atlased from
`assets_<game>/art/`: move them out (e.g. to `assets_<game>/retired/`) before packing.

Accept it when: exit code 0, no template-icon warning, `BMP_<name>` for every manifest
sprite, `font_` entries present, and

```
python <skills>/scripts/build_pipeline.py pack-status --game <game> --workspace assets_<game> --app-dir app_<game> --manifest plans/<game>_assets.json
```

exits 0 (1 = an input changed after the pack, or no record: pack again). Stage
detection and delivery use the same check. Never hand-edit `_ids.h`. Then the Stage 3→4
boundary (stepwise: asset counts, then wait).

## 8. The user's own art (Path B)

Hand the user the exact spec from the manifest: `<name>.png`, exact size, RGBA with
transparency unless the sprite is opaque (`color: "full"`), complete frame sets, the
GDD style; files go to `assets_<game>/art/`. Sounds (`.wav` / `.mp3`) go to
`assets_<game>/sound_src/` and through `sound_kit.py build`. `0.png` is made by the
pipeline, never by the user.

**Completeness check, every mode**: list every missing file by name and size (the
pack refuses an incomplete set anyway, §7). *(stepwise)* Wait for them. Autonomous: fill the
gaps only as the profile's `data_policy` allows. With `prompts` and `reference_images` in
`may_leave_machine`, through the Codex path (or the chosen provider) with the user's art as the
anchors, and report it. Otherwise nothing is sent: draw the gaps on this machine (a local Stable
Diffusion, or the procedural style when the user's art is simple enough to match), or save, list
the missing files and stop for the user (`scripts/image_providers.py` refuses a cloud provider and
Codex under `may_leave_machine: []`).
Run `art.py qa <manifest>` on the delivered files (size, key, alpha) and report
problems before packing (§7).

## 9. PSD-authored art (artists in Photoshop)

**External users (this kit alone):** export the PSD's layers to PNG (Photoshop: File > Export > Layers to Files, one PNG per sprite, named as in the manifest) and use the manifest path (§8, the user's own art): the PNGs go into
`assets_<game>/art/`, and `art.py qa` and `build_pipeline.py pack` treat them like any other art. Keep the
PSDs as the artist's sources; re-export after every change.

**Internal SDK only:** WowCube developers with an SDK checkout can pack PSDs with the SDK's official
packer (octpacker; not part of this kit: it needs a developer's SDK checkout and `uv`) instead of the
manifest path:
`app_<game>/art/octpack.json` lists the inputs (`assets` PSDs, `maps`, `fonts`, `raw`
PNG folders), `art/!pack.txt` assigns palette groups and flags (`<FULLSIZE>`,
`<ALPHA>`, `<ARGB>`, `<SOFTKEY>`, `<HALF>`); pack with
`<skills>/scripts/repack_app.py --app-dir app_<game> --octavios <SDK checkout>`, which sees
`art/octpack.json` first and runs the SDK's `octpack-pack`. Stage 5 then builds with
`build_device -Builder octpack -OctaviOS <SDK checkout>`. There is no adapter from
our manifest to octpack yet (open item); do not mix both paths in one app. Stage 3 is done when
the same `build_pipeline.py pack-status` exits 0: for such an app it checks that `index.bin` is newer
than `octpack.json`, `!pack.txt` and every input it names (no `.pack_inputs.json` is written).

## 10. Consistency reviewer (fresh subagent)

**Style-frame variant (before the lock; used for a waived lock).** Inputs: STYLE.md, the GDD's Art Style section,
the candidates (raw + final), the in-game mock. Task: pick the candidate that best fits STYLE.md and the GDD, list
what must change before it can anchor the style, or reject all. Output JSON:
`{"task": "style_frame_approval", "verdict": "approve|revise|reject", "anchors": ["<file>"], "findings": [...]}`.
The batch variant below needs anchors and `qa/sets.png`, which exist only after the lock.

Dispatched with the Agent tool. Give it the files, not your conclusions.

**Mod mode with the game's own art** (`art.source: original`): there is no STYLE.md. The brief replaces
`"style_bible"` with `"style_reference": "kept originals: the anchors in anchors_dir (art.py anchor --originals)
and every sprite in <ws>/assets_<game>/original/"`, and rule 1 reads "look at the anchors and the originals; they
are the style". The reviewer judges only the new or changed sprites (the manifest entries without `keep`); kept
sprites are the game's own and never findings.

```
You are an independent art reviewer for a WowCube game. You never generate or edit
images; you inspect and report.

<Safety block from references/AGENT_BRIEFS.md>

## Task
{"task": "asset_consistency", "game": "<game>",
 "style_bible": "<ws>/assets_<game>/style/STYLE.md",
 "anchors_dir": "<ws>/assets_<game>/style/anchors",
 "rules": "<skills>/skills/cube_art-director/references/QA_RULES.md",
 "sets_sheet": "<ws>/assets_<game>/qa/sets.png (only when the manifest has sets)",
 "all_sheet": "<ws>/assets_<game>/qa/all.png",
 "art_dir": "<ws>/assets_<game>/art",
 "manifest": "<ws>/plans/<game>_assets.json",
 "gdd": "<ws>/plans/<game>_gdd.md"}

## Rules
1. Read STYLE.md and QA_RULES.md, look at every anchor, then judge every asset and
   every set against them. Form your own view; no earlier verdicts are given to you.
2. Check rules S0-S6, A1-A8, B1-B7, plus the cube rules: panoramas continuous across
   the side faces, unique objects once, everything readable at device scale.
   Judge only the manifest's sprites: `art/0.png` (1x1, transparent) is the packer's
   slot-0 placeholder that `art.py process` writes, not an asset and never a finding.
3. Be specific: asset, rule id, what is wrong, what would fix it. Severity: critical
   (unusable: wrong subject, unreadable, broken cut-out), major (breaks a rule a player
   sees: off-style, scale pump, wrong family colours), minor (polish: a slightly thick
   rim, a detail a player cannot see at device scale).
4. Return only this JSON:
{"agent": "asset_consistency", "status": "pass|fail",
 "findings": [{"asset": "hero_walk_02", "rule": "B2", "severity": "critical|major|minor",
               "description": "...", "fix": "..."}],
 "summary": "one sentence"}
```

**Exit rule.** `fail` with a critical or major finding: fix through the §3 loop, then
dispatch a new reviewer (fresh, not the same one) on the redrawn set. Minor-only
findings: fix the cheap ones (a `fixes.json` line plus one redraw, a `process` option),
record the rest in the context (`accepted_minors: [{"asset", "finding"}]`, named in the
final report) and go on: no fresh review for minors. Fresh batch reviews per Stage 3:
`lite` 1, `standard` 3, `full` 5 (a real run spent ~190k tokens on fresh reviews of
minor fixes). `art.py qa` hard failures are not reviewer findings: they always block the
pack (§3).

**When the fresh reviews are spent** and the last one still lists critical or major findings
(a real run ended its last review with three majors open), they are never fixed and
then left unchecked. One rule, in this order:

1. Fix each open critical/major through the §3 loop as usual (a redraw, a `fixes.json` line, a
   `process` option), within the image budget.
2. **Focused re-check** of those fixes, not a fresh review: one subagent (the same brief as above, so
   it never sees your verdict) gets only the open findings, the previous and the new image of each
   asset concerned (`raw` and `art`), STYLE.md and the anchors, and answers per finding:
   `{"agent": "asset_recheck", "findings": [{"asset", "rule", "severity", "status": "resolved|open",
   "note"}]}`. It judges those findings only, not the whole set, so it costs a fraction of a fresh review.
   One focused re-check per round of fixes, at most two rounds (`lite`: one; `full`: three).
3. A finding the re-check still calls open, or one with no fix left to try (the image budget is spent,
   or the rule cannot be met), is **waived on the record**: `accepted_majors: [{"asset", "finding",
   "reason": "review budget spent"}]` in the context (the one shape, `AGENT_BRIEFS.md` "Context file") (criticals are never waived: an unusable asset
   blocks the pack, §3 "Escalate"). The final report lists every waived major with the asset's path,
   and a stepwise run shows them to the user before the pack.

Minors after the cap are fixed if cheap, else recorded as `accepted_minors`. The report says the
review budget ended the loop.
