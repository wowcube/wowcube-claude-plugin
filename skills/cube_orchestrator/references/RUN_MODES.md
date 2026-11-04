# Run modes (cube_orchestrator reference)

Read this before the intake of every new run. The run mode comes from the resolved profile
(`wowcube-setup/references/PROFILE.md`): `guidance: guided` = **stepwise**, `guidance: autonomous` =
**autonomous**. The current prompt overrides it for this run ("stepwise", "step by step", "stop and wait");
nothing else carries across turns, except a mid-run "stop and wait" that switches the rest of that run to
stepwise ("Interrupts" below: "stop, change X" does not). The context's
`run_mode` is a record of this rule, rewritten at every entry, never a source: after a reconfigure the
new `guidance` applies from the next entry. User phrases
quoted in this file are English examples: recognize the same intent in any language, and write every
message to the user in the user's language.

| Mode | How it activates | Behaviour |
|---|---|---|
| **Autonomous** | profile `guidance: autonomous` (the built-in default); never asked to confirm, no risk speech | Intake (only what the profile left open), one start line, then the whole pipeline to the verified device `.oct` **within the budget**. Stops at the **style lock** (the one creative checkpoint), for real blockers (below) and when the budget is spent. |
| **Stepwise** | profile `guidance: guided`, or "stepwise", "step by step", "with checkpoints", "review mode" in the prompt, or "stop and wait" / "pause after each step" mid-run | Every checkpoint in the skill is in force: stage boundaries, the designer interview, the asset batch review, each prompt, each mod change. Nothing advances without an explicit "ok / next". |
| **`YOLO` token (compat alias)** | The literal token `YOLO` (case-insensitive) in the body of the current prompt, then one short risk confirmation (below) | Autonomous, plus: no intake questions (no concept → the designer invents one; no Codex → the procedural style, drawn in code at final quality) and the style lock is waived (an independent reviewer approves the style frame instead of the user). The budget still applies. |

