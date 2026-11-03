# Sprite sizes and colours for the WowCube (the art director's sizing reference)

Answer "what size should my sprites be?" from this page at once: it needs no game design. The art director
owns these rules and checks them: `python <skills>/skills/cube_art-director/scripts/art.py sizes [<spec>]`
prints the guide and, with an `art.json` or a manifest, checks every asset's size against its role (exit 1
on a size that cannot work); `art.py qa` repeats the findings as `SIZE ERROR` / `SIZE WARNING` lines. The
same numbers live in `scripts/art_sizes.py` (code) and the engine facts in
`<skills>/templates/app_ai_template/API.md`, "Art tiers".

## The screen and the 2x rule

- The cube has **24 screens of 240x240 pixels**, four on each of its six faces.
- Most sprites are drawn at **half size** and shown **twice as big**: a character that should look 64 px
  tall on the screen is drawn 32 px tall. The largest half-size picture is **120x120 = one whole screen**.
  The x2 is crisp (nearest neighbour): bold shapes and clear silhouettes survive, hairlines and soft brush
  texture do not. Paint big if you like, but judge it at the drawn size x2.
- **Fullsize** sprites are drawn 1:1, up to 240x240, and always sit **above** every half-size sprite and
  the text on that screen. Use them only for special cases (a crisp splash, a detailed full-screen
  picture with nothing drawn over it).
- The **launcher icon** is its own thing: 160x160, a flat-top hexagon badge.

## Typical drawn sizes by role

| Role (`role` in art.json, else guessed from the name) | Drawn size | On screen |
|---|---|---|
| `background`: a full-screen background | 120x120 (full colour, no transparency) | the whole 240x240 screen |
| `panorama`: a picture across several screens | 120x120 per screen piece | one screen per piece |
| `character`: hero, enemy, creature | 16-60 px | 32-120 px |
| `tile`: a board tile | 10-60 px; a size that divides 120 (12, 15, 20, 24, 30, 40, 60) fills a screen evenly | 20-120 px |
| `button`: a button or panel | 20-80 px wide | 40-160 px (a finger needs 60+ px on screen) |
| `hud_icon`: heart, coin, star | 8-32 px | 16-64 px |
| `particle`: spark, dust | 2-16 px | 4-32 px |
| `launcher_icon` | 160x160 | the launcher |
| `sprite`: anything else | up to 120x120 | up to 240x240 |

A size outside its role's range is a warning (it may be intended: say why in `notes`); a half-size sprite
over 120 or a fullsize one over 240 is an error.

## Colours

- Each sprite is stored with a **palette of at most 256 colours**, one of them transparent; sprites that
  look alike share one palette, and one screen shows about 4,000 different colours at once. The cube also
  stores colour with less precision than a PC screen.
- **Flat colours and a few deliberate shades** survive well. Smooth gradients, glows and textured brushes
  are reduced to fewer colours and may band. You do not count colours: the packing step reduces them; fewer,
  deliberate colours look better.
- **Full-colour pictures** (backgrounds) keep every colour but have **no transparency**.
- Edges are cut hard by default (each pixel fully on or off); a sprite marked soft-edged (`alpha: soft`)
  keeps its anti-aliased edges.

## How the graphics are handed over (sprite sheets)

- Every sprite is **its own PNG with its own name** (`hero_walk_01.png`), at its exact drawn size, on a
  transparent background (backgrounds: opaque). The pipeline packs those PNGs into the cube's format with
  shared palettes; there is no sheet inside the game.
- **A sprite sheet the studio wants** is an export: `art.py sheet <spec>` puts the finished PNGs on one grid
  plus a JSON atlas (each sprite's x, y, w, h).
- **A sprite sheet someone sends** is first cut into named PNGs: `art.py slice <sheet.png> --cell 32x32`
  (or `--grid 8x4`, or `--atlas sheet.json`; `--names a,b,c` in reading order); empty cells are skipped.
  The PNGs are then used as the artist's drawings (`"source": "drawn/<name>.png"`).
- A Photoshop file: export one PNG per layer (File > Export > Layers to Files), named as the sprites.

## "Will the AI train on my art?"

No: this pipeline does not train any model on the user's work. If the user chose an outside tool
(ChatGPT/Codex, an image service), that provider's own data settings apply to what was sent to it; with
their own art or art drawn in code, nothing leaves the computer.
