# Style bible: <project>

The single source of truth for the look. Written together with the artist
from their references and drawings, approved by them, and kept short enough
to read in one minute. Every rule here is checkable on a generated image.
Anything the artist corrects during review is added here (and to the
`## Prompt block` when it changes how prompts should read).

## In one line
<e.g. "Dark top-down pixel art, chunky 2 px outlines, warm candle light, desaturated wood and stone, one saturated accent per character.">

## Viewpoint and framing
- Projection: <top-down 90° / 3/4 top-down / side view / isometric 2:1 / flat front for UI>
- Camera distance and how much of the object is visible: <...>
- Exceptions (UI, logo, backgrounds): <...>

## Palette
- Core colors (hex, role): <#16100c shadow wood, #3e291a mid wood, ...>
- Accent colors and where they may appear: <warm yellow only on the fireflies and the lantern>
- Forbidden: <pure white, neon, rainbow gradients ...>
- Value range: darkest <...>, lightest <...> (highlights only on <...>)

## Variant colours
<!-- Optional. Colors a legitimate variant may use besides the anchors' palette: other ship or team
     colors, a gold/silver/bronze set. One line per color: hex + role. `art.py style` adds each as a
     shaded ramp of its hue to the measured palette (rerun it after a change). Leave empty when every
     asset shares the anchors' colors. Example:
     - #2846d2 blue ship variant
     - #30a050 green ship variant -->
- <none, or the colors as in the example above>

## Rendering
- Outline: <color, weight in FINAL pixels, where it is dropped>
- Shading: <number of tone steps, cel / soft, dithering yes/no>
- Light: <direction, color, how strong>
- Texture and detail density at final size: <what must survive the downscale>
- Pixel grid: <true pixel art at final size / painterly downscaled / vector-flat>

## Proportions and shapes
- Characters: <head:body ratio, silhouette rules, readable at N px>
- Props: <chunky, simplified, ...>

## Do / Don't
- Do: <...>
- Don't: <...>

## Approved exceptions
- <asset or family>: <how and why it departs from the rules above, approved by the artist on DATE>

## Prompt block
<!-- This paragraph is injected at the top of EVERY generation prompt. Keep it
     operational: viewpoint, palette words, outline, shading, light, detail
     level, background rules. 60-120 words. No asset-specific content. -->
<Dark moody pixel art seen from directly above ...>
