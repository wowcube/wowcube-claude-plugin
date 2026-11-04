---
name: "wowcube-demo-video"
description: "Making WowCube game demo videos in the standard format: 1920 x 1080, the 3D cube on the left, the same 24 screens as a 2D net plus the controls legend on the right, captions per scene, the game played by its autopilot on the real rules, recorded from the game's HTML prototype. Use for every video request, including a video of a prototype: \"make a video\", \"record a demo\", \"gameplay video\", \"record a clip\", \"demo for the game designer\". Building the prototype page itself is wowcube-html-prototype."
---

# WowCube game demo video

Everything needed is in this skill, except the HTML recorder of method A, whose one copy lives in the
sibling skill `wowcube-html-prototype`.

`<skills>` = the folder two levels above this SKILL.md (the plugin root; `${CLAUDE_PLUGIN_ROOT}` when the host exports it); resolve it on every entry, never store it. This skill's folder is
`<skills>/skills/wowcube-demo-video/`.

```
../wowcube-html-prototype/scripts/record_html.mjs
                             records an HTML prototype on a fake clock (method A)
references/layout-html.jpg   what a frame looks like
```

## Where things go

- **A game in the WowCube pipeline**: the video goes to `<ws>/video/<game>_demo.mp4` in the workspace
  (create `<ws>/video/` first: the recorder does not create folders). Stills from it go to
  `<ws>/video/<game>_<scene>.jpg`:
  `ffmpeg -ss <sec> -i <ws>/video/<game>_demo.mp4 -frames:v 1 -vf scale=1280:-1 -q:v 3 <ws>/video/<game>_<scene>.jpg`.
  They can illustrate the GDD (its Intro section) and the game description.
- **An existing game repository** (no pipeline run): `docs/demo/<game>_demo.mp4` (`docs/demo/` and `*.mp4` in
  `.gitignore`); stills for documents go to `docs/img/<game>_<scene>.jpg` and are committed.

## What it looks like

Frame: `references/layout-html.jpg` (HTML prototype). The same for every game:

- 1920 x 1080, dark background, two rounded panels.
- **Left**: a small-caps header with the game's gestures (`3D · TILT MOVES THE PLAYER · TAP · TWIST`); a
  large 3D cube, slightly tilted following gravity, twists rotate half of the cube; a caption plate at the
  bottom: a bold line and a short explanation.
- **Right**: `NET (2D) · SAME SCREENS, UNFOLDED`, a cross-shaped net (U on top, L F R B, D at the bottom)
  with face letters; the game title in two colours, subtitle `WowCube game · <tagline>`; a legend
  "icon + gesture + what it does", with the current gesture's row highlighted.
- Gesture icons are the game's own sprites (its twist, tap, tilt icons); the font is the game's font.
- 35-90 s; 30 fps for HTML (20 fps for an engine capture: frame = tick). `libx264`, `yuv420p`, crf 18-20.

## Scenario

Each scene is one idea with one caption (`capShot` / autopilot step):

1. Title, 2-3 s.
2. The first level with tutorial hints.
3. Each mechanic once: the caption names the gesture and the result.
4. A mistake and its fix (an extra twist → restart with a double tap, losing a life).
5. A late level that uses the whole cube.
6. Victory, results, selector, game over or the ending.

The game is played by a bot or autopilot **on the real rules**: no fake animations.

## Method A: HTML prototype

Any page works if it can do two things: a video layout via `?cinema` (1280 x 720 CSS px: cube on the
left, net and legend on the right, as in `references/layout-html.jpg`) and an autopilot via `?autoplay`
that runs the page's real rules, shows scene captions and sets `window.__demoDone = true` at the end.
Recording needs Node.js with Playwright + Chromium and ffmpeg on the machine (`check_env` reports them).
Playwright is never installed into the plugin folder: install it once under
`~/.wowcube/node` (`npm i --prefix ~/.wowcube/node playwright`, then
`npx --prefix ~/.wowcube/node playwright install chromium`), a one-time download the user approves.
The recorder looks for it in `$WOWCUBE_NODE_DIR`, `~/.wowcube/node`, the workspace, then its own folder.

```bash
node <skills>/skills/wowcube-html-prototype/scripts/record_html.mjs <dir>/<game>_prototype.html <ws>/video/<game>_demo.mp4 \
     --seconds 120 --stopWhen "window.__demoDone"
```

`<dir>` is where the prototype lives: `plans/` for a pipeline game, `docs/` in a game repository (see
`wowcube-html-prototype`, "Where to put it"); in a game repository the output is `docs/demo/<game>_demo.mp4`.

Frame = exactly 1/30 s on Playwright's fake clock: the video is smooth and identical on every run.
Page errors are printed, exit code 2.

## Verification

- `ffprobe`: 1920 x 1080, fps, duration.
- Look at 4-6 frames at scene changes (`--still` or `ffmpeg -ss`): 3D and net match, captions are not
  clipped, the right gesture is highlighted, the twist rotates the right half, no empty screens.
- For HTML: no console errors, `stopWhen` fired before the limit.
