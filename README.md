# WowCube game skills for Claude Code

Make games for the WowCube with a coding agent: from an idea (or your own design document) to a
tested game file on your cube.

## What the WowCube is

The WowCube is a 2x2x2 cube made of eight modules. Each module carries three small screens, so the
cube shows 24 screens of 240x240 pixels, four on each of its six faces. You play it with your hands:
twist a layer, tap a face, tilt the whole cube. A game is one C++ header that runs as eight identical
copies, one per module, 20 ticks per second; it is installed as a single `.oct` file.

## Install

In Claude Code, two commands:

```
/plugin marketplace add wowcube/wowcube-claude-plugin
/plugin install wowcube@wowcube-skills
```

Or just ask Claude: **"Install the WowCube plugin from https://github.com/wowcube/wowcube-claude-plugin"**.

- **git is required**: Claude Code downloads the plugin with git. If git is missing, Claude can install it for
  you (on Windows with `winget install --id Git.Git -e`) after you say OK; restart Claude Code afterwards.
- **Private for now**: the repository is private, so your GitHub account needs access to it (granted by
  WowCube) and your git must be able to use it (`gh auth login`, or your usual git credentials).
- Updates: `/plugin marketplace update wowcube-skills`, then `/plugin update wowcube@wowcube-skills` (or
  enable auto-update for the marketplace in `/plugin`).

In the docs, `<skills>` means the plugin's folder: two levels above each skill's `SKILL.md`
(`${CLAUDE_PLUGIN_ROOT}` when the host exports it, else the clone); the skills resolve it themselves on every run.

## Five-minute quickstart

1. Make an empty folder for your games (your workspace) and start Claude Code in it.
2. Say: **"Make a cube game: a fox catches fireflies by tilting the cube."**
3. First time only, it says in plain words what you are going to do together and that a few tools must be
   set up first, looks at your machine without changing anything, and asks at most four short questions:
   what you start from, how much guidance you want, which AI tools and subscriptions you have (in your own
   words: "Claude only", "I have ChatGPT", "Gemini", your own art...), and how thorough the checking should
   be. "I don't know", "you choose" or "just do it" take the defaults: it works on its own, the art is drawn
   in code and the sounds are synthesized, nothing leaves your computer. A login or key it finds on the
   computer is never assumed to be yours. Then it asks once for permission to install what building and
   checking a game needs (Python and its packages, the compilers, a small checker program into
   `~/.wowcube`); after installing, it asks you to restart Claude Code in the same folder and waits for you.
   If something cannot be installed (no admin rights), it tells you exactly what to install and where to
   get it. Your answers go to `~/.wowcube/config.json` and `<workspace>/wowcube.project.json`; say "change
   my settings" to change them.
4. It shows an estimate of time and tokens, then works. It stops once to show you the art style. Step by
   step mode stops at every step; the default runs on within your limits and saves and stops (or asks) when
   they are reached. A simple game with quick checking takes about 30-50 minutes.
5. You get the game file `dist/app_<game>.oct`, and after one yes it is uploaded to the WowCube store: you
   get a QR code (`dist/app_<game>_qr.png`) and a link. Scan the code with your phone (or open the link on
   it) and the WowCube app installs the game on the cube connected to your phone. A report of what was
   checked and the controls go to `context/<game>_report.md`.

Other ways in:

> "Here is our design document (design.pdf), make it a cube game." — imports it into the pipeline's
> design template, adds a cube feasibility annex and a list of open questions; scope cuts of an
> approved design wait for your approval.
>
> "Make the fox faster" / "swap the firefly sprite" — Mod mode, smallest change (a speed or a count is
> changed in minutes). "Undo the last change" puts the previous version back.
>
> "Repack app_mygame, bump the version and verify the .oct" — the toolbox (`wowcube-tools`), no stages.
>
> "Continue the firefly game." — resumes from the files in the workspace.
>
> "I'm an artist: make a sprite sheet for my game in one style, no code." — *Art only*: the art director
> tells you the sizes right away (`skills/cube_art-director/references/SIZES.md`), agrees the style with
> you, makes the pictures with what you have (Codex, your image tool, your own art, or drawn in code),
> checks them strictly and gives you one PNG per sprite plus a sprite sheet with a JSON atlas
> (`art.py sheet`; a sheet you were sent is cut into named PNGs with `art.py slice`). No build tools are
> needed or installed.

