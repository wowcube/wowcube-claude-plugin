---
name: cube_art-director
description: "Style-locked art production with Codex for artists and art leads: the artist draws or gives a style reference, Claude writes the style bible with them, generates the assets through the local Codex CLI (ChatGPT subscription, no API key), and acts as a strict art director that measures and rejects every deviation from the artist's style until the set is consistent. Use when an artist or designer wants sprites, icons, tiles, backgrounds or animation frames generated in THEIR style: \"generate assets in my style\", \"here is my reference, make the rest\", \"keep the style consistent\", \"draw the walk cycle from my sketch\", \"art director\", \"assets from my reference\" (in any language). Standalone (works outside any game pipeline); cube_asset-builder also uses it as its Codex generation path."
---

# Art director: style-locked generation with Codex

The artist owns the style. Claude's job is to turn their references into an
explicit, checkable style lock, drive Codex to draw the assets, and refuse
everything that drifts from that lock, so the artist spends their time on
taste decisions instead of catching inconsistencies.

`<skills>` = the folder two levels above this SKILL.md (the plugin root; `${CLAUDE_PLUGIN_ROOT}` when the host exports it); resolve it on every entry, never store it. The tool below is
`<skills>/skills/cube_art-director/scripts/art.py`.

```
artist refs / drawings ──► style bible (STYLE.md) + anchors ──► profile.json (measured)
                                        │
asset list ──► Codex draws (anchors + subject refs attached) ──► key + fit ──► QA (numbers + eyes)
                                        ▲                                         │ fail
                                        └──────── fixes.json (every correction) ◄─┘
                                                                                  │ pass
                                     review.html ──► artist: OK / Fix + notes ──► anchors grow
```

## Ground rules

- **The artist's references are the law.** Never "improve" the style on your own; propose changes, the artist decides. Every accepted departure is written under "Approved exceptions" in STYLE.md.
- **Strict reviewer.** An asset that breaks a rule in `references/QA_RULES.md` is a FAIL even if it "basically works". Iterate (prompt, references, processing) until it passes or a look at the picture shows the FAIL is false (then `art.py waive` it with a one-line reason, step 5); escalate only when a rule truly cannot be met, saying what was tried. Never show the artist a batch that fails QA. A real FAIL left when the image budget is spent is recorded as accepted under budget (`waive --under-budget`, `references/QA_RULES.md`), never as a waiver.
- **Codex on the subscription, strongest listed model, high reasoning effort by default** (maximum effort only when the user asks: `ART_CODEX_EFFORT=max`; `references/CODEX.md`). Never ask for API keys. Another image tool only when the user said they have it ("Art only" below): a paid one with their one yes per run to the quoted cost (asked once, never per batch), a local model freely; otherwise the art is drawn in code.
- **Everything reproducible**: prompts in the spec, corrections in `fixes.json`, anchors in `style/anchors/`. A regeneration must reproduce every fix without the chat history.
- The artist does not need to touch a terminal: Claude runs every command and shows the results (review page, sheets).
- **Sizes are the art director's job**, and they never wait for a game design: "what size should my
  sprites be?" is answered at once from `references/SIZES.md` (the 240x240 screen, the 2x rule, typical
  sizes per role, colors, how sheets are handed over). Every asset's size is checked against its role with
  `art.py sizes <spec>` before anything is drawn, and `qa` flags it again.
- **Animation from video (optional, opt-in)**: when the user named an image-to-video service ("I have
  Higgsfield": `profile.art.animation: "video"`) or asks for it, its connector's tools are in this session
  and they agreed to the quoted credits once for this run, looping idles, walk/run cycles and short actions
  are animated from one approved picture and cut into frames with `<skills>/scripts/video_to_frames.py`;
  otherwise every frame is drawn as below. A connector found in the session is not consent.
  `references/ANIMATION_VIDEO.md`.
- **Data**: this pipeline trains no model on the user's art. With an outside tool the user chose (Codex,
  an image service), that provider's own data settings apply to what is sent; with their own art or art
  drawn in code nothing leaves the computer. Codex is used only when the user picked it: a login found on
  the computer is never assumed to be theirs.

## Art only (an artist who wants pictures, not a game)

