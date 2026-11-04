---
name: wowcube-setup
description: >-
  Onboarding component of the WowCube pipeline, invoked by cube_orchestrator on entry
  when no profile exists (no ~/.wowcube/config.json or no <ws>/wowcube.project.json),
  or when the user says "setup", "reconfigure", "change my settings", "change the
  budget", "use another image provider" (in any language). Greets the user, then
  detects the machine read-only while saying what it checks (OS, agent host, Python, the
  build-check components, Codex, image providers, local Stable Diffusion, Node/Playwright,
  ffmpeg, ARM toolchain), asks at most three short questions (starting point, guidance,
  the AI tools and subscriptions the user has; the guidance answer also sets how thoroughly
  each step is checked), asks once
  for permission to install the components a game build needs (never on the art-only path),
  and writes the machine profile and the project profile the other skills read. Never a
  paid service, a download or an install without the user's explicit yes. Also the
  environment-only install ("set up the environment", "install everything", "install
  the WowCube plugin and everything it needs"): installs every component with no other
  questions, then tells the user to restart Claude Code and start a new session. A
  later session that finds the install consent recorded asks no install question.
---

# WowCube setup

> **Component of the `cube_orchestrator` pipeline.** The orchestrator invokes it on entry when a
> profile is missing, and on "setup" / "reconfigure". It returns control to the orchestrator.

The pipeline serves people with very different machines and goals: a first-time creator with only
Claude, a studio with its own design document and image keys, a developer who only wants to build and
upload, an artist who wants only the pictures and no code at all. This skill finds out which, with as few
questions as possible, and writes it down so no later step asks again. Field definitions and the
resolution order: `references/PROFILE.md`.

**Words the user sees.** Plain words for everyone until the user shows otherwise (they use technical
words, say they are a developer, or answer *Step by step, I know C++*): no "GDD", ".oct", "CC0", "Codex",
"PSD", "simulator", "toolchain", "compiler", "winget", "pip" in what the user reads before that; the list
and a short glossary for terms that must appear: `cube_orchestrator/references/RUN_MODES.md`, "Plain
language". "The simulator" is an internal name (docs, briefs, tool names), never said to any user,
developers included. To the user it is "the automatic checks of every build". Never present it as a separate concept, a separate download, a separate choice or
a way to play: it is one of the components the user agrees to install (Step 2b). Never name or guess
subscription plans or price tiers: ask what AI tools the user has and take their words as they are.

**Defaults: the AI the user came with, everything made in code.** The art is drawn in code, the sounds are
synthesized, no outside service is used, the run is autonomous (one or two steps, each with the full set of checks). "I don't know", "you
choose", "skip setup", "just do it", "go", or a question left unanswered → these defaults (never stepwise),
and say so in one line. Outside services (ChatGPT/Codex, an image service, downloaded sounds) only when the
user picks them by name.

**What is found on this computer is not the user's until they say so.** A logged-in Codex or an API key
may belong to someone else (a family or shared PC). Never pre-select or default to it, never print a key or
credential name unless the user asks. At most, when the user says they have ChatGPT or asks what is there,
one question: "I see ChatGPT's drawing tool logged in on this computer: is it yours, and may I use it?"

**No cube, no game.** The games are for the WowCube and are installed from a phone onto a cube. A user
without a cube is told so plainly; there is no no-cube path (the automatic checks are not a way to play).

`<skills>` = the folder two levels above this SKILL.md (the plugin root; `${CLAUDE_PLUGIN_ROOT}` when the host exports it); resolve it on every entry, never store it. It holds `skills/`,
`scripts/`, `templates/`, `tools/`. `<ws>` is the user's
workspace (ask once if the current folder is not obviously it; never the plugin folder).

## Rules

- `cube_orchestrator/references/AGENT_SAFETY.md` applies in full. Detection only **reads**: it installs,
  downloads, logs in and pays for nothing.
- **A found key is a fact, never consent.** An `OPENAI_API_KEY` in the environment means the user *could*
  pay for images; it is used only after they say so in this run (`--allow-paid`, RUN_MODES.md).
- **No secrets in profiles.** Profiles hold credential *references* (`"env:OPENAI_API_KEY"`,
  `"file:~/.wowcube/image_api.json"`), never a key, token or password. Never print a key's value; test
  presence only.
- **Role sets defaults, nothing else.** "creator", "developer" or "staff" changes default answers. A
  "staff" answer grants no access, skips no gate, and unlocks no paid service or private resource.
- Ask with options (AskUserQuestion), in the user's language, plain words. Never more than three
  questions in the first round; a follow-up only when an answer needs one (the provider choice).

## Step 0: say hello and what happens next

Before it, read `~/.wowcube/config.json` (a file read, no tool run): its `install_consent`
(`profile_provider.install_consent` reads it, the object shape and the older plain string alike) says
whether the user already agreed to the installs (the one-command installer records `yes`, so does an
earlier *Install them*).

The first message is short (three to five lines), in the user's language and plain words, before any
check:
- what we are going to do: "I'll make a game for your WowCube with you: we work out the idea, I draw the
  pictures and make the sounds, write the game and check it, and at the end you install it on your cube
  from your phone." (Art only: "I'll draw the pictures for your game in one style.")
- the tools, by what the profile says:
  - no `install_consent` yet: "First I need to set up a few tools on this computer (Python and the
    programs that build and check games). I'll look at what's already there; nothing is installed
    without your OK."
  - `install_consent` is `yes` (the installer ran, or the user agreed earlier): no setup line, only "I'll
    quickly check that the tools are all there." Never "First I need to set up a few tools", and no
    install question (Step 2b).

