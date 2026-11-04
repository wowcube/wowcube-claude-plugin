# Source

Contributed by the WowCube team. Adapted for this pipeline.

## Changes made here

- The full example page of an earlier game was removed (examples stay genre-neutral); SKILL.md describes the
  page structure and shows a neutral autopilot script.
- The gesture is called **tap** everywhere (pages, legends, captions); `onTap` is accepted as the name of the
  tap callback (`onPat` still works).
- SKILL.md "Where to put it": pipeline games use `plans/<game>_prototype.html` + `plans/common/` (as
  `cube_game-designer` Step 5), an existing game repository keeps `docs/`; autonomous runs build one only when
  the brief asks.
- SKILL.md description: this skill builds the page; recording or rendering any video (also of a prototype) is
  `wowcube-demo-video`, which uses this skill's `scripts/record_html.mjs` (now the only copy).
- `scripts/record_html.mjs`: the default query adds `video`, so a recording never plays sound (the skill silences
  sound only under `?video`).