Entry `art` from `wowcube-setup` ("I'm an artist, I want a sprite sheet, no code"), or any request for
art alone. No game is designed, coded or built: no simulator, no build kit, no ARM toolchain, no install
question. Python with Pillow and numpy is all it needs (`art.py doctor --no-codex`; plain `doctor` when
Codex draws). Talk about pictures only; no "manifest", "pack" or other pipeline words.

1. **Intake** (Workflow 1) with `art.py init <dir>` in the user's workspace: what they need (sprites,
   animation frames, icons, backgrounds, tiles), the sizes (for the cube straight from
   `references/SIZES.md`; another target: ask, and set `"target"` in `art.json`), their references. A
   sprite sheet they were sent is cut into named PNGs first (`art.py slice`).
2. **How the pictures are made** comes from what the user said they have (`profile.resources`,
   `scripts/profile_provider.py` `art_routes`), never from what detection found:
   - *Codex* (they have ChatGPT): `gen` as in the Workflow;
   - *their image tool* (Gemini, an OpenAI/xAI/OpenRouter key, a local Stable Diffusion): one picture per
     asset with `python <skills>/scripts/genimg.py "<style block + the asset's prompt>" -o <ws>/raw/<name>.png`
     (no `-s`: `process` fits it), `--allow-paid` only after their yes to paying, asked ONCE for the run
     with the quoted cost of all its pictures (never per batch; ask again only when the run needs more than
     they agreed to; a local model is free); then the same `process`, `qa`, `review`;
   - *their own art*: `"source": "drawn/<file>.png"` per asset (copied, keyed, fitted, checked);
   - *drawn in code* (always possible): a script in the workspace writes `raw/<name>.png` for every asset,
     4-8x the size, transparent canvas for cut-outs (`cube_orchestrator/references/STAGE3_ASSETS.md` §2,
     "Procedural style"; the same steps with `art.json` instead of a manifest).