`YOLO` activation is literal: no paraphrase or translation counts ("autonomous
mode", "go autonomous", "just run it to the end", in any language, do not), it is never inferred from tone,
and a previous prompt's token does not carry over. It removes stops, never checks.

**YOLO risk confirmation** (the one message before a `YOLO` run; in the user's
language; wait for an explicit "yes", anything else → the default autonomous
mode):

> YOLO: I'll run to the finished file without stopping. I'll invent the game if the request has none, and I won't show you the art style for approval (an independent reviewer checks it instead). Risk: the result may not be what you wanted and may need rework. YOLO does NOT approve paid APIs or downloads: without Codex the art is drawn in code and the sounds are synthesized. Start? (yes / no)

**Paid image APIs need the user's own explicit opt-in, in every mode, per run.** Neither the
autonomous mode, `YOLO` (nor its confirmation), nor a provider chosen in the profile implies consent
to pay: a paid provider (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `XAI_API_KEY`, `OPENROUTER_API_KEY`,
`IMAGE_API`, `~/.wowcube/image_api.json`) is used only when the user, in this run, said yes to paying
per image for this batch; only then set `WOWCUBE_ALLOW_PAID_IMAGES=1` / `--allow-paid`. A key that is
merely configured is not consent. A local Stable Diffusion server on this machine (`http://localhost`
/ `127.0.0.1`) costs nothing and needs no opt-in.

## Interrupts, questions and changes mid-run

- **"stop, change X"** (or "wait, make it faster", "hold on, X") is an interrupt, not a mode switch: finish
  the atomic step in flight (a coder run, a generation batch), save, apply X (the light lane below when X
  is a tunable), then **resume in the same mode**.
- **"stop and wait"**, "pause after each step", "step by step" switch the rest of the run to stepwise: finish
  the step in flight, save, stop.
- **Back to autonomous**: "continue on your own", "don't stop anymore", "just continue", "go on to the end"
  (any language) end the stepwise switch: the rest of the run is autonomous again (the profile's
  `guidance` is unchanged; "reconfigure" changes it for good).
- **A question is answered, never executed.** "Can I ...?", "how do we ...?", "is it possible to ...?",
  "what would it take to ...?": answer it (what it would change, roughly how long and how many tokens),
  then ask whether to do it. Only an instruction ("do it", "add ...", "make ...") starts work.
- **A request the user mentions but does not start** ("my boss may want a new level", "maybe a pink ship
  later", an offer they answered "later") goes to the context's `pending` list (`AGENT_BRIEFS.md`,
  "Context file") with their words and the date, and is shown on the next entry ("Open from last time:
  ..."). Done or dropped → removed.
- **A change of the game's structure** (a new level system, a new mode, a new mechanic, a different
  progression; Mod mode T4) always stops for a short mini-plan approval, in every mode, `YOLO`
  included: first say that this starts a new round of work and what it costs (the estimate: time and
  tokens from the planned prompts), then the mini-plan from `cube_game-designer` (what changes for the
  player, the GDD update, the new parts); nothing runs before the user's yes. Rebuilding, installing and
  re-checking afterwards follow the normal flow; whether to start is the user's call.
- **A reference to an existing game** ("like Minecraft", "Tetris but ...") is clarified before any design,
  in every mode, with one short question: its look, which mechanic(s), or what exactly ("Like Minecraft
  how: the blocky look, digging and building, exploring, or something else?"). The answer goes into the
  concept.

## Light lane: a tunable change in minutes

A change that only edits named values in the game's tunables block (speed, counts, timings, sizes, colours
defined there; the block from `technical_prompter` Step 5a) is done in minutes, not a review round:
1. snapshot (`scripts/history.py snapshot`, below "History and undo");
2. edit the value(s) yourself (the one place the orchestrator writes game code: only the literal values in
   the tunables block, nothing else; anything more is a coder task) or one small coder call;
3. build the plugin (it runs the ARM `-Werror` device check too) and ONE hidden visual-gate run, look at
   the frames, delete them;
4. update the GDD's tunables table, record it in the context (`balance_passes` when it is balance), and
   rebuild the device `.oct` (`repack_app.py`: minor version bump) when the user will install it.
No code reviewer, no playtest unless the user asks for one. Target: a couple of minutes.

## History and undo

Before every change to a game (each prompt's coder run, each mod, each tunable change, a restore
included) take a snapshot:
`python <skills>/scripts/history.py snapshot --workspace <ws> --game <game> --label "<what>" --request "<the user's words>"`
(add `--assets` when the change touches pictures or sounds). It copies the code, the plans and the context
fields a change moves into `<ws>/.history/<n>_<label>/` (no build output, no frames) and records it in the
context's `history`.

"Undo the last change" (any language): `history.py restore --workspace <ws> --game <game>` puts the latest
not-yet-undone snapshot back (code, tunables, manifest, plans, those context fields; pictures and sounds when
it was an `--assets` snapshot) and keeps the version and `APP_GUID1`. Then rebuild and check as for any
change (plugin build, one visual gate; `build_pipeline.py pack` first for an `--assets` restore), build the
device `.oct` with `repack_app.py` (the minor version still goes up: the cube only installs a newer
number), and tell the user in one line what was undone ("Undid: the snake speed change (0.25 s back to
0.40 s)"). A second "undo" goes one change further back; the state before an undo is kept as a `pre_undo`
snapshot ("redo" restores it with `--n`).

## Hard invariants (every mode, every tier)

These decide whether the result runs on the cube; no mode, tier or budget suspends them.

- Every prompt passes its tier's code review (≥ 90, below), no unresolved **critical** finding from
  any check whatever the score, no open **major** unless accepted with a reason in the context
  (`accepted_majors`), and the **visual gate** (hidden simulator, all 24 screens, the agent looks at
  the frames). The visual gate is never dropped, in any tier.
- **A prompt is never marked complete while a gate fails.** When the fix rounds are used up, the
  prompt is rescoped (failure policy below) and the rescoped version must pass every gate, or the run
  stops with a report.
- The orchestrator never writes code, design, prompts or assets itself (one exception: the literal values
  of the tunables block in the light lane above).
- `_ids.h` is never hand-edited; a partial asset set is never packed:
  `build_pipeline.py pack` refuses it before writing anything.
- Art is packed only when every rule in `cube_art-director/references/QA_RULES.md`
  passes, or a spent image budget waived a style rule on the record (STAGE3_ASSETS.md §3);
  placeholder art (`art.source: placeholder`, only on request) is never presented as final; the
  procedural style is final art.
- Downloads only after the user approved the list (the `YOLO` waiver is not an approval of downloads).
- Paid image APIs only after the user's explicit opt-in in this run (`--allow-paid`).
- Material leaves the machine only as the profile's `data_policy` allows (prompts and references to
  Codex or a provider; nothing when the list is empty).