No question in this message: the questions come after the check, all in one call (Step 2). No install
list, no tool names, no jargon in this message; the details come only when the user asks or an install
question needs them (Step 2b). Never start with silent tool runs: the user must always know what you are
doing and why.

## Environment-only install (step 1 of 2 for a new user)

The first contact for a new user is two steps: (1) "install everything" in one session, (2) restart Claude
Code, open a new session, "I want to make a game". This section is step 1. It runs when the user asks only
to set up or install ("set up the environment", "install everything", "install the WowCube plugin and all
it needs", on any machine, typically a clean one), and replaces Step 0 and Steps 2–2b:
- **The request is the install consent**, like running the one-command installer: the yes to every
  install below and, on Windows, to winget's package and source agreements (`-AcceptAgreements`). Record
  `install_consent: {"answer": "yes", "date": ...}` in `~/.wowcube/config.json` (merge, keep the other
  keys); ask nothing else: no game questions, no guidance question, no AI tools question (they come in
  step 2, the first game).
- **One start line, then work.** In the user's language: "Setting up everything for making WowCube games
  on this computer: about N GB and about M minutes. I'll tell you when it's done." (N and M: the sum of
  Step 2b's table rows for the `[MISSING]` items; a clean computer is up to about 4 GB and 30–60 minutes,
  the build checker alone about 6 MB and under a minute. On Windows add "Windows may ask for administrator
  permission a few times; accept each". "You can leave it running" only when nothing in the list needs
  the user.) No explanations of what each tool is, no install lists. Progress: this is a long install, so
  one line per finished group ("Python ready", "build tools ready") is fine; nothing in between.
- **Install everything a game build needs**, the same set as Step 2b after a yes: detect (Step 1), then
  Windows `check_env.ps1 -Install -AcceptAgreements`; the build checker (`get_sim`); the Python packages
  (Linux/macOS: the `~/.wowcube/venv` venv `check_env.sh` prints); macOS: `brew install` the missing
  packages when Homebrew is there. What only the user can do (macOS `xcode-select --install` opens Apple's
  installer; installing Homebrew and Linux package lines need their password): one plain line with the
  exact command, wait, then go on.
- **Check, then hand over.** Run `check_env` again (`check_env.ps1` re-reads PATH from the registry itself,
  so programs installed a minute ago are found in this session too). All ok → "Everything is installed.
  Close Claude Code if it is open, open it in a short folder for your games (e.g. C:\games or ~/games),
  start a new session and say 'I want to make a game for my WowCube'." Then stop: nothing else is started
  in this session (no entry, no game). An item the installer reported as installed but this check still
  misses is not a failure: say the new session will find it (never tell the user to install it by hand).
  An item whose install failed (`[FAILED]`) → Step 2b's "No admin rights, a declined Windows prompt, or a
  failed install" rule.