## Requirements by profile

Every game needs the base kit; the art column follows the tools you say you have at setup. *Art only*
needs just Python with Pillow and numpy (plus the drawing tool you chose).

| | Claude only | Own image key | ChatGPT (Codex) | Local model |
|---|---|---|---|---|
| Claude Code | yes | yes | yes | yes |
| Art | drawn in code (a deliberate flat style) or your own PNG/PSD art | OpenAI, Gemini, xAI or OpenRouter key in your environment; **you pay per image and are asked before every paid batch** | Codex CLI logged in with ChatGPT (`codex login`); billed to your plan, no key | an A1111-compatible Stable Diffusion server on `127.0.0.1`; free, stays local |
| What leaves your machine | nothing | prompts (and reference images) to the provider | prompts and reference images to OpenAI via Codex | nothing |

Base kit (all profiles):

| What | Needed for |
|---|---|
| Python 3.11+ (installed for you on Windows by `check_env.ps1 -Install`: Python 3.12 per user; or python.org, uv-managed or the Microsoft Store build) with `scripts/requirements.txt` | packing, sound, checks, the store upload's QR code. Store build: its packages live in the user site, so run scripts as `python <script>`, never `python -I` / `-s` (they hide Pillow); `check_env` says so. Homebrew and Debian/Ubuntu Python refuse a global `pip install` (PEP 668): use a venv, `python3 -m venv ~/.wowcube/venv`, then `. ~/.wowcube/venv/bin/activate` and `pip install -r <skills>/scripts/requirements.txt`; activate it before you start Claude Code |
| The bundled simulator (prebuilt in `simulator/dist`; the binaries go to `~/.wowcube/sim/<version>/<os>/`) | the agent's hidden automatic checks of every build (an internal tool, not a way to play): `tools/sim/get_sim.ps1` / `get_sim.sh` installs the prebuilt simulator this plugin carries (no download, nothing to build) |
| Windows: Visual Studio 2022 Build Tools (C++ x64) + `clang-cl` (LLVM) | compiling the game into the simulator's plugin |
| macOS: Xcode command-line tools | the game plugin |
| Linux: g++ or clang++, the SDL3 runtime, OpenGL/EGL, Xvfb (`xvfb-run`) | the game plugin and hidden runs |
| ARM GNU toolchain (`arm-none-eabi-g++`) | every game build: `build_game.*` first compiles the game with the cube's compiler and flags (the device `-Werror` check) before the simulator plugin; and the device `.oct` (all OSes) |
| CMake, Ninja | the device `.oct` (all OSes) |
| ffmpeg | sounds, videos |
| Node.js + Playwright (optional) | browser prototypes and demo videos |
| A WowCube and a phone with the WowCube app | installing and playing the game (scan the QR code) |

`<skills>/scripts/check_env.ps1` / `check_env.sh` checks all of it. On Windows `check_env.ps1 -Install`
adds what is missing with quiet winget installs (Python and its packages included), and only after you
agreed; winget asks you to accept the package and source agreements unless you add `-AcceptAgreements`.
It lists anything it could not install with where to get it; restart Claude Code afterwards. Nothing is
installed or downloaded behind your back.

## What runs where

| Where | What |
|---|---|
| Claude Code (your plan or API key) | the design, prompts, code, reviews and reports; subagents for coding and reviews |
| Your machine | the hidden simulator (no window, no sound), packing, sound processing, the device build; all files stay in your workspace |
| Codex CLI or an image provider | drawing the art, only if you chose it; a paid provider only after your yes for that run |
| The internet | CC0 sound downloads, only if you asked for recorded sounds and approved the list; tool installs, only after you agreed |
| The WowCube store | the finished `.oct`, only after your yes: it returns the install link and QR code |
| Your phone and cube | you scan the QR code; the WowCube app installs the game on your cube |

The simulator is the WowCube engine built once for your PC (Windows, Linux, macOS); the game is
compiled into a small plugin it loads. It is the agent's internal checking tool: its runs are hidden and
silent, and you play the game on your cube. Details: `simulator/README.md`.
No other checkout is needed: the public game API (`api/`: what a game compiles against), the prebuilt simulator
(`simulator/dist`) and the device build kit are in this plugin. The engine and simulator sources are not: they are
private (wowcube/OCT_cube-sim-sources), and the plugin carries only their build outputs and the generated API.