- The deliverable is the Stage 5 device `.oct` with verified ARM code, in `dist/`;
  never a simulator-written `.oct`.
- `references/AGENT_SAFETY.md`, for you and in every subagent brief.

## Verification tiers

The tier comes from the profile (`verification`), which follows the guidance answer (owner decision
2026-11-04; there is no question about checking): **autonomous** (*On my own*, *Just show me results*,
the default) = `lite`, the quick lane; **guided** (both *Step by step* answers) = `full`. `standard` is
never offered to the user; it exists only when the user asks for it in their own words ("check it more
but not every detail"). A request may raise the tier for one run ("check everything thoroughly" →
`full`); nothing lowers the checks below `lite`: "fast", "quick" or "just a simple game" picks the
quick structure, never fewer reviewers or playtests. The hard invariants above hold in all three.

The id `lite` is kept so that existing profiles keep working; since 2026-11-04 it no longer means lighter
checks: an older project file with `verification: lite` gets the checks below without any change.

| | `lite` | `standard` | `full` |
|---|---|---|---|
| Prompts (`technical_prompter` sizes them by the game) | **1** when the core loop, input, scoring and game over fit one coherent change (snake, tap-the-target, a simple puzzle); **2** when the game also has separate structure (1 = the core loop playable on all faces with its input; 2 = title, levels, game over, sound, polish). Never more | as many as the game needs, each a testable slice (a small game usually 4-8) | as `standard` |
| Code review | Requirements Agent + Template Agent, two separate reviewers, every prompt | Requirements Agent + Template Agent | Requirements Agent + Template Agent |
| Re-check after a fix | both re-check the diff (`cube_verifier` "Re-check rounds") | both re-check the diff (`cube_verifier` "Re-check rounds") | both re-check the diff; a full review whenever `cube_verifier` asks for one |
| Visual gate | every coder and fixer run | every coder and fixer run | every coder and fixer run |
| Playtest Agent | every prompt | every `foundation`, `core` and `secondary` prompt, plus any prompt that adds or changes an input or a mechanic | every prompt |
| Max fix rounds per prompt | 2 | 3 | 5 |
| Rescopes per run (autonomous) | 2 | 3 | 5 |
| Default image budget (Stage 3) | 30 | 80 | 200 |
| Fresh art reviews (Stage 3), then focused re-checks of the fixes | 2, then 2 | 3, then 2 | 5, then 3 (still open after them: waived on the record and reported, STAGE3_ASSETS.md §10) |
| Who gets it | autonomous guidance (*On my own*, *Just show me results*, the default) | only on the user's explicit words | guided (*Step by step*), or "check everything thoroughly" |

**The quick lane (`lite`).** One or two prompts, and every prompt gets the full set of checks: the plugin
build with the ARM `-Werror` device check, a hidden run with the 24-screen review (frames looked at, then
deleted), the Requirements Agent and the Template Agent as two separate reviewers, and the Playtest Agent;
at most 2 fix rounds; then the device `.oct` and `pack_beta.py --verify-oct` as always. What makes it
quick is the structure (few prompts, few fix rounds, a small image budget), never fewer checks. Every
autonomous run gets this lane unless the profile or the request says otherwise.