3. **Style lock, families, review** exactly as in the Workflow (2-6); the user approves as the artist.
   Guidance *Just show me results*: they see the style frame (with the bible's one-line summary) and the
   finished set; family leaders go to a fresh reviewer instead. The guidance answer sets the picture
   budget (`"budget": {"images": N}` in `art.json`) and the fresh reviews: *On my own* / *Just show me
   results* 30 pictures and 1 review, *Step by step* 200 and 5 (an explicit `standard` request: 80 and 3).
4. **Delivery**: the exact-size PNGs in `<ws>/art_work/final/`, a sprite sheet and its atlas
   (`art.py sheet art.json`, one per set with `--set <set>` when they want one per animation), the QA
   sheet and the review page. On request, a cube-ready asset set: write a WowCube manifest for the same
   assets and pack them (`cube_asset-builder` Step 9, "Pack", into an app folder made with
   `scripts/new_app.ps1 -SkipBuild -SkipEnvCheck` / `new_app.sh --skip-build --skip-env-check`: scaffold and
   pack only, so no build components are needed).
   Report: absolute paths, sizes, how many pictures were drawn against the budget, and what was drawn in
   code on purpose.

## Who approves (standalone vs inside the WowCube pipeline)

- **Standalone** (an artist or art lead drives it): every approval in the workflow below is theirs: the style bible (2), the style frame (3), each family leader (4), the review page (6).
- **Inside the WowCube pipeline** (`cube_asset-builder`, driven by `cube_orchestrator`), **autonomous run** (the default): the only user stop is the orchestrator's **style lock**: style frame, in-game mock, the style bible's short summary and the sound list in one message (`cube_orchestrator/references/STAGE3_ASSETS.md` §2). Family leaders and every batch are approved by the independent fresh-agent reviewer (5, step 5), never by stopping for the user; the review page is linked in the final report. An explicit waiver or the `YOLO` token lets that reviewer approve the style frame too.
- **Inside the pipeline, stepwise run**: the user takes the artist's role at every approval.

## Tool

`scripts/art.py` (Python 3.11+ with `<skills>/scripts/requirements.txt`: `pip install -r <skills>/scripts/requirements.txt`, in a venv on Homebrew or Debian/Ubuntu Python):

| Command | What it does |
|---|---|
| `doctor [<spec>]` | setup check: Python deps, Codex CLI found, ChatGPT login, chosen model/effort, spec valid |
| `init <dir>` | new project: `art.json`, `style/STYLE.md` (from `references/STYLE_TEMPLATE.md`), `style/anchors/`, `style/candidates/`, `refs/`, `drawn/` |
| `candidates <spec> --subject "..." [--n 3]` | first style frames BEFORE the lock: the artist's `refs/` + `drawn/` are attached as style references -> `style/candidates/` |
| `style <spec>` | measures the anchors -> `style/profile.json` + `palette.png` (palette, light range, saturation ceiling, outline). One anchor = default thresholds; 2+ anchors widen them to what the anchors need, capped at 2x the default, with a warning when the anchors look like different styles (split them into families). The hex colors under STYLE.md's `## Variant colours` are added to the measured palette (below) |
| `anchor <spec> --only a,b` | promotes approved assets to anchors and rebuilds the profile. The anchor is the asset's FINAL image (exact size: what `qa` measures, so the profile and the scores are taken at the same scale; a modded game's own sprites have no raw and anchor this way); when a raw image exists its keyed raw-resolution look is saved as `anchors/hires/<name>.png` and is what `gen` attaches for Codex (not profiled) |
| `gen <spec> [--only a,b] [--set s] [--force] [--jobs 3]` | Codex draws every asset without a raw image (anchors + subject/sketch refs attached; assets whose `subject_ref` is drawn in the same batch go second). Counts every request against the image budget and refuses (exit 4) a run that does not fit; warns when a `fixes.json` note rules out what the prompt still asks for |
| `budget <spec>` | image requests spent, the cap and where it comes from. Going past the cap is the user's call: ask them, then `--over-budget` (`--budget N` only lowers the cap for one run; above the budget it is refused unless `--over-budget` is given too) |
| `process <spec> [--only a,b]` | key out the backdrop, fit to size (binary alpha unless the asset says `alpha: soft`); `motion` sets share one scale and are centroid-aligned; `colour_lock` frames are color-matched; a `keep` asset is copied byte for byte from its original (never keyed or refitted). A set is always fitted together; while some members still have no raw image (a family leader drawn first), the members that have one are fitted together and it prints `partial set: refit when the family is complete` |
| `qa <spec> [--only a,b] [--set s]` | size, real cut-out, key, alpha, fill, set rules (scale, jitter, color lock) and the style score per asset (a `keep` asset: only size, PNG format and "still its original"); exit 1 on hard failures (every line names its check id, e.g. `[set_height]`; waived checks are not counted); sheets + per-animation GIFs in `<ws>/qa/`. Scope it to a family leader while the rest is still pending |
| `waive <spec> --only a[,b] --check <id>[,<id>] --reason "..." [--under-budget]` | a numeric FAIL a look at the picture shows is false: `qa` reports `WAIVED <asset>: <check> - <reason>` and does not count it while what was looked at is unchanged: the final image (its SHA-256 is stored), for a set check also its reference frame (waive after a `qa` run), for `style` also the style profile (the anchors). Stored in art.json `qa_waivers`, for a manifest `<ws>/qa_waivers.json`, never in `fixes.json`. Waivable: `style`, `fill`, `set_centroid`, `set_area`, `set_height`, `set_colour`; never size, cut-out, key, alpha, opaque, missing, empty or kept-file checks. `--under-budget`: a REAL failure accepted because the image budget is spent (refused while images are left; `qa` reports `ACCEPTED UNDER BUDGET`, apart from waivers). No `--only` lists them, `--drop` removes |
| `review <spec>` | `<ws>/review.html`: anchors, palette, sets with onion skin, every asset (raw, final x4, verdicts, prompt) with OK / Fix + note |
| `feedback <spec> --file fb.json` | folds the page's "Copy feedback" JSON into `fixes.json` and prints the regen command |
| `all <spec>` | gen -> process -> qa -> review |
| `sheet <spec> [--only a,b] [--set s] [--cols N] [--padding 2] [--name n]` | the finished images on one grid PNG plus a JSON atlas: `<ws>/sheet/<name>.png` + `<name>.json` (`frames`: each sprite's x, y, w, h; `animations`: one ordered list per set; the common "JSON hash" layout game engines and sheet importers read). Takes the finals `process` wrote; refuses (exit 1) when one is missing |
| `budget <spec> --video <anim> --quote`, then `budget <spec> --video <anim> [--video-frames N] [--credits C]`, `--drop` | an animation video job: `--quote` checks it fits and records nothing (exit 4 = it does not fit, do not submit); after the user's yes it is recorded ONCE, right before it is submitted, with the credits: one entry counting the frames it replaces (the spec's `<anim>_NN`, minus an approved frame 0 the clip keeps); `--drop` removes a recorded job that was never submitted (`references/ANIMATION_VIDEO.md`) |
| `doctor --no-codex` | the art is drawn in code or is the artist's own: Codex lines become notes, only Python, Pillow and numpy must be there |
| `sizes [<spec>]` | the WowCube size guide (`references/SIZES.md`); with a spec, every asset's size against its role (`role` field, else guessed from the name): half size up to 120, fullsize up to 240, the launcher icon 160, typical ranges per role; exit 1 on a size that cannot work. Skipped for an `art.json` whose `"target"` is not the cube |
| `slice <sheet.png> (--cell WxH \| --grid COLSxROWS \| --atlas a.json) [--names a,b] [--padding P] [--margin M] [--out dir]` | cuts a sprite sheet someone sent into one named PNG per sprite (reading order; empty cells skipped; default names `<sheet>_NN`, or the atlas's names), default `<sheet folder>/sliced/`; use them as drawings (`"source": "drawn/<name>.png"`). Cells touch by default (`--padding 0`; the `sheet` command's default of 2 does not apply). The reverse of `sheet` |

