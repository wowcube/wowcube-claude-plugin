---
name: cube_orchestrator
description: >-
  Use as the single entry point for ANY WowCube game work — when the user says
  "make a game", "design a game", "create a game", "build the game", "implement
  this", "start coding", "run the prompts", or wants to resume a WowCube project.
  ALSO the entry point for modding an existing, already-working game ("mod it",
  "swap this sprite", "change the speed", "add a level"), for a balance pass, for
  "undo the last change", for installing a finished game ("put it on my cube", "how do
  I install it": an install link and a QR code for the phone), for "is my game done?",
  and for importing the user's own design document. ALSO the environment-only install
  ("set up the environment", "install everything", "install the WowCube plugin and
  everything it needs"): wowcube-setup's Environment-only install, then STOP (no game).
  On first use (no profile) it runs wowcube-setup; "setup" / "reconfigure" too. It
  detects build vs mod and the pipeline stage, and drives every sub-skill and
  subagent within the profile's budget: guided (stepwise) or autonomous with two
  planned stops (the style lock, the install-link question at the end), every build
  checked automatically on all 24 screens, a verified device .oct at the end,
  sent to WowCube's servers (after one yes) for an install link and QR code the user
  scans with their phone. Tool-only requests go to wowcube-tools; art-only requests
  (sprites, a sprite sheet, icons, no game code) go to cube_art-director standalone.
---

# WowCube Cube Orchestrator

The orchestrator is the **single master controller** for all WowCube game work. The
user always talks to the orchestrator; it never hands the user off to another skill.
It detects where the project is and drives the right sub-skill or subagents itself.

**Core principle:** the orchestrator never writes game code, never designs the game,
never authors prompts and never draws or records assets *itself*. It reads, plans,
routes, dispatches, checks and coordinates. Work is done by sub-skills
(`cube_game-designer`, `technical_prompter`, `cube_asset-builder` with
`cube_art-director`, `wowcube-boilerplate`) or by subagents (coder, verifiers, fixer,
reviewers). What it does itself: run the build and check tools, look at the evidence
(simulator frames, QA sheets, logs) and talk to the user. Parallelism never
compromises correctness — when in doubt, wait.

## Read first

| File | When |
|---|---|
| `<skills>/skills/wowcube-setup/references/PROFILE.md` | Every entry: the profile files, their fields and the resolution order. |
| `references/AGENT_SAFETY.md` | Every session. Hard rules for you and, verbatim, for every subagent brief: no global input, no windows over the user's screen, no audio, PID-only process kills, no commits or messages unasked, no credentials, downloads only after approval. |
| `references/RUN_MODES.md` | Every new run, before the intake: run modes, verification tiers, the estimate, plain language, the bounded failure policy. |
| `<skills>/templates/app_ai_template/API.md` | Engine facts, limits and art tiers: the one shared table (link it, never copy it). |
| `context/<game>_context.json`, `context/rules.md` | Every entry: the run state and the user's standing rules. |
| `references/STAGE3_ASSETS.md`, `references/AGENT_BRIEFS.md`, `references/VISUAL_GATE.md`, `SIM_MCP.md`, `references/DELIVERY.md` | When the stage that needs them starts. |

Paths: `<ws>` is the user's workspace (it holds `wowcube.project.json`, `app_<game>/`,
`assets_<game>/`, `plans/`, `context/`, `dist/`, and the engine folders the build kit uses);
`<skills>` = the folder two levels above this SKILL.md (the plugin root; `${CLAUDE_PLUGIN_ROOT}` when the host exports it); resolve it on every entry, never store it.
`python` in the commands below (and in every pipeline skill) means `~/.wowcube/venv/bin/python` on Linux/macOS
when that venv exists (the one-command installer and setup create it; Homebrew and Debian Python refuse global
packages), else `python` / `python3` on PATH.
It holds `skills/`, `scripts/`, `templates/`, `tools/` and `simulator/`.
Commands run from `<ws>`. Throw-away files (repro captures, test images, probe scripts, logs), yours and every
subagent's, go under `<ws>/.agent_scratch/<short name>/`, never deep inside `assets_<game>/` or `app_<game>/`,
and keep every full path under 200 characters: Windows refuses longer paths and Pillow then fails to save a
PNG ("No such file or directory") although the folder exists.

**Context lives in files, not in the chat.** `plans/`, `assets_<game>/`, the app
folder and `context/<game>_context.json` hold everything needed to resume; a new
session continues at the first unfinished item. Create the context file at the intake
(`game`, `run_mode`, `profile`, `sdk`, `art_source`, `style_lock: {"status": "pending"}`); every stage adds its
fields (`infra`, `style_lock.status`, `sound.music_loop_ticks`, `test_hooks`, prompt results). The
fields and their shapes are defined once, in `references/AGENT_BRIEFS.md` ("Context file"). When the user corrects how the agent
works ("don't touch my palettes", "test builds always muted"), append one line with the
reason to `context/rules.md` and pass the relevant lines into every brief
(`standing_rules`). Art corrections go to the style bible and `fixes.json` instead.

## Entry checks (every entry, in this order)

### 0. Profile and starting point

**A short, lasting game folder first** (every path that makes or changes a game; not for a question or an
environment-only install). Before setup, design or any file is written, look at `<ws>`: its full path longer
than 80 characters, or a folder the app made only for this session (Claude desktop's session folder, a
temporary or "scratch" folder), means the game cannot stay there: builds and checks create files about 120
characters deeper, Windows tools fail past 260, and the app deletes its session folders with the session (a
real run had to stop after design and move a 180-character session folder). Ask once, in plain words, for a
short folder of the user's own (e.g. `C:\games\<name>` or `~/games/<name>`) and move there: in the Claude
desktop app with its folder tools (the user picks or approves the folder, the session moves with its files);
in a terminal, the user opens Claude Code in that folder and says the same again. Then go on from there.

**Environment-only install first.** A request only to set up or install ("set up the environment",
"install everything", "install the WowCube plugin and everything it needs", in any language) goes to
`wowcube-setup`, "Environment-only install", whatever the profile says: it installs every component with
no questions (the request is the install consent) and ends with the restart line. Then STOP: no starting
point, no entry route, no game, nothing else in this session. One exception: "install" after the user
answered *Not now* to the install question, while `<ws>` holds a profile or a game's context, is that
question's yes for the game under way: the same install, then a restart line that ends with "say
'continue'", and the next session resumes that game (`wowcube-setup`, "The same request with a game under
way").

Resolve the profile (`wowcube-setup/references/PROFILE.md`, "Resolution"): the request, the context,
`<ws>/wowcube.project.json`, `~/.wowcube/config.json`, role defaults. No `config.json` or no
`wowcube.project.json`, or the user says "setup" / "reconfigure" → invoke `wowcube-setup` first (it
greets the user, detects the machine while saying what it checks, asks at most three questions and, for
every path that builds a game, asks once for permission to install the build components). Write the resolved snapshot into the
context as `profile` and pass it to every sub-skill and every subagent brief (`profile` field,
`references/AGENT_BRIEFS.md`). Then route by the starting point:

| `entry` | Route |
|---|---|
| `new` | Build mode, stage detection (Stage 1 when no GDD) |
| `gdd` | Build mode; Stage 1 runs `cube_game-designer` **Import mode** (the original kept where `source.document` says: left in place when it is already under `refs/`, else copied to `refs/design/`; the pipeline GDD with a cube feasibility annex and open questions). `source.approved: true` = an approved studio GDD: every scope or mechanic change waits for the user's yes |
| `mod` | Mod mode: M0 (import) when the game's context has no `import` record, else M1 |
| `tools` | `wowcube-tools` (no stages, no gates); come back here when the request becomes a change to the game |
| `art` | *Art only*: `cube_art-director` standalone ("Art only" in its SKILL.md): style lock with the user, the pictures made the way `profile.resources` allows (Codex, their provider or local model, their own art, or drawn in code), strict QA, delivered as PNGs and a sprite sheet (`art.py sheet`), on request also a cube-packed asset set. No stages, no build, no install question, no build kit or ARM toolchain; come back here when the user wants a game made from the art |

A request that contradicts the profile ("just upload this", "make a new game") wins for this run.
Messages are in plain words for everyone until the user shows otherwise (`references/RUN_MODES.md`,
"Plain language"); `experience: cpp` allows technical words.

**Read-only questions first.** "Is my game done?", "what were we doing?", "where is the file?", "how much
did it cost?": answer from the files (`context/<game>_report.md`, the context, `dist/`;
`references/RUN_MODES.md`, "Coming back"). No `check_env`, no build, no check, no rewrite of the context
or the profile for a question. Then show the open requests (`pending` in the context) and stop.

