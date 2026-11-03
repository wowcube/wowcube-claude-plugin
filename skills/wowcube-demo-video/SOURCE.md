# Source

Author: Alex Poshivalov (WowCube). Adapted for this pipeline.

## Changes made here

- `templates/shot.h`: `header->SaveSize = APP_SAVE_SIZE` under `#ifdef APP_SAVE_SIZE`, as sim.h does, so a
  game without `app_save.h` compiles.
- `templates/capture.h`: a label sprite id at or above `CAPTURE_LABELS_MAX` (4096) no longer reads past the
  label table; it is written with an empty text.
- SKILL.md and the examples: `on_pretwisted` gets the plane being turned (`(t % OCT_TWIST_HALF) / 2`, the
  engine's `OCT_TWIST_PRE + plane`), not the twist id.
- `examples/`: the original examples were captures of existing games; they are replaced by two examples written
  for the plugin's own template app (`templates/app_ai_template`): `template_tour` (method B, sprite mode, with a
  robot that turns the cube over) and `template_twists` (method C, net mode, with physical twists).
- `scripts/render_demo.py`: a sprite-mode capture stops with a message when `ids` is not a file / has no
  `BMP_` lines or the sprite dump is empty, instead of rendering a blank video.
- `scripts/record_html.mjs` removed: the one copy is `wowcube-html-prototype/scripts/record_html.mjs`
  (identical); SKILL.md points there.
- SKILL.md description: every video request (including a video of a prototype) is this skill; building the
  prototype page is `wowcube-html-prototype`. Method A names the prototype's folder (`plans/` or `docs/`).
- `scripts/render_demo.py`: `--dump <art dir> [--manifest]` makes the sprite dump from a pipeline game's
  `assets_<game>/art` (this repository has no `gen_art.py`); the documented numpy / Pillow pins are the ones of
  `scripts/requirements.txt`.
- SKILL.md, `templates/capture_demo.sh`: no `gen_art.py`, `art\!pack.bat` or "cloud environment"; they name
  what the user needs instead (the sprite dump, a packed app, Node.js + Playwright + Chromium and ffmpeg).