`<spec>` is `art.json` (format at the top of `scripts/art_spec.py`) or a
WowCube manifest `plans/<game>_assets.json` (then the workspace is
`assets_<game>/`, the style lives in `assets_<game>/style/`, and final images
land in `assets_<game>/art/` where the WowCube pack stage reads them; give
every sprite an explicit `"background": "key" | "opaque"`).

Project layout (art.json):
```
<project>/art.json            asset list + style paths
<project>/refs/  drawn/       artist references and drawings (inputs)
<project>/style/STYLE.md      style bible;  anchors/  approved anchors;  candidates/  first style frames
<project>/style/profile.json  measured style lock (+ palette.png)
<project>/art_work/raw/       model output (+ keys.json backdrop per asset, prompts.json, logs/)
<project>/art_work/final/     exact-size images (the deliverable)
<project>/art_work/qa/        report.txt/json, all.png (every final), sets.png + GIFs (sets only), provenance.json
<project>/art_work/fixes.json every correction, replayed on regeneration
<project>/art_work/review.html the artist's review page
```
Run commands from anywhere as `python <skill>/scripts/art.py <cmd> <path to art.json>`; the
commands the tool prints are copy-pasteable (interpreter, script, spec, workspace).
**Image budget.** Every Codex request is one entry in a ledger, written before the request is made:
each attempt of a sprite (a retry after "no PNG" or "at capacity" is a new request), each panorama
picture, each style candidate (`scripts/art_budget.py`). An art.json project keeps it in
`<ws>/image_ledger.json` and has no cap unless `art.json` says `"budget": {"images": N}`; inside the
WowCube pipeline it is `context/<game>_images.json`, the count is mirrored into the context's
`spend.images_used`, and the cap is the context's `art_budget.images` (else the profile's
`budget.images`, else the verification tier: lite 30, standard 80, full 200). `gen` and `candidates`
print `spent / budget` and refuse a run that does not fit in what is left (exit 4, nothing drawn);
a run with nothing left to draw always passes, so `process`, `qa` and `review` (and `all` on a drawn
set) still run after the budget is spent. When a run is refused, never raise the cap yourself: tell
the user what is spent and what is left, and ask; only on their yes raise `budget.images` in the
profile or rerun with `--over-budget` (every entry past the budget is marked `over_budget`).
`--budget N` caps one run and is never stored; a number above the budget is refused (exit 4)
unless `--over-budget` comes with it. A context file that does not parse stops every command
(exit 2) instead of falling back to a default budget. A project that counted images before the
ledger existed (`spend.images_used`) is carried over as one `seed` entry, and `spend.images_used`
never goes down. Two runs may share a ledger (a cross-process lock, `<ledger>.lock`).
`art.py budget <spec>` prints the state. Copies of the artist's own `source` images cost nothing. An
animation made from a video is one entry counting the frames it replaces (an approved frame 0 the clip
keeps is not counted): `budget --video <anim> --quote` first (records nothing), then, after the user's
yes, one record with `--credits` right before the job is submitted (`--drop` if it never was); the
service's credits are the user's separate yes, asked once per run.