**The playtest rule (`standard`; `lite` and `full` playtest every prompt), one sentence:** a prompt gets the Playtest Agent when its category is listed for
the tier **or** it adds or changes an input (a tap, twist, tilt or shake the game reacts to) or a
mechanic (a rule of play), **whatever its category**: a `ui` prompt that adds "tap to restart" or a
`polish` prompt that changes how a twist moves the hero is playtested in `standard` too. The
prompt says so itself (`### Input or mechanic change`, `technical_prompter` Step 5); when that line is
missing, read the Goal and Verification: any input or rule of play named there counts as a change.
Mods use the same table (orchestrator SKILL.md, M5: a mod's type maps to a category). The playtest needs the hidden instance's control socket; without it the visual gate carries the
prompt and the report says nobody drove the game. The profile's `budget.images` and
`budget.fix_rounds` override the table.

## Estimate (the start line and the setup summary)

Measured on real runs (the `lite` rows are estimates built on the old `lite` measurements, labelled so), whole runs including setup checks, art drawn in code, the device `.oct`. Compute the
estimate from the **planned number of prompts** (`plans/<game>_prompts.md`; before Stage 2, from the game's
size: a simple game is 1-2 prompts in `lite`, a small game 4-8 in `full`), never from a fixed count,
and say it is an estimate.

| Measured run | Time | Tokens |
|---|---|---|
| `lite`, a 1-prompt simple game | estimate: about 30–45 min (old lite, one reviewer: ~17 min measured, release 2.4.0) | estimate: about 1M (old lite: ~0.6M subagents) |
| `lite`, a new small game (2 prompts, art in code) | estimate: about 1.5–2.5 h (old lite, one reviewer and a playtest only on the last prompt: ~1 h 40 min measured in a QA run) | estimate: about 1.5M subagent tokens, about 2M with the main session (old lite: ~1.2M subagents measured) |
| `standard`, a studio game, 8 prompts | ~2 h 15 min | ~3.5M (subagents) |
| `standard`, one single-feature mod | ~25 min | ~0.85M |
| `full`, one foundation prompt with one fix round | ~1.5 h | ~2M (subagents) |
| a light-lane tunable change | a few minutes | well under 0.1M |

Per prompt, for the formula: `lite` a 1-prompt game, setup and delivery included, about 30–45 min and
about 1M tokens, and each further prompt about 45–75 min and about 0.5–1M tokens (two reviewers and a
playtest per prompt; estimates, the new `lite` is not measured yet); `standard` ~17 min and ~0.45M subagent
tokens plus ~10% for the main session; `full` ~1.5 h and ~2M. Art adds about 2-4 min per Codex picture
(about a minute per picture drawn in code) and ~45 min for the fresh art reviews (`lite`: ~15 min).

Never name, invent or guess subscription plans. Say the time and the tokens; when the user has told you
their subscription and its weekly limit in tokens or as they know it, add roughly what share of that limit
the run takes; for the real number point them to their usage page ("Cost questions" below).

### Cost questions (quote these)

- **"How much will it cost / is it free?"** It runs on the AI the user already has (their Claude
  subscription or API key): no extra charge from this kit. It uses tokens: "about N million tokens by my
  estimate" (the table above). Drawing in code and synthesized sound cost nothing more; an outside image
  service is used only if the user picked it themselves (a paid one asks before every batch).
- **"How much of my plan is that?"** Only if they tell you their plan and its limit: "roughly X% of a
  weekly limit". Never guess a plan. The real usage is on their Claude usage page (Claude Code: `/usage`;
  claude.ai: Settings > Usage; an API key: the Anthropic Console).
- **"What if my limit runs out mid-run?"** The run stops where it is; everything done so far is saved in
  the project folder. When the limit resets, open Claude Code in the same folder and say "continue": it
  resumes from the files.
- **"Will the AI train on my art / my game?"** No: this pipeline does not train any model on the user's
  work. If they chose an outside tool (ChatGPT/Codex, an image service), that provider's own data
  settings apply to what was sent to it.

Add the art: about 2-4 min per image (images = the manifest's sprites plus redraws, capped by the image
budget), and ~45 min for the fresh art reviews. *Art only* (`entry: art`) is just this part: the pictures
and the reviews, no code (drawn in code: about a minute per picture, no image budget spent).

**Mods** are estimated per change, not per prompt:

| Mod | `lite` | `standard` / `full` |
|---|---|---|
| One change (M0 import incl. art extraction, the change, its gates, the repack and the device `.oct`) | estimate: about 1–1.5 h, about 1.2M subagent tokens (old lite with one reviewer measured ~1 h, ~1M: one sprite change on a game delivered without art sources; now two reviewers and a playtest) | `standard`: ~25 min, ~0.85M tokens (~0.6M subagent + ~0.25M main session; measured 2026-11-03: a fork adding one small feature with three code-drawn sprites, Claude only, art drawn in code; one fresh art review, no fix round). `full`: not measured |
| Each further change in the same run | less: the import, the baseline frames and the extraction are done once | |

A tunable change (speed, timing, a count) goes through the light lane: a few minutes. A T4 structural
change is estimated like new prompts (the mini-plan says how many).

## Intake (once, before going quiet)

Ask only what the profile and the prompt leave open; ask nothing mid-run. Questions are short, with
options (AskUserQuestion), never a wall of text. No profile yet → `wowcube-setup` first.