- **The same request with a game under way** ("install" after *Not now*, while `<ws>` holds a profile or
  a game's context): this is the Step 2b yes for that game, not a fresh setup. Install the same way, then
  end with "close Claude Code, open it again in this same folder, start a new session and say 'continue':
  we go on with your game" (never "I want to make a game": that starts a new one).

## Step 1: detect (read-only, before any question)

Run the checks and keep the results in memory. Say what you are checking in one line when the checks
start ("Checking what's needed to build and check games, and what else is installed…") and one when they
end (below), never raw command output. Each check is read-only and short; a check that fails or times
out is recorded as `unknown`, never retried in a loop.

When detection ends, say what it means in one or two plain lines ("Some tools for building games are not
installed yet: I'll ask before installing them", or "Everything needed is already here"). No list of
programs, no key or credential names, no detected logins presented as the user's.
Detection only adds notes for you; the user's own answers decide. Key *names* are recorded in the machine
profile, never shown unless the user asks; values never.

| What | How (Windows / Linux, macOS) | Recorded as |
|---|---|---|
| OS, shell | the environment | `os` |
| Agent host and subagents | the tools you have: an Agent/Task tool means subagents; a Skill tool means skills load as skills; otherwise the docs are read as plain files | `host.name`, `host.subagents`, `host.skills` |
| Python 3.11+ and its packages | part of `check_env` (Windows: `-Install` installs Python 3.12 for this user with winget and then the packages from `scripts/requirements.txt`; Linux/macOS: the package line it prints) | `tools.python` |
| Build-check components (internal: the simulator and the build kit) | `<skills>/scripts/check_env.ps1` / `check_env.sh` (exit 0 = ready; it reads, installs nothing): `~/.wowcube/sim/<version>/<os>/wowcube-sim` answers `--version` with the version this plugin needs (`ok`), or `get_sim` could install it (`missing`, with the line it printed); the plugin compiler and the ARM toolchain. Each `[MISSING]` line says whether it can be installed for the user (the build checker: `get_sim` copies the prebuilt one this plugin carries, no download, nothing to build; winget on Windows) or must be installed by them | `tools.sim`, `tools.build_kit` |
| ARM toolchain | part of the same check (`arm-none-eabi-g++`, CMake, Ninja) | `tools.arm` |
| Codex CLI + ChatGPT login | `python <skills>/skills/cube_art-director/scripts/art.py doctor` | `art.codex`: `chatgpt` / `api_key_login` (unusable: it bills that key) / `not_logged_in` / `absent` |
| Image provider keys | presence only: `OPENAI_API_KEY`, `GEMINI_API_KEY` or `GOOGLE_API_KEY`, `XAI_API_KEY`, `OPENROUTER_API_KEY`, `IMAGE_API`, the file `~/.wowcube/image_api.json` | `art.keys_found`: names, never values |
| Local Stable Diffusion | an A1111-compatible server answering on `http://127.0.0.1:7860` (one request, 2 s timeout; localhost only) | `art.local_sd` |
| Node + Playwright, ffmpeg | `node --version`; `node <skills>/skills/wowcube-html-prototype/scripts/check_playwright.cjs` (exit 0 = Playwright and Chromium found in `$WOWCUBE_NODE_DIR`, `~/.wowcube/node`, the workspace or the recorder's folder); `ffmpeg -version` | `tools.node`, `tools.playwright`, `tools.ffmpeg` |
| Existing work | `<ws>/plans/`, `<ws>/context/`, `<ws>/app_*/`, a design document the user mentioned | used to pre-select the starting point |

Presence-only key check (PowerShell):
`'OPENAI_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','XAI_API_KEY','OPENROUTER_API_KEY','IMAGE_API' | Where-Object { [Environment]::GetEnvironmentVariable($_) } `
(bash: `for v in OPENAI_API_KEY GEMINI_API_KEY GOOGLE_API_KEY XAI_API_KEY OPENROUTER_API_KEY IMAGE_API; do [ -n "${!v}" ] && echo "$v"; done`).

## Step 2: ask (at most three questions, one AskUserQuestion call)

One line before the questions on why they matter ("Your answers decide how I work with you, what the
art is made with and how much time and usage the game takes; you can change them later: say 'change my
settings'"). Each option's description says in plain words what choosing it means for the user; the
first option of every question is the default (above) and is marked so.

Skip any question the request already answered ("I have a design document", "just install this game
file", "I only want the sprites", "I have ChatGPT"). "Skip setup", "just do it",
"you choose", "I don't know" → no more questions: the defaults (autonomous with its checking, drawn in
code, synthesized sound), then only the install question (Step 2b) when something is missing. Option labels
below are English examples. The question tool shows at most four options per question plus a free-text
answer ("Other"); a host without it asks the same questions as a short numbered list.

1. **Starting point** — "What are we starting from?"
   - *A new game* — an idea, or "your choice".
   - *My design document* — a description of the game, a pitch or a design document (any format).
   - *An existing game* — change it (a mod or reskin), make a new game from it, or just build, check,
     install or film it: its game folder (with or without the art's source files) or its game file.
   - *Art only* — "I want sprites, a sprite sheet, icons or backgrounds in one consistent style, no game
     code" (`entry: art`). No game is designed, coded or built: the art director works with the user
     directly (Step 2c) and delivers PNG files and a sprite sheet. This path never needs the build-check
     components, the ARM toolchain or a C++ compiler, and never asks to install them (only Python, when it is
     missing: Step 2c).
2. **Guidance** — "How should I work with you? (This also sets how carefully each step is checked.)" The
   question says it in those words, so nobody looks for a separate "how thorough" question. The answer sets how each step is checked
   (`verification`, `profile_provider.verification_for_guidance`); there is no separate question about
   checking and no "less careful" choice. Every option's description says the consequence in time and
   usage, from `cube_orchestrator/references/RUN_MODES.md` ("Estimate"), as an estimate, never a plan
   name or a tier name:
   - *On my own* (autonomous, the default; `verification: lite`) — I run to the finished game and stop
     to show you the look and, at the end, to ask about the install link. The game is made in one or two
     steps, and every step is built, looked at
     on all 24 screens, read by two separate reviewers and played automatically before the next one; a
     simple game (one step) takes about 45–75 minutes and about 1 million tokens, a game with menus and
     levels (two steps) about 1.5–2.5 hours and about 1.5–2 million tokens in total (estimates). At most 30
     pictures.
     This answer writes `budget.scope_cuts: auto` (whatever the role default, e.g. a developer's `ask`:
     the user said not to stop for anything but the two planned stops), unless they add "ask me before
     cutting anything". The
     checking it sets does not change that (the checks set the reviewers and the image budget, not the
     stops). An approved design document (`source.approved: true`) still keeps every scope or mechanic change for
     the user's yes (`references/PROFILE.md`, "Precedence of `scope_cuts`").
   - *Step by step* (guided; `verification: full`) — I explain each step and wait for your OK (the install
     link comes once, at the end; nothing goes to the cube in between). The game is
     made in more, smaller steps, each checked as thoroughly as I can (two reviewers, an automatic
     playtest, up to five fix rounds); about 1.5 hours and about 2 million tokens per step, so a bigger
     game can take several days of sessions (estimates). At most 200 pictures.
   - *Step by step, I know C++* — the same, technical detail welcome (`verification: full`).
   - *Just show me results* — "I don't care about the code": no technical words ever, I decide the
     technical things myself and show you only what you can see and judge: the art style, the finished
     pictures (art only: each family's first picture and the final set), the game's screens. Writes
     `guidance: autonomous`, `experience: new`, `budget.scope_cuts: ask` (a cut of something the user can see
     is still theirs to decide), and the same checking, time and pictures as *On my own*
     (`verification: lite`). The answer that fits an artist on the *Art only* path.
3. **AI tools and subscriptions** — "What AI tools and subscriptions do you have?" Multi-select plus free
   text; the user's words are the source of truth (`resources.have`, their own words in `resources.note`).
   - *Only Claude* — nothing else: the art is drawn in code in a deliberate style, or it is your own art.
   - *ChatGPT* — ChatGPT's drawing tool can draw the art on your ChatGPT subscription; descriptions and
     reference images go to OpenAI.
   - *Gemini, an image API key or a local image model* — say which in your own words (Gemini; an OpenAI,
     xAI or OpenRouter key; Stable Diffusion on this computer). A cloud key costs money per image: I ask
     once per run, with the cost. A local model is free and stays on this computer.
   - *An artist, or my own art* — one PNG per picture (a sprite sheet is cut into named pictures first,
     `art.py slice`; a Photoshop file's layers are exported as PNGs); I size, check and pack them.
   The free-text answer covers anything else ("I have Claude and Gemini", "a friend draws for me"). An
   image-to-video service the user names there ("I have Higgsfield") is `video`: it makes animations from
   an approved picture, never the pictures themselves (Step 2a).
   Pre-selected: *Only Claude*. Detection never adds a tool the user did not name and never pre-selects
   one: a logged-in Codex or a key in the environment is not mentioned in the options at all; when the
   user names ChatGPT, or asks what this computer has, ask once whether the login found here is theirs
   and may be used ("Rules" above). No answer, "I don't know" → *Only Claude*. Mapping to the ids
   (`scripts/profile_provider.py`, `RESOURCE_IDS`): `claude`, `codex`, `gemini`, `image_key`,
   `local_model`, `own_art`, `video`. A video connector found in the session is not an answer: never
   pre-select or suggest it.

Free text in any answer still overrides the checking and the budgets for this project
(`profile_provider.verification_for`): "check everything thoroughly" → `verification: full`; an explicit
"standard" or "check it more but not every detail" → `standard` (the only ways to get it; never offered as
an option); "quick" or "fast" → `lite` (the one-or-two-step game, never fewer checks); any other word
("normal", "medium") changes nothing: the guidance answer decides. A number of hours or a maximum number of
pictures → `budget.hours` / `budget.images`; "cut what you need without asking" → `budget.scope_cuts:
auto`. Nothing makes the checking lighter than *On my own*.
On *Art only* the guidance answer sets the picture budget and the number of fresh art reviews the same
way (*On my own* / *Just show me results*: 30 pictures and 1 review; *Step by step*: 200 and 5; an
explicit `standard`: 80 and 3).

### Step 2a: follow-ups (a second short call, only what the first answers need)

- *My design document*: "Where is it?" (pre-filled with what detection found, e.g. a file in
  `<ws>/refs/`) and "Is it approved?": *Approved, build it as written* (`source.approved: true`: every
  change of scope or mechanic waits for the user's yes, whatever the other answers say) or *A draft, adapt
  it to the cube* (`source.approved: false`). `source.document` is the path relative to `<ws>`: a file
  already under `<ws>/refs/` stays there (never copied twice); one from elsewhere is copied into
  `<ws>/refs/design/` by the game designer's Import mode.
- *An existing game*: "Where is it?" (`source.app_dir`); "What should I do with it?": *Change it* (same
  game and identity, the cube replaces the installed one; `source.mod: update`), *Make a new game from it*
  (its own name, a new `APP_GUID1`, its first delivered version 0.1.0; `source.mod: fork`) or *Just build,
  check, upload or film it* (`entry: tools`: `wowcube-tools`, no stages). For a change or a new game, the
  rights question, a plain yes/no:
  **"Do you have the right to change this game and publish your version?"**
  *Yes (it is mine, or its owner said I may change and publish it)* → `source.rights: yes`. That
  includes "a friend made it, gave it to me and said I can modify and publish it": the owner's permission
  is what counts, a written yes is not needed. *No* → `source.rights: no`: say
  plainly that a game they have no right to change is not modded without its owner's permission, and
  stop that path (offer the other starting points); *Not sure* (e.g. "I have the files, but nobody told
  me whether I may change or publish it") → `source.rights: unsure`: the mod is made for private testing only (the automatic checks and their own cube),
  never published or shared, and the report says that publishing needs the owner's permission first.
  Ask it whenever the game was not made by this user in this workspace.
- **How the art is made**, only when the tools answer leaves more than one way
  (`profile_provider.art_routes`): "How should the art be made?" with only the ways the user has, plus
  the ones that need nothing:
  - *Keep and edit the game's own art* — mods only, pre-selected there: the game's packed art is extracted
    and kept (`art.source: original`); changed or new pictures match it and are made the way `art.new`
    says: `procedural` (drawn or edited in code on this computer, the default) or `codex` (only when the
    user has Codex and chose it too). Nothing leaves the computer unless `codex`.
  - *ChatGPT's drawing tool* — when they said they have ChatGPT; drawn on their ChatGPT subscription
    (`art.source: codex`; `art.py doctor` checks the login).
  - *Gemini / my image key / my local model* — `art.source: provider`; which one when the answer named
    several or "a key" (OpenAI, xAI, OpenRouter: `profile_provider.provider_hint`), and for a cloud one:
    "each picture costs money on your account; I'll tell you the cost and ask once per run". A local Stable Diffusion is
    free and stays local.
  - *My own art* — one PNG per picture from an artist (a sprite sheet is first cut into named PNGs with `art.py slice`, PSD layers are exported); the pipeline sizes and packs them. For
    PSDs, export the PSD's layers to PNG (Photoshop: File > Export > Layers to Files, one PNG per sprite,
    named as in the manifest) and use the manifest path (STAGE3_ASSETS.md §8); packing PSDs directly with
    octpacker is internal SDK only.
  - *Drawn in code* — always offered: the agent draws a deliberate, simple style in code (flat shapes,
    clean outlines, a fixed palette): a final style, not placeholders; nothing leaves the computer.
  One way only → no question: say in one line what the art will be made with. The choice sets
  `data_policy.may_leave_machine` (`profile_provider.data_policy_for`): Codex or a cloud provider get the
  prompts and reference images (`["prompts", "reference_images"]`); everything else sends nothing.
- **Animations from video**, only when the tools answer named an image-to-video service: no question,
  one line: "You have Higgsfield: I can use it to animate characters (idles, walks) from their approved
  picture. It uses your Higgsfield credits, so I'll tell you the cost and ask once per run." Writes
  `art.animation: video`, `art.animation_provider` (e.g. `higgsfield`) and adds `animation_frames` to
  `data_policy.may_leave_machine` (`profile_provider.animation_for`, `data_policy_for(..., animation=)`).
  Otherwise `art.animation: frames`. Route and rules: `cube_art-director/references/ANIMATION_VIDEO.md`.
- Sound is not a setup question: the default is synthesized sound (`sound.source: synth`: tones, chords
  and a simple music loop made in code, nothing downloaded, a final choice). Real recordings (free sounds
  anyone may use, downloaded after the user approves the list; `sound.source: cc0`) only when the user
  asks for them ("real sounds", "recordings").

### Step 2b: permission to install the build components (one question, never on *Art only*)

For every path that builds a game (new, design document, an existing game, tools), ask once, and only
when it is needed:
- everything is there → no question: say so in one line ("Everything needed is already here").
- `install_consent` is already `yes` (the one-command installer, the environment-only install or an
  earlier *Install them*) → no question either: install what is still `[MISSING]` under that consent,
  with one line saying what and how long ("A few tools are still missing; installing them, about M
  minutes"), then the restart below.
- otherwise the question:

**"To build and check your game I need to install a few tools on this computer (Python and the programs
that build and check games; about N GB to download, about M minutes). OK to install them?"**

- *Install them* (recommended: every build is checked automatically).
- *Not now* — then say plainly: "Without these components I can't build or check the game, so I'll stop
  here. Everything so far is saved: say 'install' when you're ready, and we go on with this game." Stop
  until they agree; nothing is built, nothing else is asked. Their later "install" (in this or a new
  session) is this question's yes: install, restart, continue with the same game (Environment-only
  install, "The same request with a game under way").

Fill the question from `check_env`'s `[MISSING]` lines, in plain words:
- Python 3.12 and its packages are installed like the other tools (Windows: per user, no admin rights;
  `check_env.ps1 -Install` does both). Never ask the user to install Python by hand while the installer
  can do it.
- N, M and the wording: the sum of the table rows below for the `[MISSING]` items only, never the
  clean-computer figure when less is missing (only the build checker missing: "about 6 MB, under a
  minute"). The checker program the build checks use (internal: the simulator; `get_sim` copies the
  prebuilt one this plugin carries, no download, nothing to build) is about 6 MB into `~/.wowcube/sim/`. When `check_env` also lists tools it can install (Windows:
  `check_env.ps1 -Install`, quiet winget installs: the ARM compiler for the cube, CMake, Ninja, LLVM,
  FFmpeg, the Visual Studio C++ build tools, several GB when those are missing), say that they are
  installed as normal programs, not into `~/.wowcube`, so "nothing else changes" is only said when the
  checker is all that is missing. One short detail line lists what gets installed ("the build checker,
  about 6 MB; the cube's ARM compiler; C++ build tools, several GB"), never tool jargon for a `new` user.
- Sizes and times for N and M (Windows, `check_env.ps1 -Install`; approximate, say "about"; add up only
  the `[MISSING]` items; macOS and Linux are of the same order without the Visual Studio row):

  | Item (winget id) | Download | On disk | Time |
  |---|---|---|---|
  | The build checker (`get_sim`, copied from the plugin) | none (about 6 MB copied) | about 6 MB | under a minute |
  | Python 3.12 (`Python.Python.3.12`, per user) | about 25 MB | about 100 MB | about 2 minutes |
  | Python packages (`scripts/requirements.txt`: numpy, Pillow, ...) | about 50 MB | about 150 MB | about 2 minutes |
  | LLVM / clang-cl (`LLVM.LLVM`) | about 350 MB | about 2 GB | about 5–10 minutes |
  | ARM GNU toolchain, the cube's compiler | about 150 MB | about 1 GB | about 3–5 minutes |
  | CMake | about 30 MB | about 100 MB | about 1 minute |
  | Ninja | under 1 MB | under 1 MB | under a minute |
  | FFmpeg (`Gyan.FFmpeg`) | about 100 MB | about 300 MB | about 2 minutes |
  | Visual Studio 2022 Build Tools: C++ workload, Clang tools, Windows SDK | about 3 GB | about 7 GB | about 15–40 minutes |
  | Everything on a clean machine | up to about 4 GB | about 10-12 GB | about 30–60 minutes |

  Administrator rights: the Visual Studio build tools need them, and the machine-wide installers (LLVM,
  CMake, the ARM toolchain, git) may each show a Windows permission prompt too; Python and its packages
  need none. Plain words for the user, e.g.: "up to about 4 GB to download and about 11 GB of disk space,
  30 to 60 minutes; Windows may ask for administrator permission a few times: accept each." On macOS the
  ARM compiler's installer asks for the user's password once.
- What the user must do themselves, in plain words, when something cannot be installed for them: on
  Linux the package line
  `check_env.sh` printed (it needs their password: they run it); on macOS `xcode-select --install`
  (Apple's installer) and the Homebrew line; on Windows without winget the download pages.
- The yes is the one-time environment approval (`cube_orchestrator/references/AGENT_SAFETY.md`): after it
  the infra gate passes `-GetSim` / `--get-sim` to `new_app` and runs `check_env.ps1 -Install` (winget may
  still ask to accept its agreements unless the user accepted them: `-AcceptAgreements`). Record
  `install_consent: {"answer": "yes"|"not_now", "date": ...}` in `~/.wowcube/config.json` (the one shape,
  `references/PROFILE.md`; merge, keep the other keys); on *Not now* ask again only when the user brings it
  up or starts or resumes a build: an entry with `install_consent: not_now` and a build request asks this
  question again (one line on why) before anything else, never silently goes on and never re-runs the
  whole setup.
- **Nothing starts before the yes** (design included; only *Art only* needs none of it). Once the user
  agreed, while the installs run or wait for something only the user can do (a package line, an
  administrator prompt), the design and the art may go on; nothing is built before the installs are done
  and Claude Code was restarted.
- **After the installs: save, then restart.** First write both profiles (Step 3: every answer is saved in
  `~/.wowcube/config.json` and `<ws>/wowcube.project.json`, and the orchestrator saves the game's context
  when one is under way); only then: "Please close Claude Code, open it again in this same folder, start a
  new session and say 'continue': the new tools are only found by a new session. Everything is saved."
  Then stop this session: a waiting question cannot span sessions. The next session continues from the
  saved profiles: it finds both files, asks nothing again, runs `check_env` once more and goes on.
- **No admin rights, a declined Windows prompt, or a failed install** (`check_env` prints `[FAILED]`
  lines): say plainly that the game needs these programs on this computer, list exactly what is missing
  with where to get it (the name and the download page: "Python 3.12: python.org/downloads"; "Visual
  Studio Build Tools, with 'Desktop development with C++': visualstudio.microsoft.com/downloads"; "Arm
  GNU Toolchain: developer.arm.com/downloads/-/arm-gnu-toolchain-downloads"; "CMake: cmake.org/download";
  "Ninja: github.com/ninja-build/ninja/releases"; "LLVM: github.com/llvm/llvm-project/releases"; "FFmpeg:
  ffmpeg.org/download.html"), ask them to install it or to ask whoever manages the computer, and stop.

### Step 2c: *Art only* (`entry: art`)

No game, no build, no question about the build components. What it needs: Python with Pillow and numpy
(`art.py doctor --no-codex` checks them when the art is drawn in code or is the user's own; plain `art.py
doctor` when Codex draws), and the drawing route from the tools answer. When Python or those packages are
missing (a clean computer), ask one small question instead of stopping: **"To draw and check the pictures
I need Python on this computer (about 150 MB, a few minutes, no administrator rights). OK to install it?"**
Yes → only Python and the packages: Windows `winget install --id Python.Python.3.12 -e --scope user
--silent`, then that Python's `-m pip install -r <skills>/scripts/requirements.txt` (the per-user Python
is at `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`: call it by that full path in this session,
`python` on the old PATH does not find it until a restart); Linux/macOS the
`~/.wowcube/venv` venv (`python3 -m venv ~/.wowcube/venv`, its pip, the same requirements; a missing
`python3` / `python3-venv` is the one package line the user runs). Never the build components on this
path. *Not now* → say plainly that the pictures cannot be made without it, and stop. Route to `cube_art-director` standalone
("Art only", its SKILL.md): the user is the artist (style lock with them, generation through what they
have or drawn in code, strict QA), and the delivery is PNG files, a sprite sheet with its atlas
(`art.py sheet`), and on request a cube-packed asset set. The guidance answer sets the picture budget
and the review rounds (through `verification`, Step 2) and how often it stops (*Just show me results*: the style frame and
the finished set).

### Role and experience (every path, never asked)

Role: do not ask it as a question. Infer it from the answers and use only its defaults
(`references/PROFILE.md`, "Role defaults"), in this order:
1. the user says they work at WowCube → staff;
2. their own design document, or they said they know C++ (*Step by step, I know C++*, or their own words) → developer;
3. everyone else → creator. That includes *On my own* and *Just show me results* by someone new to WowCube
   or to game making: the role gives the plain-language defaults, and the Guidance answer still
   wins for `guidance`, `scope_cuts` and `verification`, as it always does.

Experience (`experience`, how messages are worded) is recorded on every path, never asked separately:
*Step by step*, *Just show me results* and the defaults → `new`; *Step by step, I know C++* → `cpp`;
*On my own* → `cpp` only when the user's words show it (C++, "I'm a developer", their own technical design document), else `new` (plain
words cost nothing, jargon confuses a newcomer).

## Step 3: write the profiles

Written as soon as the answers are in, before any install and before a restart is asked for (Step 2b):
a new session resumes from these files, never from the chat.

1. `~/.wowcube/config.json` (machine): detection results, the install consent, the provider choice and its
   credential reference, the workspace paths. Generation reads the choice from here and from the project
   file (`scripts/profile_provider.py`; precedence: `references/PROFILE.md`, "Image provider"). Create
   `~/.wowcube/` if missing. Merge with an existing file; keep unknown keys.
2. `<ws>/wowcube.project.json` (project intent): entry mode, guidance, the user's resources in their words,
   verification tier, budgets, provider id, data policy, the design document's path. Shareable: no
   secrets, no machine paths outside `<ws>`.
3. Show the user a short summary in plain words and the estimate from
   `cube_orchestrator/references/RUN_MODES.md` ("Estimate": time and tokens from the game's size), e.g. "A
   new game, I work on my own and stop to show you the look and, at the end, to ask about the install
   link; pictures drawn in code, sounds made in
   code; every step checked by two reviewers and an automatic playtest: about 45–75 minutes and about 1
   million tokens for a simple game (my estimate). A game can take more than one usage window of your
   Claude plan: if the limit runs out, everything is saved, and you say 'continue' when it resets. Change
   anything? Say 'change my settings'." Art only: "Sprites for your
   game, drawn in code in one style, I show you the look and the finished set: about a minute per picture
   plus the reviews; you get PNGs and a sprite sheet."
4. Return to `cube_orchestrator` with the resolved snapshot (`references/PROFILE.md`, "Resolution").

## Missing pieces: tell once, then go on

For each gap that the chosen path needs, one line in plain words with what happens or what the **user**
runs (installs need the one-time approval of Step 2b, AGENT_SAFETY.md). *Art only* needs none of the build
rows.

| Gap | Says |
|---|---|
| Build-check components not installed (internal: the simulator; `check_env` `[MISSING]` with the `get_sim` command) | covered by the Step 2b question; after the yes "Installing the build checker (about 6 MB)…" and the agent runs `get_sim` (it copies the prebuilt checker this plugin carries: no download, nothing to build); nothing starts before the yes, and after it the design and the art may go on while the installs run (Step 2b) |
| Build tools incomplete (internal: the plugin compiler, CMake, Ninja) | Step 2b: installed after the yes where `check_env -Install` can (Windows); otherwise the plain line of what to install and the command `check_env` printed |
| Codex chosen, not logged in | "Run `codex login` and choose ChatGPT" |
| Codex logged in with an API key | "ChatGPT's drawing tool is logged in with a paid key and would bill it; run `codex login` and choose ChatGPT, or pick another option" |
| Provider chosen, key not set | the variable name to set in their own shell (they set it; you never type a key) |
| Node/Playwright missing | only when a prototype or video is wanted: `npm i --prefix ~/.wowcube/node playwright`, then `npx --prefix ~/.wowcube/node playwright install chromium` (never into the plugin folder) |
| ARM toolchain missing (the cube's compiler) | needed from the first build on: every build is first compiled the way the cube compiles it (internally every `build_game` compiles the game with `arm-none-eabi-g++` and the cube's `-Werror` flags before the checker's plugin) and the final cube file is built with it; part of Step 2b, a hard stop before the infra gate until it is there |
| Python or its packages missing | Step 2b: installed after the yes (`check_env.ps1 -Install`; Linux/macOS the package line), then the restart |

## Reconfigure

"reconfigure", "change my settings", "setup", "change the budget", "switch to Codex", "I have Gemini now":
re-run Step 1, ask only the questions the request touches (all three on a bare "reconfigure"), rewrite the
files, report what changed. Without such a request an existing `<ws>/wowcube.project.json` is never
rewritten: when only `~/.wowcube/config.json` is missing, detect the machine (and ask the install
question), and keep the project's answers. A running game keeps its run state (stage, scores, spend); the orchestrator re-resolves the
profile at its next entry, so new limits, tier, art source and `guidance` (the run mode) apply from then
on (`references/PROFILE.md`, "Resolution").