`candidates` and `gen` need the Codex CLI; `style`, `anchor`, `process`, `qa`, `review` and
`feedback` work on whatever images are in the raw folder (in the WowCube pipeline also a
paid provider's, but only when the user explicitly asked for one and agreed to pay:
`cube_asset-builder/references/ART.md` "No Codex"). Codex must be logged in with ChatGPT:
`gen` refuses an API-key login, which would bill that key.

## Workflow

### 1. Intake
Ask for: the references (their own drawings, finished sprites, or mood images
they like), the list of assets (or a manifest), where the art will
be used (WowCube cube screens: give the sizes yourself from `references/SIZES.md` and check them with
`art.py sizes`; other targets: say so), and hard constraints (transparent background, palette
limits, text). Run `art.py init`, put references in `refs/`, drawings in
`drawn/`.

### 2. Style bible
Study the references closely (zoom in: outline pixels, tone steps, light
direction, palette). Fill `style/STYLE.md`: one-line summary, viewpoint,
palette with roles, rendering (outline, shading, light, detail at final size),
proportions, Do/Don't, and the operational `## Prompt block` that is injected
into every prompt. Show the artist a short summary and get explicit approval;
their corrections go straight into the file. (Pipeline, autonomous: the summary rides
with the style-lock message; no separate stop.)

### 3. Anchors (the style lock)
- If the artist supplied finished art in the target style, those images are the anchors.
- Otherwise draw 1-3 **style frames** with `art.py candidates --subject "<a representative character, prop or scene>"` (refs/ and drawn/ are attached), show them, iterate until the artist approves one. Never mass-generate before an approved frame.

Before you lock, **check the frame against STYLE.md, rule by rule** (outline, shading steps, light,
palette roles, Do/Don't). Where the approved frame and the text disagree, one of them changes now:
the artist says which, and either STYLE.md (and its Prompt block) is rewritten to describe the frame,
or the frame is redrawn. An anchor that contradicts the bible makes the QA loop unwinnable: every
later asset is held to both, and reviewers flag "majors" that no redraw can fix.

Put the approved images in `style/anchors/`, list them in `art.json`
(`style.anchors`), run `art.py style`. Check the palette swatch with the artist.

**Variant colours.** The profile is measured from the anchors only, so a legitimate variant in
another color (the blue and green ships next to the red anchor ship, team colors, a gold/silver/
bronze medal set) fails the palette score. List those colors, with their role, under
`## Variant colours` in STYLE.md (hex codes; `references/STYLE_TEMPLATE.md`), then run `art.py style`
again: each color adds a lightness/chroma ramp of its hue to the palette, so the variants are
judged on everything else (light range, outline, detail). `qa` warns when the section changed
after the profile was built. `@style_exempt` stays for assets that leave the style on purpose
(a logo, a photo backdrop), not for color variants.

### 4. Family leaders first
For each family (a character, a prop group, the UI kit, effects), generate ONE
leader asset (`gen --only <leader>`), run `process --only <leader>` + `qa --only <leader>`, look
at it, fix, get the artist's OK (pipeline, autonomous: the fresh reviewer's OK), then
`art.py anchor --only <leader>` (it stores the approved final, and its keyed, color-matched
raw-resolution look in `anchors/hires/` as the reference Codex gets). While the rest of its set has no raw image, `process` fits the leader alone and
prints `partial set: refit when the family is complete`: expected. The rest of the family is
generated with the leader as `subject_ref` (same design, only the pose/state changes) and
held to the grown profile; the next `process` refits the complete set at one shared scale
(look at the leader again in `qa/sets.png`; its anchor keeps the approved look).