1. **Game concept** — only for entry `new` and only if the prompt has none at all: "What is the game
   about? One sentence, or say 'your choice'." Any genre, theme or mechanic in the prompt means no
   question. A concept that names an existing game ("like Minecraft") gets the one clarifying question
   ("Interrupts", above), in every mode.
2. **Art access** — only if the profile's art source cannot work now: Codex chosen but
   `art.py doctor` fails on the CLI or the ChatGPT login → the user runs `codex login` themselves
   (never type credentials). "can't" / "no" → the procedural style (drawn in code, final quality; temporary
   placeholders only when the profile asks for `art.source: placeholder`), one line in the final report. A paid provider is used only when the user
   says, in this run, that they agree to pay per image (then `--allow-paid`;
   `cube_asset-builder/references/ART.md` "No Codex").

Not a question but a blocker, reported at intake when the entry checks find it: the bundled simulator
or build kit is missing or older than the pipeline needs, or the toolchain is incomplete. Send the
exact fix once (SKILL.md, entry check 3); design, prompts, art and sound continue; the run waits before
the infra gate until the user says it is done.

"I don't know", "you choose", "skip setup", "just do it", or no answer to a question: take the defaults
and go on autonomously: the AI the user came with (Claude), the art drawn in code, the sounds synthesized,
no outside service, the autonomous checking (`lite`: few prompts, full checks). Outside services (Codex, an image service, downloaded sounds)
only when the user picks them by name.

`YOLO`: after the risk confirmation, skip questions 1 and 2 (invent the concept; no Codex → the
procedural style, never a paid provider unless the prompt itself explicitly asks for one and agrees to
pay). The environment blocker still applies.

