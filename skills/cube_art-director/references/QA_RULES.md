# QA rules: the reviewer's contract

The goal is a set that is *good*, not merely *present*. Claude reviews every
asset against these rules and makes Codex redraw until each one passes or a
look at the picture shows the FAIL is false (then it is waived: "Numeric FAILs
are questions" below). "It basically works" while a rule is broken is a FAIL.
There is no "good enough after N tries": change the prompt, the references or
the processing until it passes, and only escalate to the artist when a rule
genuinely cannot be met, saying what was tried. The one exception is a spent
image budget ("A spent budget" below).

`art.py qa` measures what can be measured (exit 1 on a hard failure); the
visual rules need eyes on three views of every asset: the raw model output,
the final image at x4 nearest-neighbor, and the asset composed in its real
context (on the game background, next to its neighbors, at device scale).
Most defects show in only one of the three.

## S. Style lock (the artist's references are the law)

| # | Rule | How checked |
|---|------|-------------|
| S0 | **Anchors and bible agree.** Before the lock every anchor is checked against STYLE.md rule by rule; a contradiction is resolved by rewriting STYLE.md (and its Prompt block) to the approved frame or by redrawing the frame, never left for the QA loop. | visual, at the lock |
| S1 | **Matches the anchors**: palette family, outline color and weight, shading steps, light direction, detail density. A color variant listed under STYLE.md's `## Variant colours` (other ship colors, team colors) matches in everything but its color. | `qa` style score (palette distance, off-palette share, over-saturation, light/dark range, outline; the palette includes the declared variant colors after `art.py style`) + visual side-by-side with the anchors |
| S2 | **Matches the style bible's Do/Don't list** line by line. | visual, against STYLE.md |
| S3 | **No content leak** from a reference: only the style is copied, never a character, prop, composition or background of the anchor (a person inside a sparkle effect sprite = FAIL). | visual |
| S4 | **Deliberate departures are declared**, never silent: an asset that must break the palette (sky, logo, UI, glowing effect) is marked `style_check: false` (or `@style_exempt`) and listed under "Approved exceptions" in STYLE.md once the artist accepts it. A color variant is not a departure: it goes under `## Variant colours`. | spec + STYLE.md |
| S5 | **The lock grows with approvals**: once the artist approves a new family's first asset (first character, first prop; in an autonomous WowCube run the fresh reviewer approves it), promote it with `art.py anchor` so the rest of that family is held to it. | workflow |
| S6 | **Corrections of the look edit the source.** A style correction changes the asset's prompt (manifest `gen_prompt`) or STYLE.md / its Prompt block (and `_style`); a `fixes.json` note only appends and cannot override contradicting words (`gen` warns). | `fixes.json` vs prompts |

## A. Every asset

| # | Rule | How checked |
|---|------|-------------|
| A1 | **Right subject, nothing else**: exactly what the prompt names; no extra props, no text unless the asset is text. | visual |
| A2 | **Viewpoint** as the style bible says (a front-view window in a top-down room = FAIL). | visual |
| A3 | **Exact size**, transparent or opaque as specified. | qa |
| A4 | **Clean key**: no key-color pixels, no fringe; no semi-transparent pixels when alpha is binary (the default; `alpha: "soft"` keeps anti-aliased or translucent edges on purpose: glows, smoke, a modded game's soft-edged originals). A `keep` asset (a modded game's own sprite carried through unchanged) is exempt from every A and B rule: `qa` checks only its size, format and that it is still its original. Holes that should be solid (glass, gaps) must not be keyed out: draw them dark in the prompt. A subject that uses pink/magenta gets the green key. | qa + visual |
| A5 | **Footprint**: objects that occupy a cell/slot fill it (`fill`), nothing looks smaller or bigger than its gameplay size. | qa (`fill`) + in-context view |
| A6 | **Readable at final size** on its real background: silhouette and key features survive the downscale (if a hat or a held tool vanishes, enlarge or simplify it in the prompt). | final x4 + in-context |
| A7 | **Text is spelled exactly.** | visual |
| A8 | **Names** are `[a-z][a-z0-9_]*` (a letter first) and short (WowCube packer: 23 characters max, no reserved name; `build_pipeline.py validate` checks a manifest). `art/0.png` (1x1, transparent) is the packer's slot-0 placeholder `process` writes: not an asset, exempt. | spec validation |

## B. Sets and sequences (the strictest part)

A set = assets with the same `set` and size: animation frames, a character's
idle/walk/attack, state pairs (intact/broken, full/empty).

| # | Rule | Threshold |
|---|------|-----------|
| B1 | **Same design in every frame**: same character, costume, proportions; only the described pose changes. Later frames are generated with the first as `subject_ref`. | visual (onion skin, flipbook) |
| B2 | **No scale pumping** inside one animation (`motion` sets share one scale; frames are never fitted to their own bbox). | area 0.85-1.15, height 0.93-1.07 vs the anim's first frame (hard for color-locked characters; `pose_free` frames such as an attack lunge only warn) |
| B3 | **No position jitter**: frames aligned on the center of mass. | centroid drift <= 1.0 px |
| B4 | **Colors logical within a set**: one character keeps its colors (`colour_lock`); a change only where it means something (wounded, broken, empty) and marked `colour_exempt`. | mean dRGB <= 10 |
| B5 | **The loop reads as the intended motion**, no flicker of random details. | flipbook GIF |
| B6 | **States are distinguishable** at final size while keeping the footprint. | final x4 + in-context |
| B7 | **Paired scenes line up** (day/night versions of one background): generated with the first as `subject_ref`. | visual overlay |

## Numeric FAILs are questions: look, then fix or waive

`art.py qa`'s numbers are proxies: a style score against the anchors, `fill`,
and the set numbers (centroid, area, height, color drift). They are often
wrong for one asset: a back or side view "off style" because no anchor shows
that pose, two different monsters in one `set` "drifting" in color, a broken
brick that should not fill its cell, a squash frame "pumping". Every such FAIL
is a question; answer it with the picture, not with the number:

1. Open the asset in the QA sheets (`qa/all.png`, `qa/sets.png` with its onion
   skin, the flipbook GIF) next to the anchors.
2. **Real** (the picture shows the defect): fix it as above (prompt, reference,
   processing) and redraw.
3. **False** (the picture is right, the number is not): waive that one check of
   that one asset with a one-line reason saying what the picture shows:
   `art.py waive <spec> --only hero_back --check style --reason "back view: same
   palette and outline as the anchors, no anchor shows a back"`.
   `qa` then prints `WAIVED <asset>: <check> - <reason>` and does not count it.
   A set check is waived after a `qa` run (the waiver binds the frame the
   number was measured against, from `qa/report.json`).
   `art.py waive <spec>` lists the waivers (a stale one says why); `--drop`
   removes one.

**When a waiver ends.** A waiver holds only for what was looked at; `qa` drops
it (`FAIL ... its waiver was dropped: <why> - look at it again`) and the check
counts again when:
- the asset's final image changes (redrawn or reprocessed): every waiver;
- a set check (`set_*`) is measured against another frame, or that reference
  frame's image changes (a redrawn first frame);
- a `style` waiver's style profile changes: an anchor added, removed or
  replaced, or the variant colors changed (`art.py style` / `anchor` rebuild
  the profile).

Waivable check ids: `style`, `fill`, `set_centroid`, `set_area`, `set_height`,
`set_colour`. Never waivable (technical: fix them with `process`, the key or the
size): `size`, `cutout` (transparency), `key` (key-color fringe), `alpha`,
`opaque`, `missing`, `empty`, and a kept sprite's `keep_size` / `keep_format` /
`keep_original`. Waivers live in art.json (`qa_waivers`), or for a WowCube
manifest in `<workspace>/qa_waivers.json`.

**A spent budget: "accepted under budget", never a waiver.** When the image
budget is spent (`art.py budget` shows nothing left) and a REAL failure remains
(the picture shows the defect), it is not waived as false: it is recorded as
accepted under budget, with the finding as the reason:
`art.py waive <spec> --only <asset> --check <id> --under-budget --reason
"accepted under budget: <the finding>"`. The tool refuses it while images are
left; `qa` prints `ACCEPTED UNDER BUDGET <asset>: ...` and counts it apart
(`accepted_under_budget` in `qa/report.json`), and the final report lists it
under `accepted_under_budget` (cube_orchestrator `STAGE3_ASSETS.md` §3). It
ends like a waiver. Neither waivers nor acceptances are ever written into
`fixes.json` (that file holds corrections only).

**Never add anchors, split or regroup sets, or drop rules only to silence a
check.** Anchors are the style (adding a pose to them, or removing one, moves the
palette and outline checks of every other asset: removing the fire sprite from
the anchors made every yellow sprite "fall out of the palette"); a `set` is one
character's frames; the class exemptions (`@style_exempt`, `@pose_exempt`,
`@colour_exempt`, `fill`) are for assets that are different *by design* and are
declared in STYLE.md, not for one false number. One false number = one waiver.

## Reporting

- Per asset: PASS, or what failed and what was changed.
- Never present a set to the artist while `qa` fails or a visual rule is knowingly broken.
- Every fix goes to `fixes.json` (or the spec), never only into the chat, so a regeneration reproduces it.
- Before the artist sees a batch: an independent consistency review by a fresh agent (no anchoring on your opinion), then the review page.