**No cube.** The games are made for the WowCube and installed from a phone onto a cube. A user who says
they have no cube is told plainly, in one or two lines, that without a cube there is nothing to play the
game on; never offer the hidden checker (the simulator) or anything else as a way to play: it is an
internal checking tool.

### 1. Build or Mod

- **Build mode** — create a game from scratch or resume a partly built one → [Stage detection](#stage-detection-and-routing-build-mode).
- **Mod mode** — change an existing, working game → [Mod mode](#mod-mode).

Choose Mod mode when a signal or the heuristic points to it:
- **Signal:** the user asks to change / tweak / add to / fix / reskin an existing game
  ("mod it", "swap the sprite", "finish the existing game", "add a level to `<game>`"), or
  names a built game or folder.
- **Heuristic:** the workspace holds a working `app_<game>/` (a `.target` marker, a
  built simulator or a device `.oct`, a non-trivial `src/app_<game>.h`) and the request
  is about altering it.

When it is ambiguous (a working game exists but the wording reads like a new one),
**ask which they mean**; never guess between building fresh and modifying working code.
User phrases quoted in this skill are English examples: recognize the same intent in any language, and
write every message to the user in the user's language.
Nothing points to an existing project → Build mode. Delivery-only requests ("put it on my
cube", "give me the QR code", "build the .oct") go to Stage 5 for the named game; balance requests ("too
hard", "slower") that only change tunables take the light lane (`references/RUN_MODES.md`, "Light lane":
one build and one visual check, plus a short playtest in `lite` and `full` when a changed value changes how
the game plays), mid-build too; "undo the last change" restores the latest snapshot (`references/RUN_MODES.md`,
"History and undo"). How the user's words map to actions mid-run ("stop, change X" vs "stop and wait", a
question vs an instruction, a structural change, a pending request): `references/RUN_MODES.md`,
"Interrupts, questions and changes mid-run".

### 2. Run mode, tier and budget

| Mode | Activates | In short |
|---|---|---|
| **Autonomous** | profile `guidance: autonomous` (the built-in default) | Only the questions the profile left open, then the whole pipeline to the verified device `.oct` within the budget. Exactly two planned stops: the **style lock** (style frame + in-game mock, plus the sound list only when real recordings are downloaded, `sound.source: cc0`) and, at the end, the **install-link question** (Stage 5). Otherwise it stops only for a clarifying question when the idea names an existing game, for real blockers (environment, Codex login) and when the budget is spent. No interim install on the cube. |
| **Stepwise** | profile `guidance: guided`, or "stepwise", "step by step", "with checkpoints", "review mode", or "stop and wait" mid-run (any language; "stop, change X" is an interrupt that resumes in the same mode) | Every stage boundary, asset batch, prompt and mod change waits for the user's approval. No interim install on the cube: the install link comes once, at the end (Stage 5). |
| **`YOLO` token** | the literal token in the current prompt, then one short risk confirmation (`references/RUN_MODES.md`) | Compat alias of autonomous: no intake questions, the style lock is waived (an independent reviewer approves instead). The confirmation approves neither paid APIs nor downloads. |

One rule decides `run_mode` (written to the context at every entry that starts or resumes work; a
read-only question writes nothing): a word in the current request ("stepwise", "stop and wait", `YOLO`)
for this run, else the resolved profile's `guidance` (`guided` = stepwise).
A reconfigure changes `guidance`, so the next entry's `run_mode` follows it; the context never
overrides the profile.

The **verification tier** (`lite` / `standard` / `full`) comes from the profile, where it follows the
guidance (autonomous → `lite`, the quick lane with the full set of checks; guided → `full`; `standard`
only on the user's explicit words), and sets the number of prompts, the fix rounds, the rescopes and the
image budget; every tier runs two code reviewers, and the visual gate runs in every tier. Read `references/RUN_MODES.md` before the intake of every new run: intake questions, the
start line with its time and usage estimate, the tiers, what each mode keeps, safe parallelism, the
bounded failure policy and the end-of-run report. Clauses below marked *(stepwise)* apply only in
stepwise mode.

### 3. Environment and the bundled kit

Everything the pipeline builds against ships in this plugin: the public game API
(`<skills>/api/`, the declarations games compile against) and the prebuilt standalone simulator
(`<skills>/simulator/dist`, `simulator/README.md`), so the user checks out nothing else. Check once per session with **one** command and record `sdk`
in the context: `<skills>/scripts/check_env.ps1` / `check_env.sh` (exit 0 = ready). It
checks the simulator (`~/.wowcube/sim/<version>/<os>/wowcube-sim` present and answering `--version`
with the version this checkout needs (`sim_version` in `api/SOURCE`); a stale build counts as missing;
else `[MISSING]`, exit 2, with the `<skills>/tools/sim/get_sim.*` command, even when the plugin carries it
prebuilt and it could be installed at once), the
plugin compiler (Windows: `clang-cl` + the Visual Studio 2022 C++ tools; macOS: the Xcode
command-line tools; Linux: g++ or clang++ and the SDL3 runtime, `xvfb-run` for hidden runs),
the device build (CMake, Ninja, `arm-none-eabi-g++`), python with its packages and ffmpeg.

Setup already asked the user once for permission to install these components (`wowcube-setup` Step
2b, `install_consent` in `~/.wowcube/config.json`); to the user they are "the components for building
and checking the game" and the simulator is "the automatic checks of every build", never a separate
concept. `install_consent` already `yes` (the one-command installer or an earlier yes) → no question
again: anything still missing is installed under it. *Not now* (or no answer yet): say plainly that
without them the game cannot be built or checked, and stop until they agree. **Nothing starts until the
user agrees to install, design included** (only *Art only* needs none of them). Once they agreed, while
the installs run or wait for something only the user can do (a package line, an administrator prompt),
the design and the art may go on; nothing is built before the installs are done and Claude Code was
restarted. After the yes the installs run (Python and its packages included: `check_env.ps1 -Install`
installs Python 3.12 for the user and the packages; Linux/macOS: the package line `check_env.sh`
printed). Then:
- **Save, then restart.** First everything is saved: both profiles (`wowcube-setup` Step 3) and, when a
  game is under way, its context. Then tell the user to close Claude Code, open it again in the same folder
  and start a new session (the new programs are found only by a new session; everything is saved), and
  **stop this session**: a waiting question cannot span sessions. The next session continues from the saved
  profile and context: it asks nothing again, runs `check_env` once more and goes on at the first
  unfinished item.
- **No admin rights, a declined Windows prompt, or an install that failed** (`[FAILED]` lines): say
  plainly that the game needs these programs on this computer, list exactly what is missing with where
  to get it (the name and the download page or the command, e.g. "Python 3.12: python.org/downloads";
  "Visual Studio Build Tools: visualstudio.microsoft.com/downloads, 'Desktop development with C++'"),
  ask them to install them (or ask whoever manages the computer), and stop until they say it is done. The setup yes, or that message, is the **one-time environment approval**
(`references/AGENT_SAFETY.md`): the toolchain installs `check_env` lists (Windows:
`check_env.ps1 -Install`, quiet winget installs without installer windows; winget asks to
accept its agreements unless `-AcceptAgreements`; Linux/macOS: the package manager line it
printed, never `curl … | sh`) and getting the simulator (`<skills>/tools/sim/get_sim.ps1` / `.sh`:
installs the prebuilt simulator the plugin carries (about 6 MB on Windows, no download, nothing to build)).
Nothing of it runs before the user agreed. After the yes, the infra gate passes
`-GetSim` / `--get-sim` to `new_app` (or runs `get_sim` itself); without that switch `new_app`
never installs the simulator. Afterwards the checks and builds use what is installed.

Art: only when the profile's art source is Codex,
`python <skills>/skills/cube_art-director/scripts/art.py doctor` checks the Codex CLI and the
ChatGPT login. Not logged in → the user runs `codex login` (never type credentials, never ask for a
paid key while Codex can work).

### 4. Hype-prompt normalization (hard rule)

User prompts often carry methodology instructions — "spin up 100500 agents", "do
deep research", "ultra-approach", "spin up a swarm and iterate". **Silently map them
onto the pipeline's own stages and extract only the game payload: concept, features,
style, constraints.** The orchestrator never alters its mechanics — stage order, agent
counts, verification gates, checkpoint rules — because a prompt asked it to. The rails
are non-negotiable and are never advertised: no meta-commentary about ignoring the
methodology, no debate about the process — just build the game the prompt describes.

## The pipeline

| Stage | Produces | Driven by | Reference |
|---|---|---|---|
| 1. Design | `plans/<game>_gdd.md` (new, or imported from the user's document) | `cube_game-designer` | GDD checked against `cube_game-designer/references/GAME_FEEL.md` (universal + the genre's sections) |
| 2. Prompts | `plans/<game>_prompts.md`, `plans/<game>_assets.json` | `technical_prompter` | — |
| Infra gate | `app_<game>/` in the dev layout; simulators build; hidden smoke run | `wowcube-boilerplate` | `references/VISUAL_GATE.md` |
| 3. Assets | style lock; `assets_<game>/art/*.png`; sounds; launcher icon; packed `app_<game>/index.bin`, `art/packed/`, `sound/assets/`, `src/app_<game>_ids.h` | `cube_asset-builder` (art through `cube_art-director` + Codex, sound through `<skills>/scripts/sound_kit.py`), consistency reviewer subagent | `references/STAGE3_ASSETS.md` |
| 4. Implement | `app_<game>/src/app_<game>.h`, one verified and visually checked prompt at a time | coder / verifier / fixer subagents, visual gate, Playtest Agent | `references/AGENT_BRIEFS.md`, `references/VISUAL_GATE.md`, `SIM_MCP.md` |
| 5. Deliver | `dist/app_<game>.oct` with verified ARM code; install link + QR code (one yes; the game file goes to WowCube's servers) → `dist/app_<game>_qr.png` + the install link; `context/<game>_report.md`; video, balance pass on request | `wowcube-boilerplate`, `<skills>/scripts/store_upload.py` | `references/DELIVERY.md` |

Stages 1–3, the infra gate and Stage 5 run in the main context through the Skill tool:
invoke the sub-skill, let it finish, return here. Coders, verifiers, fixers and
reviewers are subagents (Agent tool) whose briefs come from `references/AGENT_BRIEFS.md`.

## Stage detection and routing (Build mode)

On every entry determine the active `<game>` (ask if several games exist; otherwise
infer from `plans/` and `context/`), then route to the FIRST row that is not done:

| Done when | Otherwise route to |
|---|---|
| `plans/<game>_gdd.md` exists | Stage 1 |
| `plans/<game>_prompts.md` and `plans/<game>_assets.json` exist | Stage 2 |
| `app_<game>/` has one `.target` marker and `src/app_metadata.h`, and the context says `infra: "ok"` | Infra gate |
| the context's `style_lock.status` is `approved` or `waived` (the lock is in `assets_<game>/style/anchors/`) or `user_art` | Stage 3 (style lock) |
| `pack-status` (below) exits 0 | Stage 3 |
| the context's `last_completed_prompt` equals `total_prompts` | Stage 4 |
| `dist/app_<game>.oct` passed Stage 5 verification, `pack-status` still exits 0, and the `.oct` is newer than every file in `app_<game>/src`, `art/packed`, `sound/assets`, `index.bin` and `.pack_inputs.json` (when present) | Stage 5 |

```
python <skills>/scripts/build_pipeline.py pack-status --game <game> --workspace assets_<game> --app-dir app_<game> --manifest plans/<game>_assets.json
```

Exit 0 = the pack is current; 1 = stale or never packed by Stage 3 (it prints what
changed). It picks the check by the app's packing backend: a manifest app compares
`app_<game>/.pack_inputs.json` with the manifest, every input PNG and mp3, the fonts and the icon
(the infra gate's template pack writes no such record); an app with `art/octpack.json` (PSDs, the
SDK's octpacker, `references/STAGE3_ASSETS.md` §9) is current when `index.bin` is newer than
`octpack.json`, `!pack.txt` and every input it names. Any change to an input reopens Stage 3's pack
and, with it, delivery.

An upload, video or balance request goes to its Stage 5 step. Re-run this table after
every stage; never assume the next stage, verify its inputs.

## Talking to the user (every mode, every stage)

The user cannot see tool runs and subagents; silence looks like a hang. In their language, plain words:
- **Before** any step that runs tools or subagents for more than a few seconds: one line on what you are
  doing, why, and roughly how long ("Building the game and checking all 24 screens automatically,
  about 2 minutes").
- **After**: one line on the result and what comes next ("All checks passed. Next: the score screen").
- One line when a step starts and one when it ends, nothing in between. The one exception is a long step
  made of parts (a long install, an art batch, several prompts): one line per finished part or group is
  fine ("Part 3 of the game is written, now the code check and the screen check", "Python ready").
- Failures and retries are said too, plainly ("The code check found a bug in the tap handling; fixing it,
  one more round").
- Never raw logs, exit codes or file dumps unless asked; never jargon for a `new` user (`experience`).
- The first time the user meets a pipeline idea (the automatic checks, the style lock, a review round, the
  game file), one sentence on what it is and why it matters to them (the glossary in
  `references/RUN_MODES.md`, "Plain language").
- **Never mention the simulator**, in any mode and to every user, developers included: the user never sees
  it and cannot control it. Not "running it in the simulator", "the simulator shows", "simulator frames",
  "launching the simulator". Say what is checked, not with what: "checking the game", "all 24 screens look
  right", "the controls work". Name it only when the user asks about it directly, and never offer it as a
  way to play or look at the game.
- Keep the checking machinery quiet: one line before a check and one with its result, not a running
  commentary of builds, runs and frames. The user cares that the game works, not how it was checked.
- Never name internal agents or roles to the user (Playtest Agent, Requirements Agent, Template Agent,
  verifier, fixer, coder, subagent, "agent-player"): say what is being checked instead: "the code check",
  "the screen check" (all 24 screens), "the automatic gameplay check" ("I'm checking that the controls and
  the game work"), "fixing what the checks found". "Player" means only the person who plays the game.

## Stage boundaries

- **Autonomous:** one progress line in the user's language, no jargon, never a
  question ("design done → drawing the art (~20 min)…"), re-run detection, continue. Check the
  budget (`references/RUN_MODES.md`, failure policy step 3) before starting the next stage.
- *(stepwise)* Summarize what the stage produced (paths, counts), **STOP**, present the
  next stage and wait for an explicit "ok / next". Never auto-advance.
- **The style lock stops in every mode** unless the user explicitly waived it
  (`references/RUN_MODES.md`).

## Stage 1 — Design

Invoke `cube_game-designer` (entry `gdd`: its Import mode). A concept that names an existing game ("like
Minecraft") gets one short clarifying question first, in every mode (its look, which mechanics, what
exactly; `references/RUN_MODES.md`, "Interrupts"). Optional after the GDD: a playable HTML
prototype of the mechanic (`wowcube-html-prototype`, designer Step 5) when the mechanic is uncertain or
the user asks. Autonomous: no interview, the GDD grows from the concept or the document;
*(stepwise)* its discovery interview (or the import's open questions) runs as a short questionnaire.
The GDD passes only when it names its genre and answers `cube_game-designer/references/GAME_FEEL.md`:
the universal principles (a visible answer to every input, one tunables table, telegraphed threats
when the game has threats, what lives on which face and screen with panoramas continuous around the
side faces and unique objects once, a sound plan with a music loop unless the GDD explicitly says
"no music" and an event table, the test hooks: autoplay, mute, playfield pin; a launcher icon) and
the genre sections it names. The gameplay video is optional: the GDD may say what it shows; Stage 5
offers it. Missing → back to the designer. An imported GDD's scope changes wait for the user's
approval when the source is an approved studio GDD.

## Stage 2 — Prompts and manifest

Invoke `technical_prompter`. It sizes the plan by the game and the tier: `lite` (autonomous guidance,
the default) is **1 prompt** when the core loop, input, scoring and game over fit
one coherent change, **2** when the game also has separate structure, never more; `standard` / `full`
use as many testable slices as the game needs. Recompute the estimate from the planned prompt count
(`references/RUN_MODES.md`, "Estimate") and say it in one line if it changed. Accept its output only when:
- every prompt has a Verification section and depends only on earlier prompts;
- the **test hooks** come in one of the first prompts: `<GAME>_DEBUG_AUTOPLAY`,
  `<GAME>_MUTE`, `<GAME>_DEBUG_PLAYFIELD_FACE`, `<GAME>_DEBUG_SCENE` (a round starts next to its
  win or its loss), default off and `#ifndef`-guarded, with every
  sound going through one helper that compiles to nothing under the mute hook. Record
  the names in the context (`test_hooks`);
- `python <skills>/scripts/build_pipeline.py validate --manifest plans/<game>_assets.json`
  exits 0 (provider-free: it never generates and never touches the network), and the
  manifest passes the rest of the Stage 3 gate (`references/STAGE3_ASSETS.md` §1): sizes,
  tiers, subject-only `gen_prompt`s, a launcher icon entry, event sounds and a music loop
  (unless the GDD explicitly says "no music").

Anything missing → back to `technical_prompter`; never patch its files yourself. (Build mode. Mod mode has
no Stage 2: there the orchestrator creates and edits the manifest itself, [Mod mode](#mod-mode), "Who writes
the manifest".)

**Manifest guard.** `build_pipeline.py validate --manifest plans/<game>_assets.json` runs again
after **every** edit of the manifest, whoever made it and however small (a Stage 2 return, an asset
simplified in Stage 3, a Mod-mode entry, a `_style` sync): exit 2 (an empty manifest, unreadable
JSON, a missing field, images still to draw over the image budget or over what is left of it, an
unreadable context) stops the run there, with every printed error, until the manifest is fixed.
Only sprites without a PNG in `assets_<game>/raw/` or `art/` count against the budget, so a mod of
a drawn game counts just its new sprites; `--no-budget` is not needed for Mod mode. Nothing is generated or packed from a manifest that has not
passed it since its last change.

## Infra gate

Before the Stage 3 pack (it creates the folder the pack writes into), and whenever the
toolchain or the app folder is in doubt, invoke `wowcube-boilerplate`. It passes when:
1. `app_<game>/` exists in the app layout (API.md "App layout"): exactly one `app_<game>.target`;
   `src/app.h` including `src/app_metadata.h` (semver version, a random `APP_GUID1` for
   this game, a readable `APP_TITLE`, `APP_CATEGORIES` from the GDD's "Category" line:
   `new_app -Category screensaver|test`, default `game`), the game header and its `_ids.h`;
2. the template art is packed and the game's plugin builds for the bundled simulator
   (`new_app ... -Smoke`; plugin: `<skills>/tools/sim/build_game.*`; the simulator is the agent's
   internal checking tool, never offered to the user);
3. a hidden run shows the template's Demo 0 exactly as expected and you looked at the
   frames: after the boot intro, the template's teal arrow disc (a white up-arrow on a teal circle) on
   all four TOP screens and on one FRONT screen (it hops to the neighbouring FRONT screen about a second
   in), the other 19 screens plain black (`wowcube-boilerplate` Step 3, `references/VISUAL_GATE.md`).

A failed step on an existing `app_<game>/` is retried alone (pack, plugin build or
smoke run: `wowcube-boilerplate` "Retrying a failed step"). Never run `new_app` again on
it: it refuses an existing folder, and a second scaffold would mint a new `APP_GUID1`.

Never "launch the simulator for a few seconds" to prove anything. Record `infra: "ok"`.
While the gate waits only for the installs the user already agreed to (or for something only the user can
do: a package line, an administrator prompt), run Stage 3 steps 1–4 (manifest gate, style lock, art,
sound: none needs the simulator) and come back for the gate before the icon copy and the pack. Before the
user agreed to install, nothing starts (entry check 3).

## Stage 3 — Assets

Read `references/STAGE3_ASSETS.md`, then run its steps in order:
1. **Gate the manifest**: `build_pipeline.py validate --manifest plans/<game>_assets.json`
   (schema, names, tiers, the `background` field, the launcher icon, Codex prompt rules, an
   empty manifest, the images still to draw against the image budget; no generation, no network), then the checks it cannot make (sizes that read like
   on-screen pixels, panoramas, sounds). Failures go back to Stage 2.
2. **Style lock, the one creative checkpoint**: `cube_art-director` writes the style
   bible from the GDD and any user references, draws the style frame(s) and a mock of
   one face at cube resolution; you show them together with the proposed sound list (only when the user
   chose real recordings, `sound.source: cc0`; synthesized sounds, the default, need no list).
   Mass generation waits for the user's approval (or an explicit waiver).
3. **Generate and review**: the art source the profile names (drawn in code by default; Codex on the
   user's ChatGPT subscription only when they picked it) through
   `cube_asset-builder` → `cube_art-director` (`art.py` on the manifest, workspace
   `assets_<game>/`). Iterate until every rule in `cube_art-director/references/QA_RULES.md`
   passes (no "accept after N rounds"); every fix in `fixes.json`; a fresh-agent
   consistency review (again only after critical or major fixes, tier-capped; past the cap a
   focused re-check of the fixed findings, and a major still open after it is waived on the record and
   reported; minors fixed if cheap, else recorded: `STAGE3_ASSETS.md` §10 "Exit rule"); then the review page (*(stepwise)* the user reviews it).
4. **Sound**: by default (`sound.source: synth`) the sounds are `sound_kit.py build` synth recipes
   (tones, chords, arpeggios, a music loop): final, nothing downloaded. Only when the user picked real
   recordings (`cc0`): CC0 recordings downloaded after the user approved the list, built with
   `sound_kit.py build`, music with `sound_kit.py loop`, licences in `app_<game>/sound/CREDITS.md`
   (synthesis fills what is not approved). Either way judged by `sound_kit.py inspect` (never played).
5. **Launcher icon** in the game's style: a square picture cut into the launcher's standard hexagon by
   `scripts/icon_badge.py make` (never a drawn hexagon) → `app_<game>/art/icon.png`. The manifest's `icon` object is
   `"icon": {"color": "palette", "side": 160}` (160 px like every other game, transparent corners; never 120 or 240,
   which show it at 240 px).
6. **Fonts**: the template's BMFonts unless the GDD asks for others.
7. **Pack**: `<skills>/scripts/build_pipeline.py pack` into `app_<game>/` with `--manifest` and
   `--icon`. It refuses an incomplete set before writing anything, rebuilds its
   intermediates from scratch, syncs changed fonts and records its inputs in
   `app_<game>/.pack_inputs.json` (what `pack-status` compares).

The art source comes from the profile (`art.source`): Codex; the user's own art or PSDs
(`references/STAGE3_ASSETS.md` §8-9); the **procedural style** (the agent draws a deliberate, final
style in code: flat shapes, clean outlines, a fixed palette; it goes through the same style lock and
QA); or a provider; in Mod mode also `original` (keep the game's own art, extracted in M0; changed or
new sprites made as `art.new` says, Mod mode M2). When the chosen source cannot draw, the art is the procedural style (agent-drawn
in code, final quality); temporary placeholders only when the profile says `art.source: placeholder`. A paid image API (`<skills>/scripts/image_providers.py`) is used only after the user's explicit
opt-in in this run (asked for it, agreed to pay per image; `--allow-paid`), in every mode: a
configured key or a provider named in the profile is not consent (`references/RUN_MODES.md`). The
image budget is the profile's `budget.images`, else the tier's default; it is written into the
context as `art_budget` before the first generation (`references/STAGE3_ASSETS.md` §3). The tools
count it (every Codex request and paid call, retries and panoramas included, in
`context/<game>_images.json`, mirrored into `spend.images_used`) and refuse a run past it.

## Stage 4 — Implementation

Read `references/AGENT_BRIEFS.md` (JSON protocol, safety block, platform reminders,
coder and fixer templates, context schema) and `references/VISUAL_GATE.md` before the
first coder.

**Prerequisites** (missing → re-run stage detection and drive the missing stage): the
GDD, prompts and manifest; the infra gate passed; the game's assets packed;
`<skills>/templates/app_ai_template/src/app_ai_template.h` and `API.md`; a working
hidden simulator (`<skills>/tools/sim/run_hidden.ps1` / `.sh`; Linux under `xvfb-run`).

### Step 1 — Initialize
1. Parse `plans/<game>_prompts.md` (`## Prompt N:` sections); read the GDD.
2. `context/<game>_context.json` exists → resume from it (*(stepwise)* offer first).
3. New game → copy `<skills>/src/app_structure_example.h` over
   `app_<game>/src/app_<game>.h` (the infra gate's demo goes; the folder, marker,
   packed assets and toolchain carry forward). The skeleton includes the template's
   `app_ai_template_ids.h`; the scaffolder's rename pass ran before this copy, so the copy
   itself swaps the template names for the game's (run from `<ws>`):

   ```powershell
   $t = [IO.File]::ReadAllText('<skills>\src\app_structure_example.h').Replace('app_ai_template_ids', 'app_<game>_ids').Replace('app_structure_example', 'app_<game>')
   [IO.File]::WriteAllText("$PWD\app_<game>\src\app_<game>.h", $t)
   ```
   ```bash
   sed -e 's/app_ai_template_ids/app_<game>_ids/g' -e 's/app_structure_example/app_<game>/g' \
       <skills>/src/app_structure_example.h > app_<game>/src/app_<game>.h
   ```

   Then `#include "app_<game>_ids.h"` must be in the copy (`Select-String` / `grep -n
   '_ids.h'`). The test-hook prefix `GAME_` is renamed by Prompt 1's coder.
4. Build the prompt dependency graph (foundational vs cosmetic/isolated).
   *(stepwise)* Present the execution plan and wait.

### Step 2 — Validate prompts
Each prompt is a testable build: a clear Verification section, no dependency on a later
prompt, self-contained instructions. Failures → back to `technical_prompter`.

### Step 3 — The prompt cycle (repeat per prompt)
0. **Snapshot** the game before the coder runs (`python <skills>/scripts/history.py snapshot --workspace <ws>
   --game <game> --label "prompt <n>"`; `references/RUN_MODES.md`, "History and undo").
1. **Brief**: Coding Task JSON with the safety block, platform reminders, standing rules
   and test hooks (`references/AGENT_BRIEFS.md`).
2. **Coder** subagent writes `app_<game>/src/app_<game>.h` (plus `app_metadata.h` /
   `app_save.h` when the prompt adds saves or optional callbacks).
3. **Checks, in parallel**: the code review, in every tier two separate reviewers, the Requirements
   Agent and the Template Agent (`cube_verifier`, read-only, code), and the **visual gate** (every
   tier), which you run yourself:
   build the hidden simulator with the test hooks, run it with 24-screen frame dumps,
   LOOK at the frames, write findings (`references/VISUAL_GATE.md`). A build error is a
   critical finding.
4. **Playtest Agent** (`cube_verifier`) on the prompts the tier names (`lite` and `full`: every
   prompt; `standard`: foundation, core and secondary) **and, in `standard`, on any prompt that adds or
   changes an input or a mechanic, whatever its category** (its
   `### Input or mechanic change` line; `references/RUN_MODES.md`, "Verification tiers"), through the hidden
   instance's control socket (`SIM_MCP.md`): taps, twists, tilts, scored on what it sees. A socket that does not
   answer gets one restart of the instance (by PID); still no answer → an environment blocker (the prompt
   stays open, `RUN_MODES.md` failure policy 5), never a silent pass on the visual gate alone. It needs only the
   simulator, so start it as soon as the gate run has ended, while the code reviewers are
   still reading (one simulator at a time; stop it by PID afterwards).
5. **Evaluate.** Pass = every deployed code reviewer ≥ 90, no unresolved critical
   finding from any check (a critical issue fails its agent whatever the total), no
   critical or major visual finding, Playtest ≥ 90 without a critical issue when
   deployed, and **no open major from any agent**: a 93 with a major (music that never
   stops, art at ±120) is a fix round, not a pass. A major is left open only with a
   reason recorded in the context (`accepted_majors: [{"prompt"?, "asset"?, "finding", "reason"}]`,
   `references/AGENT_BRIEFS.md`, "Context file") and
   named in the report. Otherwise ONE fixer gets the union of all issues plus the frames that show
   them, then every gate runs again (a fix that satisfies the code reviewers can still
   break the picture). From the second round on the code reviewers re-check against
   their previous report and the fixer's diff (`recheck` in the brief, `cube_verifier`
   "Re-check rounds"); the visual gate and the playtest always run in full.
   **Cost** (measured on a foundation prompt at `full`): coder ~12 min, each code reviewer
   6-10 min, playtest 13-20 min, fixer ~20 min; ~1.5 h and ~2M subagent tokens with one
   full fix round. A smaller model for the reviewers did not make them faster. Fix rounds per
   prompt: the tier's maximum (`lite` 2, `standard` 3, `full` 5), then the bounded failure policy
   (`references/RUN_MODES.md`): *(stepwise)* or `scope_cuts: ask` → save and ask "simplify / try
   again / stop?"; autonomous with `scope_cuts: auto` → rescope while rescopes are left, else save and
   stop with the report. Either way the prompt completes only when the gates pass on its final
   scope; it is never marked done with a failing gate.
6. **Save context** (schema in `references/AGENT_BRIEFS.md`): scores, visual verdict and
   findings, fix rounds, cuts. **Delete the check frames as soon as each check is done** (the visual
   gate's and the playtest's folders under `assets_<game>/qa/sim/`, after you looked and wrote the
   findings): they are hundreds of MB per prompt. Keep only the frames of the final long autoplay run
   when a gameplay video was asked for (`references/DELIVERY.md` §5); a stepwise checkpoint keeps its one
   sheet PNG until the user answered.
7. **Transition.** Autonomous → next prompt. *(stepwise)* STOP with: what was added, the
   checks' result in plain words, the frames sheet, what nothing could judge (how it sounds, how it
   feels, balance, the real cube); wait for "next / here are the bugs: … / change the design / stop".

**Pipelining** (one game file, so one coder at a time):

| Situation | Decision |
|---|---|
| N+1 does not depend on N's checked code | prepare N+1's brief while N is checked |
| N+1 builds on N, N is being fixed, or N is foundational (scaffold, data, core init) | wait |
| N is cosmetic or isolated (audio, polish, UI text) | its checks may overlap the next brief |
| Any prompt | the next coder starts only after N passed every gate (the visual gate builds from that file) |
| Simulator runs and playtests | never in parallel: one instance, one port |

**Errors and resume.** A coder error → fixer with the error, then the gates. Source and
context disagree → re-read the source, update the context, adapt the remaining prompts.
Resume → read the context, check `last_completed_prompt` against the source, continue
with the next prompt.

### Step 4 — Complete
After the last prompt run one long autoplay gate (50 ms frames, one per tick, **with
`-AllowDrops` / `--allow-drops`**: at 50 ms a desktop loses one or two slots during the boot intro and a
strict run ends with exit 10, simulator exit 16; the frames feed the report and the video), then Stage 5.
The prompt gates themselves stay strict at 250-500 ms (`references/VISUAL_GATE.md`, step 2). A good-looking simulator is not a shippable result: the
simulator runs PC-compiled code, so only Stage 5's verified device `.oct` proves the game
runs on the cube.

## Stage 5 — Delivery

Read `references/DELIVERY.md`. In short:
1. **Ship build**: test hooks off, the minor version bumped (patch 0; `repack_app.py` does it) when the
   user may have an older install, then `<skills>/scripts/build_device.ps1` / `.sh` writes `dist/app_<game>.oct`:
   the ARM module against the public game API (`api/apps` + `api/include`), then the
   container; no simulator is involved. Verification is mandatory and done by the script
   (`pack_beta.py --verify-oct`): ARM code embedded, non-zero build id, the `ico` map, and
   title, version, GUID, categories and save size equal to the app's defines. A
   mismatch, or no way to verify, fails the build. **Required in every mode.** The ARM
   toolchain is already there by now: every `build_game` since the infra gate ran its device
   check with `arm-none-eabi-g++`, so a missing toolchain stopped the run before the infra
   gate (entry check 3), not here.
2. **Deliver from `dist/` only**, never an `.oct` found anywhere else.
3. **The install link and QR code**: ask once "Make an install link and a QR code so you can put the game on your cube from your phone? (The game file is sent to WowCube's servers for that.)",
   then `python <skills>/scripts/store_upload.py <ws>/dist/app_<game>.oct --yes --verify`:
   the QR code `dist/app_<game>_qr.png` and the link (keep its `?password=` part). Give both with one line:
   "Scan it with your phone (or open the link on it): the WowCube app installs the game on your cube."
   Nothing goes to a cube from this computer; which cube the phone is connected to is the user's business.
   Then the on-device checklist.
4. Optional, offered in the report: the gameplay video from the hidden frames (ffmpeg,
   made when the user wants it) and, after the first playable build, the balance loop
   (tunables table, autoplay runs, a short loop with the user).

Then the end-of-run report (`references/RUN_MODES.md`), written to `context/<game>_report.md` and shown in the
chat.

**No reminders left behind.** Never schedule wake-ups or reminders to wait for a subagent or a background
run: their results arrive by themselves. If one was scheduled anyway (a host tool such as ScheduleWakeup, a
loop, a cron task), cancel every pending one before the report: a real run delivered the game, and then two
stale "continue the build: run the audio check..." reminders fired into the user's finished session. The
same before any stop that ends the run (a blocker, a spent budget).

## Mod mode

### M0 — Import the project (entry `mod`, or sources outside `<ws>`)

M0 runs **once per game**. Its `import` record in the context marks it done; every later entry
(resume, the next mod) skips to M1 and never touches the identity again.

1. Find the sources the user named (a folder, an archive they extracted, a repository). Read them in
   place; never edit outside `<ws>` without asking.
2. Bring them into the pipeline's layout: `<ws>/app_<game>/` with one `.target` marker, `src/app.h`,
   `src/app_metadata.h`, the game header, `art/`, `sound/`. A folder already in that layout is used
   as it is (copied into `<ws>` only if the user agrees). An older layout without `app_metadata.h`
   keeps its own build path (`<skills>/scripts/repack_app.py` detects it); moving it to the new layout
   is a T4 change (ask first).
3. **Rights.** The profile's `source.rights` (setup asks it as a plain yes/no: "Do you have the right
   to change this game and publish your version?"): `yes` → go on; `no` → stop: modding it needs the
   owner's permission, say so and do nothing to it; `unsure` (or unset and the game is not the user's
   own) → the mod is made for private testing only (the automatic checks and the user's own cube), never
   published or shared, and the final report repeats that the owner's permission is needed before publishing.
4. **Update or fork** (the profile's `source.mod`, else ask): *update* works in place, never changes
   `APP_GUID1` or the title, and only bumps the version (the cube replaces the installed game and keeps
   its save); *fork* is a new game in a **new** folder `<ws>/app_<new>/` (a new `<game>` name; never the
   source folder, never an existing app folder), made with one command (it refuses an existing target
   and leaves the source untouched):

   ```
   powershell -NoProfile -ExecutionPolicy Bypass -File <skills>\scripts\fork_app.ps1 -Source <path>\app_<old> -Name <new> -Title "<New Title>" -Workspace <ws>
   bash <skills>/scripts/fork_app.sh --source <path>/app_<old> --name <new> --title "<New Title>" --workspace <ws>
   ```

   It copies the app without build output and without the source's pack record, renames the `.target`
   marker, the game and ids headers, every `#include` of them and `APP_DIR`, writes a fresh random
   `APP_GUID1`, the new `APP_TITLE` and version **0.0.0** (so its first repack ships 0.1.0; a legacy integer
   `APP_VERSION` becomes the template's MAJOR/MINOR/PATCH fields), copies `assets_<old>/` and `plans/<old>_*`
   when they exist (as `assets_<new>/`, `plans/<new>_*`), and prints the identity block for step 6.
   Test-hook macro names keep the source's prefix (record them in `test_hooks`). Then rebuild the plugin
   (`tools/sim/build_game`) before the M1 baseline run.
5. **Art sources.** An app whose art exists only packed (`index.bin` + `art/packed/`, no
   `assets_<game>/art/*.png`, no PSD or PNG sources that produce its sprites; `repack_app.py` refuses
   to repack such an app and prints this command) is extracted once, before any asset change:

   ```
   python <skills>/scripts/extract_art.py --app-dir app_<game> --out assets_<game> --manifest plans/<game>_assets.json
   ```

   It writes one pixel-exact PNG per sprite to `assets_<game>/art/` (an untouched copy in
   `assets_<game>/original/`, every packed sprite, font glyph and palette record as it was in
   `assets_<game>/original/packed/`), the launcher icon as `assets_<game>/icon.png` (from now on the
   game's one launcher icon source: edit or replace that file to change it; `app_<game>/art/icon.png` and a
   sprite named `launcher_icon` are not used for it, `references/STAGE3_ASSETS.md` §5),
   `assets_<game>/extracted.json` and, when the game has no manifest yet, a manifest that lists every
   sprite and sound as `keep` (carried through unchanged); with the manifest it also anchors up to three
   kept sprites as the style reference (`assets_<game>/style/`, "Style check in Mod mode" below). The normal manifest pack then repacks the
   game without changing anything the mod does not touch: every sprite whose PNG and manifest entry are
   unchanged, the font glyphs of every font whose source is unchanged (no `.fnt`, or the `font_<n>.fnt` +
   atlas the extraction saw: `extracted.json` `fonts` records a digest of each), the palettes and the icon
   are written back byte for byte, the asset ids stay where they were (new assets go after them) and the
   game's own `_ids.h` is kept; only edited or added sprites are encoded anew, and an edited font's glyphs
   (that font only). A `font_*.fnt` the game ships in `art/` but its pack never held (two of the reference games)
   stays unpacked unless the manifest names it (`"fonts": ["font_1"]`). `scripts/carry_art.py` and the
   pack print which sprites are re-encoded and which fonts are carried, rebuilt or not packed.
   From an `.oct` alone: `--oct <file.oct>` instead of `--app-dir` (it then also writes the sounds).
   An app packed by the SDK's octpacker (`art/octpack.json`) keeps its PSD path and is not extracted.
6. Write the `import` record into the (new) game's context before any other change:
   `{"from": "<source path>", "mode": "update|fork", "app_dir": "app_<game>", "date": "..."}`, and for
   a fork `"identity": {"guid1": "0x...", "title": "...", "fork_of": {"app_dir": "...", "guid1": "0x..."}}`
   (`fork_app` prints it; `references/AGENT_BRIEFS.md`, "Context file"). Then M1.

**Versions in Mod mode.** One rule: every build the user may install comes from `repack_app.py`, which bumps the
**minor** version and resets the patch, and the `.oct` carries exactly the version in `src/app_metadata.h`
(Stage 5's `--verify-oct` checks it; the cube's update check compares it exactly). A fork is set to 0.0.0 by
`fork_app`, so its first delivered build is **0.1.0**, then 0.2.0, 0.3.0; an update goes on from the installed
version (0.4.0 → 0.5.0). A legacy integer `APP_VERSION` (an older app, no major/minor/patch) is bumped +1 on an
update (`repack_app` says so; moving it to the semver fields is T4, ask first); a fork converts it to 0.0.0.

### Prime directive — the working project is the source of truth

**Make the smallest change that satisfies the request.** Do not rewrite, refactor,
re-architect, or restructure code, assets, or data beyond what the change strictly
needs. Structural or design-level changes are allowed **only when the user explicitly
asks for them**; in every other case, solve it minimally, with the smallest change. A working
game the user is happy with is far more valuable than a "cleaner" one that now behaves
differently, so when a change *can* be done as a small local edit, it MUST be.

This mode adds no new agents or sub-skills: it reuses `cube_asset-builder` /
`cube_art-director`, the coder/verifier/fixer subagents, the visual gate and
`wowcube-boilerplate` at the smallest scope that does the job.

### M1 — Analyze the target
1. Locate `app_<game>/`. Several games → ask which. Not there → stop and say so.
2. Read the baseline (the source of truth): `src/app_<game>.h`,
   `src/app_<game>_ids.h`, and when present `plans/<game>_assets.json`,
   `plans/<game>_gdd.md`, `assets_<game>/style/`, `assets_<game>/extracted.json`. A hand-dropped
   project may have only the code; that is enough to mod (asset changes need M0 step 5 first).
3. Run the environment check (entry check 3), then a baseline hidden run
   (`references/VISUAL_GATE.md`): it must build and render. Keep its frames for M5 and delete them when
   the mod's checks are done.

### M2 — Classify (the cheapest type that covers the request)

| Type | What | Minimal path |
|---|---|---|
| **T1 Logic / parameters** | speed, timing, balance numbers, small behaviour | only named values in the tunables block → the light lane (`references/RUN_MODES.md`: edit, build, one visual check, plus a short playtest in `lite` and `full` when a changed value changes how the game plays; minutes); other small behaviour → one scoped coder task → gates → fixer |
| **T2 Sprite** | replace or add an image | the manifest entry edited or added (below) → `build_pipeline.py validate` (the manifest guard; only the sprites still to draw count against the image budget); the changed sprite goes to `assets_<game>/raw/<name>.png` (never `art/`: `process` writes it), then `art.py process` + `qa` ("Raw images for `process`" below); generated → `cube_art-director` for that sprite only; every new or changed sprite is held to the game's style reference ("Style check" below) → repack → a new `BMP_*` gets one scoped coder edit |
| **T3 Sound** | replace or add a sound | the user's file, or a CC0 source the user approved → `sound_kit.py build` → repack |
| **T4 Structural** | new mechanic, new level system or mode, refactor, design change | only when the user explicitly asked (a question like "can we add levels?" is answered, not executed); always the mini-plan approval below, in every mode: first say it starts a new round of work and its estimate, then `cube_game-designer` updates the GDD (what changes for the player, new tunables) and the new parts are planned as prompts; nothing runs before the yes |

Record each change in the context's `prompts` list as `{"prompt": <n>, "title": "...", "type": "T1..T4",
"request": "<the user's own words for this change>"}`: the reviewers' `mod_request` (AGENT_BRIEFS.md), which
stands in for the GDD when the game has none.

**Raw images for `process`** (what `art.py process` does with `raw/<name>.png`; checked 2026-11-03):
- An **edited original** (pixels of a kept sprite changed): start from `assets_<game>/original/<name>.png`, edit it at
  its exact size, save it as `raw/<name>.png`, and give the entry `"fit": "canvas"` (plus `"alpha": "soft"` when
  `extracted.json` says `semi_transparent`). `process` then scales the canvas 1:1: the result is the PNG as edited.
- A **new sprite drawn in code** (or a user's PNG): RGBA on a transparent canvas at 4-8x the entry's `size`, same
  aspect (STAGE3_ASSETS.md §2, procedural step P2); `process` box-downscales it. Without `fit` it crops to the drawn
  object and scales that to fill the frame (centred); with `"fit": "canvas"` the whole canvas is scaled as drawn, so
  a margin or an off-centre placement is kept.
- Never an exact-size drawing without `"fit": "canvas"`: the default fit crops it to the object and scales it UP to
  the full frame (an 11 px square in a 32 px frame comes out 32 px).

**Style check in Mod mode** (`art.source: original`: the game's own art is the style). The style reference is a few
of the game's kept sprites, anchored once right after the extraction (`extract_art.py --manifest` does it; by hand:
`python <skills>/skills/cube_art-director/scripts/art.py anchor plans/<game>_assets.json --originals`, which picks up
to 3 large cut-out sprites of different families and builds `assets_<game>/style/profile.json`; `--only a,b` names
them instead). There is no STYLE.md and no `_style`: `art.py qa` scores every new or changed sprite against that
profile, an edited original against the profile plus its own original (a mirrored or retouched sprite keeps its
colours; a recolour into colours the game never uses fails: a user who asked for exactly that waives it on the
record, `accepted_majors`) (kept sprites are only checked to be unchanged), and the consistency reviewer gets the anchors and the
originals as its style reference instead of a style bible (STAGE3_ASSETS.md §10). `style_lock.status: user_art`.
Generated sprites (`art.new: codex`) use the same anchors as Codex's style reference.

**Who writes the manifest (one rule).** In Mod mode the orchestrator does: there is no Stage 2 to send it
back to, so Build mode's "back to `technical_prompter`, never patch it yourself" does not apply here.
- A game **without** a manifest whose art exists only packed gets one from the tool, never by hand:
  `extract_art.py --manifest` (M0 step 5) lists every sprite and sound the game packs, each
  `"keep": true`. (A game without a manifest that has its own art sources, a PNG folder or PSDs that
  `repack_app.py` packs, keeps them: change the asset there and repack; PSD placement maps cannot be
  rebuilt by a manifest, `extract_art.py` names them.) Creating it is part of
  the import, **not** a structural change and not a T4 question: it changes nothing in the game (the
  pack carries every untouched record through byte for byte, ids and the game's `_ids.h` included). Never a one-entry or partial manifest:
  `build_pipeline.py pack` rebuilds the whole `index.bin` and `_ids.h` from it, so an asset missing from
  it would vanish (`repack_app.py` refuses such a repack).
- **Editing entries** is the T2/T3 work itself: to change a sprite, drop its `keep` and give it a
  subject-only `gen_prompt` and its `background` (the validator asks for both; a later redraw uses them);
  it is then processed and checked like drawn art. For an edited original add `"fit": "canvas"` so
  nothing is cropped or rescaled, and `"alpha": "soft"` when its edges were soft (`extracted.json` says
  `semi_transparent`; the default binary alpha would cut them);
  to add one, a new entry with `gen_prompt` and `background` (subject-only prompt rules,
  `references/STAGE3_ASSETS.md` §1); sounds the same way. Untouched sprites stay `keep`: `art.py process`
  copies them byte for byte from `assets_<game>/original/` and `qa` only checks their size, format and
  that they are still the original.
- The manifest guard (`build_pipeline.py validate`) runs after every edit, as in Build mode.
- An app packed by the SDK's octpacker (`art/octpack.json`, PSDs) gets no manifest: change the PSD layer
  or input and repack with `repack_app.py` (it runs `octpack-pack`).

### M3 — Mini-plan
The type, the exact files and assets, why it is minimal. Snapshot before executing (`history.py
snapshot ... --label "<change>" --request "<the user's words>"`, `--assets` for T2/T3). Autonomous:
composed and auto-approved for T1-T3 (resources were settled at intake). **T4 always stops**: the cost
line (a new round of work, the estimate in time and tokens) and the designer's mini-plan, then wait for
the yes, in every mode. *(stepwise)* Present it, ask for any missing resource (Codex login, approval of a
sound download), STOP until approved.

### M4 — Execute at minimal scope
Code: one coder subagent whose task is only the requested edit; `prior_context`
describes the existing structures so it extends, never rewrites. Assets:
`cube_asset-builder` for the specific sprite or sound, then its pack step (refreshes
`index.bin`, `art/packed`, `sound/assets`, `_ids.h`).

### M5 — Verify
The Stage 4 gates of the profile's tier (`references/RUN_MODES.md`, "Verification tiers"): the tier's
code review (Requirements + Template, in every tier), each
≥ 90 with no critical issue and no open major; the visual gate in every tier; the Playtest Agent by the
mod's category, read from the tier's playtest row: T1 that changes input or a mechanic and T4 count as
`core` (and get the playtest in every tier by the input-or-mechanic rule), a T1 number change counts as
`polish`, T2 and T3 count as `audio` / `polish` (playtest in `lite` and `full`, not in `standard`). Framed for a mod:
(a) the change is there, (b) nothing else moved compared with the M1 baseline frames
(`no_regressions` weighs most; `gdd_alignment` against the GDD when one exists, else against the recorded
`mod_request`). Fixer: the tier's
maximum of rounds, then the bounded failure policy. Autonomous: independent mods back to back,
reported once. *(stepwise)* A per-change checkpoint with before/after frames; one mod at
a time, never batched.

### M6 — Repackage and deliver
A mod is not done until the device package is rebuilt: Stage 5 (`repack_app.py`: the minor version
bumped, patch 0, "Versions in Mod mode" above; `dist/app_<game>.oct` carrying exactly that version;
a new install link and QR code, under the consent already given for this game). An older app without `src/app_metadata.h` is
built with the fallback builder; moving it to the dev layout is a T4 change (ask first).

## Configuration

| Setting | Default | Notes |
|---|---|---|
| Profile | `~/.wowcube/config.json` + `<ws>/wowcube.project.json` | written by `wowcube-setup`; resolution in its `references/PROFILE.md` |
| Verification tier | from the profile, following `guidance` (autonomous → `lite`, guided → `full`) | `lite` / `standard` / `full`: prompts, playtests, fix rounds, rescopes, image budget (`references/RUN_MODES.md`) |
| Verification threshold | 90 | per deployed agent (code reviewers, Playtest); any unresolved critical issue fails regardless of score |
| Max fix rounds | tier: 2 / 3 / 5 | per prompt or mod change; `budget.fix_rounds` overrides |
| Visual gate | always, every tier | after every coder and fixer run (`references/VISUAL_GATE.md`) |
| Playtest Agent | per tier, through the hidden instance's socket (one restart when it does not answer, then an environment blocker) | ports from 8177 (`playtest_port`); never an instance this session did not start |
| Run mode | from the profile (`guided` = stepwise) | a request overrides it for the run; `YOLO` is the compat alias (`references/RUN_MODES.md`) |
| Failure policy | bounded | rounds and rescopes are counted; when the budget is spent: save, then ask (guided) or stop with the report (autonomous); every cut in the final report |
| Art source | from the profile; the procedural style (drawn in code) by default | Codex, own art or a provider only when the user picked it (a detected login or key is never assumed to be theirs); the procedural style when the source cannot draw; a paid image API only on the user's explicit opt-in in this run |
| Image budget | tier: 30 / 80 / 200 | `budget.images` overrides; counted in the context (`art_budget`); spent, it ends the redraws, not the run |
| Sound source | from the profile: `synth` (the default) or `cc0` (only when the user picked real recordings; approved list) | `sound_kit.py` either way; `synth` is final, synthesis under `cc0` is a fallback |
| Deliverable | `dist/app_<game>.oct` + the install QR code `dist/app_<game>_qr.png` and link | `<skills>/scripts/build_device.*`: ARM module against the bundled public game API, then the container (pure Python); `<skills>/scripts/store_upload.py` after the user's one yes |
| History | `<ws>/.history/` | a snapshot before every change; "undo" restores the latest (`references/RUN_MODES.md`, "History and undo") |
| Start from | 1 | the first prompt to run (resume) |
