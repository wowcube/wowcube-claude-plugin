# Animation from video (optional route)

An image-to-video service animates ONE approved picture of a character; `scripts/video_to_frames.py`
cuts the clip into keyed frames that go through the normal `process`, `qa` and review like any other
drawing. Proven on 2026-11-03 with the Higgsfield MCP connector in Claude Code (Kling 3.0): an 8-12 frame
idle loop for about 7.5 credits and about a minute, seam between the clip's first and last frame about
1/255.

The connector is an MCP connector: only Claude in the session can call its tools (`generate_video`,
`jobs_wait`, `media_upload`, `media_confirm`, `balance`). No script in this repository calls it.

## When it is used (opt-in only)

All three must hold; otherwise every frame is drawn by the normal picture route (Codex, the user's image
tool, their own art or drawn in code), exactly as before:

1. **The user named it.** The setup answer to "What AI tools and subscriptions do you have?" names an
   image-to-video service ("I have Higgsfield": `resources.have` holds `video`, the project file says
   `art.animation: "video"` and `art.animation_provider: "higgsfield"`;
   `wowcube-setup/references/PROFILE.md`), or the user asks for it in this run ("animate it with
   Higgsfield"). A connector found in the session is a fact, never consent: do not offer it unasked
   more than once, and never use it on your own.
2. **The connector's tools are in this session** (`generate_video` and `jobs_wait` of the Higgsfield
   connector). Missing: say once that the animations will be drawn frame by frame instead, and go on.
3. **The user agreed to the cost in this run.** It spends their paid credits: preflight every job with
   `get_cost: true`, then ask ONCE per run, with the quoted total for all the animations of the run,
   before the first job (the same rule as a paid image provider, `cube_orchestrator/references/RUN_MODES.md`):
   never once per animation or per batch. Autonomous mode, `YOLO` and a profile entry are not consent.
   Plain words, for example:
   "I can animate the fox's idle and walk with Higgsfield: 2 short videos, about 15 credits from your
   Higgsfield account (you have N). The fox's picture and a description of the movement are sent to
   Higgsfield. OK?"
   Only an animation added later in the same run that pushes the total past what they agreed to is asked
   again.

`data_policy.may_leave_machine` gets `animation_frames` (the base picture of each animation and its motion
description go to the service). A project with `may_leave_machine: []` never uses the route.

Do not use the service for what the user already has through their own subscription (pictures: their
ChatGPT/Codex, their image tool). Its value is what they do not otherwise have: the video models. In
particular its GPT image model is never used when the user has ChatGPT/Codex.

## What it suits

- **Good**: looping idles (breathing, blinking, bobbing, tail wag), walk and run cycles in place, short
  actions that return to the start pose (a hop, a nod, a wave, a shake).
- **Poor**: actions that travel across the screen (animate in place; the game moves the sprite),
  effects (flashes, particles: draw them), big rotations or turnarounds (the design drifts), anything
  where every frame must hit an exact pose (a timer ring, a progress bar: `fit: canvas` drawings).
- **Size**: cube sprites are authored at half the screen size (a 40x40 sprite shows as 80x80). The
  video's fine texture (fur, grass blades, small shading) is lost at that size; big flat shapes, a clear
  silhouette and a thick outline survive. Judge the result in the x2 preview GIF, not in the clip.

## The route, step by step

### 1. The base picture
One still of the character in the locked style, centered, whole body with a margin, on a flat key color
(magenta `#FF00FF`; green `#00FF00` for a pink or purple character):
- best: the approved anchor or the final sprite of that animation's first frame (`assets_<game>/art/` or
  `style/anchors/hires/`), composited on the key color and scaled up (nearest neighbor for pixel art) to
  about 1024x1024;
- else: drawn by the user's normal picture route like any other asset (a manifest entry of its own is not
  needed; draw it as the animation's frame 0, approve it, then composite).

That approved frame 0 stays the animation's first frame: the clip only replaces the frames after it
(`video_to_frames.py` keeps an existing `<anim>_00` and `art.py budget --video` does not count it).

Who draws the base: the user's picture route. The video service's own image models draw it only when the
user chose that service for pictures too (the setup answer names it as their picture tool, or they ask
for it in this run); then its other image models (FLUX and the like) may draw the base, never its GPT
image model when the user has ChatGPT/Codex. What decides is the tool the user chose for pictures, not
whether another route could draw it (drawing in code always could).

### 2. Check the budget, preflight, ask once, then record
1. `python <skills>/skills/cube_art-director/scripts/art.py budget <spec> --video <anim> --quote` checks
   that the job fits the image budget (below, "Budget") and records nothing. Exit 4: it does not fit; do
   not submit; ask the user as for any spent budget.
2. Upload the base: `media_upload` (`filename: "<anim>_base.png"`), PUT the bytes to the returned
   `upload_url` with curl, then `media_confirm` (`type: "image"`, the `media_id`).
3. Preflight: `generate_video` with the exact parameters below plus `get_cost: true`; `balance` for what
   they have. Ask (step "When it is used", 3) once for the run's total.
4. On their yes, right before submitting each job: `art.py budget <spec> --video <anim> --credits <cost>`
   records it ONCE, with the credits it costs. The job was not submitted after all (a submission error
   with no job id, the user changed their mind): `art.py budget <spec> --video <anim> --drop` removes that
   entry. Never drop a job that was submitted, and never record the same job twice.

