# Source

Author: Alex Poshivalov (WowCube). Adapted for this pipeline.

## Changes made here

- `references/example-maze_box.html`: links `common/cube.css` and `common/cube.js`, the layout SKILL.md
  prescribes, instead of `../assets/`.
- SKILL.md "Where to put it": pipeline games use `plans/<game>_prototype.html` + `plans/common/` (as
  `cube_game-designer` Step 5), an existing game repository keeps `docs/`; autonomous runs build one only when
  the brief asks.
- SKILL.md description: this skill builds the page; recording or rendering any video (also of a prototype) is
  `wowcube-demo-video`, which uses this skill's `scripts/record_html.mjs` (now the only copy).
- `scripts/record_html.mjs`: the default query adds `video`, so a recording never plays sound (the skill silences
  sound only under `?video`).