### 5. Batch + strict review loop
For every batch:
1. `art.py gen` (only what is missing or failed), `process`, `qa`.
2. Look at three views of each asset: raw output, final x4, and in context (on its background/next to neighbors at the real display scale). Read `qa/sets.png` and the GIFs for every set.
3. Every numeric FAIL is a question, not a verdict: open the picture (`qa/all.png`, `qa/sets.png` and its onion
   skin, the GIF, next to the anchors) and decide. **False** (the picture is right, the number is not: a back
   view no anchor shows, two different monsters in one set, a squash frame, a broken brick that should not fill
   its cell) -> `art.py waive <spec> --only <asset> --check <id> --reason "<what the picture shows>"`; `qa`
   then reports `WAIVED <asset>: <check> - <reason>` and does not count it until the image changes
   (`references/QA_RULES.md`, "Numeric FAILs are questions", also says when a waiver ends: the image, a set's
   reference frame or the style profile changes). Never add anchors, split sets or drop rules only
   to silence a check: anchors move every other asset's palette and outline checks. Size, transparency
   (cut-out), key fringe, alpha, opaque and missing/empty/kept-file checks are technical and cannot be waived.
   **Real** FAIL: fix the cause (sharper prompt line in `fixes.json`, better subject ref, green key for pink subjects, `fill`, `pose_free`/`colour_exempt` only for intended changes) and regenerate only what failed plus set partners that must match.
   **Style notes edit the source.** A `fixes.json` note is only **appended** to the prompt: it adds,
   it never removes. A note that contradicts the prompt ("no dark outline" when the `gen_prompt` or
   the Prompt block says "thick dark outline") leaves both instructions in the prompt and the model
   follows either. So a correction of the look (outline, shading, palette, light) is made where the
   look is described: the asset's prompt (`gen_prompt` in a WowCube manifest, `prompt` in art.json),
   or STYLE.md and its Prompt block (plus the manifest's `_style`) when it concerns every asset.
   `fixes.json` keeps additions and subject refs. `gen` prints a warning for a note that rules out
   something the prompt still asks for.
4. Style score FAIL: decide drift vs intended exception vs a false number. Drift -> fix and redraw. A whole class of asset that departs by design (sky, logo, UI) -> propose it to the artist; once accepted, `style_check: false` + a line under "Approved exceptions". One asset that is right but measures wrong (a pose the anchors lack) -> `waive --check style`.
5. Before the artist sees the batch: an independent consistency review by a fresh subagent. Give it exactly: `style/anchors/`, STYLE.md, QA_RULES.md, `qa/all.png`, and `qa/sets.png` when there are sets; not your conclusions (`art/0.png` is the packer's placeholder, not an asset). Codex in read-only mode is a good second opinion too (`references/CODEX.md`).

### 6. Artist review
`art.py review`, send/open `review.html`. The artist marks OK / Fix with
notes and presses "Copy feedback"; paste it into a file and run
`art.py feedback --file`. Notes become `fixes.json` entries; recurring notes
("outlines too thin", "too shiny") become STYLE.md rules and Prompt block
lines. Redraw, re-review, repeat until every asset is OK. Promote newly
approved family leaders to anchors.

### 7. Delivery
`final/` (or `assets_<game>/art/`) holds the exact-size PNGs; `art.py sheet` puts them on one sprite sheet
with a JSON atlas (`<ws>/sheet/`); `raw/` the
model outputs; `style/` the bible, anchors and profile; `review.html` the
last review. For WowCube, hand off to the pack stage (cube_asset-builder).

## Asset spec cheatsheet (art.json)

```json
{"name": "hero_walk_01", "size": [40, 40], "set": "hero", "motion": true, "colour_lock": true,
 "subject_ref": "hero_idle_00", "prompt": "the heroine mid-stride, left foot forward, facing down"}
```
`background: "opaque"` for full-frame pictures, `sketch: "drawn/pose.png"`
to follow the artist's drawing, `source: "drawn/logo.png"` for art the artist
made themselves (no redraw: it is copied in as the raw image, then keyed/fitted and checked like any other asset), `fill: 0.8` for tiles that must cover their cell,
`style_check: false` for approved departures, `pose_free: true` for frames
whose pose change is the point.

## Prompt craft that worked

- Describe the subject, pose and colors; let the Prompt block and the anchors carry the style. Do not re-describe the style per asset in different words (it drifts).
- Name the view every time for non-standard assets ("flat front view" for UI in a top-down game).
- Animations from a video (opted in): `references/ANIMATION_VIDEO.md` has the prompt pattern; the frames
  come in as drawings (`video_to_frames.py`), with `fixed_canvas` / `"fit": "canvas"` to keep the motion.
- For animation frames, name the phase and what must stay identical ("same character, same tiara, same dress length, only the legs move").
- For effects (flash, blast, slash): "no characters, no objects, only the effect", or the anchor's content leaks in.
- Square canvas, single subject, clear margin, flat key backdrop; the processor crops and scales.