## Glossary

| Word | Meaning |
|---|---|
| **Module** | one of the eight corner blocks of the cube; each has its own processor, speaker and three screens |
| **Face** | one of the six sides of the cube: 2x2 = four screens, each on a different module |
| **Screen** | one 240x240 display; 24 in total. Sprites are drawn at double size, so art is authored at half size |
| **Twist** | turning one layer (half of the cube) by a quarter turn; it moves 4 modules and 12 screens |
| **Half twist** | starting a twist and letting it snap back: the game is told, nothing moves (a custom action) |
| **Tap** | knocking on a face; the game learns the face and, on current firmware, the screen |
| **Tilt** | holding the cube at an angle; the game reads gravity and which face is up |
| **Shake** | always returns to the launcher; never a game control |
| **Game file (`.oct`)** | the installable game, like an app on a phone |
| **Install QR code** | the code you scan with your phone to install the game from the WowCube store |

## How the pipeline works

You talk to `cube_orchestrator`; it drives the rest.

| Step | What happens | Output |
|---|---|---|
| Setup (first use) | detect the machine, four questions, one permission to install the build components | the two profile files |
| 1. Design | a design document from your idea, or yours imported; checked against game-feel rules for its genre | `plans/<game>_gdd.md` |
| 2. Plan | small testable implementation steps + the list of pictures and sounds | `plans/<game>_prompts.md`, `plans/<game>_assets.json` |
| Infra check | the game folder is created, the game builds for the simulator and shows the template | `app_<game>/` |
| 3. Assets | **art style approved by you**, art drawn and reviewed, sounds sourced, icon, packed | `assets_<game>/`, packed files in `app_<game>/` |
| 4. Code | per step: coder, code review (one or two reviewers by tier), a look at all 24 screens in the hidden simulator, a playtest, fixes | `app_<game>/src/app_<game>.h` |
| 5. Deliver | the device `.oct`, verified; store upload (one yes) with the install QR code; video, balance passes on request | `dist/app_<game>.oct` |

Verification tiers (`lite`, `standard`, `full`) set how many reviewers, playtests and fix rounds each
step gets; the look at all 24 screens is never skipped. Details: `docs/pipeline-flow.md`,
`skills/cube_orchestrator/SKILL.md`, `skills/cube_orchestrator/references/RUN_MODES.md`.

## Safety

No windows over your screen, no sound from test runs, no keyboard or mouse input to your desktop,
processes stopped only by their PID, no commits, pushes or messages unless you ask, no credentials
typed, no paid API without your explicit yes, downloads only after you approve them
(`skills/cube_orchestrator/references/AGENT_SAFETY.md`).

## Repository layout

```
.claude-plugin/                 plugin.json, marketplace.json
skills/
├── cube_orchestrator/          the entry point: modes, tiers, stage routing, Mod mode, delivery
├── wowcube-setup/              first-run detection and the profile (references/PROFILE.md)
├── wowcube-tools/              the toolbox without stages
├── cube_game-designer/         design document (new or imported); references/GAME_FEEL.md
├── technical_prompter/         implementation steps + the asset list
├── cube_art-director/          style-locked art with strict QA (also standalone, for artists)
├── cube_asset-builder/         art, sound, icon, fonts -> packed app assets
├── wowcube-boilerplate/        scaffold, simulator builds, device .oct
├── cube_verifier/              code reviewers, screen review, playtest
├── wowcube-html-prototype/     optional browser prototype of the mechanic (Alex Poshivalov)
└── wowcube-demo-video/         1920x1080 demo videos (Alex Poshivalov)
scripts/                        packer, manifest validator, sound_kit, device build, repack, checks,
                                store upload + QR (store_upload.py), change history and undo (history.py)
api/                            the public game API: headers games compile against, module and plugin glue
simulator/                      the prebuilt simulator for every OS (dist/) and its manual (README.md)
tools/                          hidden simulator helpers
templates/app_ai_template/      the app template; API.md (engine facts and limits), src/app_ai_template.h (annotated API)
src/app_structure_example.h     the skeleton a new game header starts from
docs/pipeline-flow.md           the pipeline as a diagram
```