### 3. Animate
`generate_video` with `params`:

```json
{"model": "kling3_0", "mode": "std", "sound": "off", "duration": 5, "aspect_ratio": "1:1",
 "medias": [{"role": "start_image", "value": "<media_id>"}, {"role": "end_image", "value": "<media_id>"}],
 "prompt": "<prompt>"}
```

The SAME picture as start and end image makes the clip return to its first frame: a seamless loop.
Prompt pattern (one paragraph, plain):

> Locked static camera, no zoom, no pan. The flat magenta background never changes, no shadows, no
> ground, no new objects. The <character> stays in the same place and size in the frame. <The action:
> breathes slowly, blinks once, tail sways left and right / walks in place, legs alternating, body
> bobbing slightly>. Same character design, colors and outline as the picture in every frame. At the
> end it returns exactly to the starting pose.

Leave `use_unlim` out unless the user asked to use free-trial generations (the tool then returns a
question for the user instead of charging).

### 4. Wait without burning turns
`generate_video` returns a job id. `jobs_wait` long-polls at most 15 s per call; a job may sit "queued"
for minutes. Do other work between polls (cut the previous clip, process, QA), or poll with the
`poll_after_seconds` it returns; never loop dozens of empty polls. After a transport timeout the
submission outcome is unknown: never resubmit before the first job's state is known (that would pay
twice).

### 5. Download and cut
Download the finished clip's result URL into a fresh folder (`<ws>/assets_<game>/video/<anim>.mp4`, or
`<project>/art_work/video/` for art only), then:

```
python <skills>/scripts/video_to_frames.py <clip.mp4> --name <anim> --spec <manifest or art.json> \
    [--supersample 4] [--align bottom] [--key auto] [--start S] [--end E]
```

It picks the spec's frame count evenly (a loop never repeats the closing frame), keys the background
(median corner color; alpha ramps over the color distance `--key-range 40:80`), despills the outline
(no key-colored fringe on dark backgrounds), crops all frames with one shared box (the filmed motion is
kept), scales to the sprite's size and writes:
- the frames where the pipeline reads drawings: a manifest → `assets_<game>/raw/<anim>_NN.png`; an
  art.json → `<project>/drawn/<anim>_NN.png` (each frame `"source": "drawn/<anim>_NN.png"`). The approved
  first frame `<anim>_00` (its final, raw or drawn image exists) is KEPT: only `<anim>_01` onwards are
  written. `--no-keep-first --force` replaces it with the clip's first frame;
- `<workspace>/video/<anim>.png` + `.json` (the sheet and atlas `art.py sheet` writes) and
  `<anim>_preview.gif` (x2, dark background);
- the loop seam: the first frame against the clip's closing frame, next to the typical step between
  frames. "VISIBLE JUMP" = the clip did not return to its start: regenerate (ask if it costs beyond what
  they agreed to) or use `--once` for a one-shot action. It also prints the wrap (the last picked frame
  back to the first, the jump the loop makes when it restarts) to compare with the same typical step.
Other existing frames are replaced only with `--force`. `--start` / `--end` cut a part of the clip (works
with any ffmpeg version; `--start` alone runs to the end). Without a spec:
`--frames N --size WxH --out <dir>`.

### 6. The normal pipeline
Give the animation's frames `"fit": "canvas"` in the manifest (`"fixed_canvas": true` in art.json) so
`process` keeps the shared crop instead of recentering every frame; then `art.py process`, `qa`, the
fresh-agent review and the review page as for drawn frames. The frames are held to the same QA_RULES.md:
a frame that drifts from the design (a new color, a changed face) is a FAIL like any other. The kept
frame 0 is checked with them: a jump between it and frame 1 in the GIF is a real FAIL (`set_centroid`);
re-cut with another `--align`, or with `--no-keep-first --force` (the clip's own first frame, filmed from
that same approved still).

## Budget

A video job is ONE ledger entry of kind `video` whose `count` is the number of frames it replaces
(`art_budget.py`): the animation's frames minus the approved frame 0 the clip keeps. It costs the image
budget what drawing those frames one by one would, so the budget arithmetic (`build_pipeline.py
validate`, the tier's caps) is the same on both routes. The order is: `--quote` (checks, records
nothing), the user's yes, then one record with `--credits` right before the job is submitted; `--drop`
only for a recorded job that was never submitted. A regenerated clip is a new entry. Past the budget
nothing is submitted; only on the user's yes `--over-budget` (marked in the ledger) or a raised
`budget.images`. The credits are the user's separate yes, asked once per run; the ledger only notes them
(`credits`).

## Fallbacks

- No connector tools, no yes to the cost, a job that fails twice, or a seam or a design drift that two
  regenerations do not fix: draw that animation's frames with the normal route and say so in one line.
- **Higgsfield's `autosprite` model**: failed 4 of 4 times in testing (no reason given, credits
  refunded). Unreliable: never the default; only when the user asks for it.
- Background not flat (gradient, shadow): `--key` with the color you see and a wider `--key-range`
  (e.g. `30:90`); otherwise regenerate with the background lines of the prompt stated more firmly.