**Start line** (autonomous; in the user's language, plain words), printed once, then continue without
waiting for a reply:

> Making your game for the cube. I'll stop once to show you how it will look, then go on my own to the finished game. Estimate: about 30–45 minutes and about 1 million tokens of your AI usage. If your usage limit runs out, everything is saved and we continue later. Want to approve each step? Say "step by step".

Fill the estimate from the table above, the profile's tier and the planned number of prompts (before
Stage 2, from the game's size: "Estimate"). Guided runs give the same estimate in their first message.

## Plain language (the default for everyone)

Plain words for every user until they show otherwise (they use the technical words themselves, say they
are a developer, or `experience: cpp`). Talk about the game, not the machinery. Never say "manifest",
"stage", "verifier", "prompt", "gate", "rescope", "subagent", "tier", "pack", "playtest", "Playtest Agent", "reviewer", "agent", "GDD", ".oct", "CC0",
"Codex", "PSD", "simulator", "toolchain", "compiler", "SDK", "plugin", "winget", "pip", "repository",
"API", "token" (except in a cost answer), "build kit", "reconfigure" (say "change my settings"). Say
instead: "the list of pictures and sounds", "step", "the checks", "a part of the game", "simplify",
"helper", "the code check", "the screen check", "the automatic gameplay check", "the game's description", "the game file", "free sounds anyone may use", "ChatGPT's drawing
tool", "a Photoshop file", "the automatic checks", "the tools that build the game". Numbers the user can
act on ("3 of 10 parts done, about 4 hours left") beat scores ("Template 92").

Two words stay out even for developers: "simulator" (the user never sees or controls it: say what is
checked, "checking the game", "all 24 screens look right") and "store" (say "an install link and a QR
code for your phone"; the consent question names WowCube's servers, not a store).

When a term has to appear (a file name, the user asked), explain it once in a few words:

| Term | Say |
|---|---|
| GDD | the game's description: what happens, the controls, the pictures and sounds it needs |
| `.oct` | the game file the cube installs, like an app on a phone |
| CC0 | free sounds and pictures anyone may use, no credit needed |
| Codex | ChatGPT's coding and drawing tool; it draws on the user's ChatGPT subscription |
| PSD | a Photoshop file |
| tokens | how AI usage is counted; a subscription allows a certain amount per week |
| the automatic checks | the computer plays every version of the game and looks at all 24 screens (never "the simulator") |
| QR code | a square code the phone camera reads; it opens the link that installs the game |
| style lock | the one stop where the user approves how the game looks before everything is drawn |

## What each mode does at each checkpoint

| Checkpoint | Stepwise | Autonomous |
|---|---|---|
| Stage boundary | Summarize, STOP, wait | One progress line, re-run stage detection, continue |
| Designer discovery interview / GDD import questions | Short questionnaire | GDD from the concept or the document, no interview; open questions answered with recorded defaults |
| Asset source (AI / own art / PSDs / procedural) | From the profile; ask only if unset | From the profile |
| **Style lock: style frame + mock** | STOP, iterate until approved | **STOP, iterate until approved** (waived only by an explicit user statement or `YOLO`) |
| **Sound list (downloads)** | Approve with the style lock | **Approve with the style lock**; not approved → synthesis. `sound.source: synth`: no list, nothing to approve |
| Art batch review (`review.html`) | The user marks OK / Fix | Fresh-agent review instead; page linked in the final report |
| Execution plan before Stage 4 | Present, wait | Dependency graph, continue |
| Per-prompt checkpoint | Summary + the agent's frames, STOP | Save context, next prompt |
| Fix rounds used up | Ask: simplify / try again / stop | Rescope if `scope_cuts: auto` and the rescope budget allows, else stop with a report |
| Budget spent | Save, ask: more budget / simplify / stop | Save, stop with the report |
| Mod mini-plan, per-change check | Present, STOP | Auto-approved, mods back-to-back; a structural change (T4) always stops ("Interrupts") |
| Store upload and install QR code (Stage 5) | Ask once, then upload | Ask once ("Make an install link and a QR code so you can put the game on your cube from your phone? (The game file is sent to WowCube's servers for that.)"), then upload; the run's only other stop |

**Real blockers** that stop autonomous mode: the environment (simulator, build kit, toolchain; the ARM
toolchain from the infra gate on, since every build's device check needs it, CMake and Ninja at Stage 5; a hidden simulator that stops working mid-run, failure policy 5), the Codex login when the profile wants Codex art, a spent run budget (not the image budget), and a game whose simplest
playable loop still fails the gates.

## Safe parallelism (Stage 4)

All game code is one file (`app_<game>/src/app_<game>.h`), so coding is sequential.

1. Build the prompt dependency graph first: foundational (scaffold, data structures,
   core init) vs cosmetic/isolated (audio, polish, UI text).
2. The code reviewers run in parallel with each other and with the visual gate's
   build; prepare prompt N+1's brief while N is being checked.
3. Never dispatch the next coder before prompt N has passed every gate (the visual gate
   builds from that file); never run two coders that could touch the file.
4. Foundational prompts are strictly sequential and fully verified before anything
   downstream.
5. **One hidden simulator at a time**: visual-gate runs and playtests never run in
   parallel (one binary, one port).
6. Art: `art.py gen --jobs 3` parallelizes Codex calls; the review loop decides what to
   redraw.
7. A host without subagents (`host.subagents: false`): you play each role in turn, with a fresh read of
   the files for every review and no memory of having written the code; say so in the report.

## Failure policy: bounded, then save and ask

A failing prompt never counts as done, and the run never loops without end. Everything is counted in
the context (`fix_rounds` per prompt, `rescopes_used`, `images_used`, the time since the start).

1. **Fix rounds** (the tier's maximum, or `budget.fix_rounds`): one fixer per round with the union of
   all findings, then every gate of the tier again.
2. **Rounds used up** →
   - stepwise, or `scope_cuts: ask`, or a cut that touches an approved studio GDD (`source.approved:
     true` wins over `scope_cuts: auto`; `wowcube-setup/references/PROFILE.md`, "Precedence of
     `scope_cuts`"): save, then ask
     "The check still fails after N attempts (best score X). Simplify the feature / try again / stop?";
   - autonomous with `scope_cuts: auto` and rescopes left: **rescope** = cut or simplify the failing
     feature in this prompt's instructions and record the cut (you change scope only; coders still write
     all code). The rescoped prompt gets a fresh round budget and must pass every gate. A foundational
     prompt, or a build that does not compile or renders nothing, also gets ONE pass over the remaining
     prompts (simplify or drop what builds on the missing piece).
   - visual or playtest findings: the rescope cuts or simplifies the feature that shows them (an effect,
     an extra animated layer, a tilt mode); the findings and frames go into the cut's record.
3. **Budget spent** (rescopes, the profile's `hours`, or the user's usage limit as they stated it) →
   finish the step in flight, save the context, then: guided → ask "more budget / simplify / stop";
   autonomous → stop with the end-of-run report (what works, what was cut, what failed, the command to
   resume). Never deliver a build whose gates fail. The **image budget** is not a run budget: spent, it
   ends the redraws only (STAGE3_ASSETS.md §3: processing fixes and recorded waivers), and the run goes
   on to the pack and Stage 4.
4. **Art rule that genuinely cannot be met** (after real changes to prompt, references and processing)
   → simplify the asset within its manifest entry (same name and size) until QA passes, record it;
   when the image budget is spent, STAGE3_ASSETS.md §3 decides.
5. **Visual gate unavailable** (the hidden tool itself broke, not the game) → try to fix the tool; if
   that fails, the prompt stays open (never passed): record it in `not_checked_visually`, save the
   context and stop with the tool's error; guided and autonomous alike (a real blocker, below). After
   the tool is repaired, the gate runs again on the same prompt and its code; the next coder starts
   only after it passed (safe parallelism, rule 3).

The floor is the simplest playable loop that passes every gate; every cut is in the final report.
Nothing is dropped silently.

## Progress lines and the final report

During an autonomous run: one-way progress lines at stage transitions, in the user's
language, plain words (see "Plain language"): "design done → drawing the art (~20 min)…",
"art done → writing the code, part 1 of 10…".

The final report (autonomous; also the end of a stepwise run), plain language. Stage 5 writes it to
`context/<game>_report.md` (overwritten at every delivery) and shows it in the chat:

1. **Install it**: the QR code (`dist/app_<game>_qr.png`) and the link from the store upload, with one
   line: "Scan the QR code with your phone (or open the link on it): the WowCube app installs the game on
   the cube connected to the phone." The version, and the game file `dist/app_<game>.oct`. Not uploaded
   (the user said no) → say that the game is ready and the QR code comes with "upload it".
2. **What was checked**: what the checks covered, the gameplay video if made, the art review page
   (`assets_<game>/review.html`), and what no check could judge (how it sounds, how it feels, balance,
   the real cube).
3. **What was cut or simplified** — every item, one line each; a prompt waiting for the visual gate
   (`not_checked_visually`); what the budget stopped, and how to resume ("say 'continue'").
4. **Temporary parts**, one line each when they apply: "The art is temporary: log in to
   Codex (`codex login`) and say 'redraw the art'."; "The sounds are synthesized: say
   'find real sounds'." (only when recordings were the plan); "You did not approve the style: say so
   if you want another one." The procedural style and a chosen `sound.source: synth` are not
   temporary: say they were made in code on purpose.
5. **Spend**: time taken, images drawn, fix rounds and rescopes used, against the budget.
6. **Sound credits**: `app_<game>/sound/CREDITS.md`.
7. **How to play**: the controls (taps, twists, tilt), what to try first.
8. **Next**: the on-device checklist (short), an offer of a balance pass, and the open requests
   (`pending`).

Per-prompt scores, fix rounds and gate verdicts stay in
`context/<game>_context.json`; give them when the user asks.

## Coming back: "is my game done?", "what were we doing?"

A status question is read-only: answer it from `context/<game>_report.md`, the context and `dist/`;
run no `check_env`, no build, no check, and do not rewrite the context or the profile.
- **Every stage done, nothing changed since the delivery** (stage detection's last row is done): a plain
  recap in a few lines: the game's name and what it is, that it is finished and installable (the QR code
  and the link again), what was simplified (one line), and what they can do next: install and try it,
  ask for changes ("make it faster", "a new colour"), undo a change, or start a new game in a new folder.
- **The last part passed and the user has said nothing since**: they have not looked yet. Say it is ready,
  where it is (the QR code and link; the report), and ask them to install and try it. Never rebuild or
  re-check for this.
- **Open requests** (`pending`): list them ("Open from last time: a pink ship, a harder mode") and ask
  which to start.
- **Work left**: where it stopped, what is next and the estimate for the rest; "continue" resumes.

## Stepwise specifics

- Every stop presents what was produced (paths, counts, frames) and waits for an
  explicit answer; silence is not approval.
- The per-prompt checkpoint arrives with the agent's own evidence (frames sheet,
  playtest findings) and leads with what the agent could not judge, so the user's
  time goes to feel, difficulty, sound and pacing.
- The hidden test copy of the cube is an internal checking tool: never offer it to the user as a way to
  play. To try the game, the user installs it on their cube (Stage 5's QR code; a mid-run install needs a
  device build, `repack_app.py`, and a store upload with their yes).
- Long builds: suggest one stage, or one batch of prompts, per session. Everything
  resumes from the files (`plans/`, `assets_<game>/`, `context/`).
