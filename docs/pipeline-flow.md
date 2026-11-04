# WowCube game pipeline: the flow

End-to-end flow driven by `cube_orchestrator`, from a request to a verified `.oct` on
the user's cube. The default run mode is *On my own* (autonomous): exactly two planned stops,
the style lock and the install-link question at the end (`STOP, always`); the stops marked
`STOP, step by step` happen only when the user chose *Step by step* (stepwise mode). Nothing is
installed on the cube before the end. Rules: `skills/cube_orchestrator/SKILL.md` and its
`references/`.

```mermaid
flowchart TD
    U(["User: make a game / continue / mod / upload"]) --> ORCH["cube_orchestrator"]
    ORCH --> PROF{"Profile exists?"}
    PROF -->|"no, or 'reconfigure'"| SETUP["wowcube-setup: detect the machine (read-only),<br/>at most three questions (the one-line install<br/>before it asks none), write the profiles"]
    SETUP --> PROF
    PROF -->|"entry: tools"| TOOLS(["wowcube-tools: build, repack, verify, upload, video"])
    PROF -->|"entry: art"| ART(["cube_art-director standalone: style lock with the user,<br/>pictures, strict QA, PNGs + sprite sheet and atlas"])
    PROF -->|"entry: new / gdd / mod"| CHK["Entry checks: build or mod, run mode and tier from the profile,<br/>the automatic checks and the build kit, art source"]
    CHK -->|"SDK or toolchain missing"| ENV["Tell the user the exact update commands;<br/>design, prompts and art go on; wait before the infra gate"]
    CHK --> DET{"Stage detection:<br/>first step not done"}

    DET -->|"no GDD"| S1["Stage 1: cube_game-designer<br/>new GDD, or import of the user's document<br/>(feasibility annex + open questions);<br/>checked against GAME_FEEL (universal + genre)"]
    S1 --> CP1{{"STOP, step by step: review the GDD"}}
    CP1 --> S2
    DET -->|"no prompts or manifest"| S2["Stage 2: technical_prompter<br/>prompts with test hooks + manifest with a drawing prompt per sprite"]
    S2 --> CP2{{"STOP, step by step: review prompts and manifest"}}
    CP2 --> INFRA
    DET -->|"no app folder or infra not ok"| INFRA["Infra gate: wowcube-boilerplate<br/>app layout, the game built for the automatic checks, a hidden smoke run:<br/>the agent checks Demo 0's expected screens<br/>(a failed step is retried alone, never a new scaffold)"]

    INFRA --> GATE3["Manifest gate: build_pipeline.py validate<br/>(no generation, no network), then sizes, panoramas, sounds"]
    DET -->|"no style lock"| GATE3
    GATE3 -->|"fails"| S2
    GATE3 --> SL["cube_art-director: style bible, style frames,<br/>in-game mock of one face; the sound list (synthesized by default)"]
    SL --> LOCK{{"STOP, always: the user approves the style and the sound list"}}
    LOCK -->|"change"| SL
    LOCK -->|"approved"| GEN["Drawing via art.py: in code by default,<br/>Codex or another provider only when the user chose it;<br/>family leaders first, then the batch"]
    DET -->|"pack-status not current"| GEN
    GEN --> QA{"Every QA rule passes, is waived after a look (false FAIL),<br/>or is accepted under a spent image budget?"}
    QA -->|"no: cause-level fix in fixes.json, redraw failures"| GEN
    QA -->|"yes"| FRESH["Fresh-agent consistency review + review.html"]
    FRESH --> CP3{{"STOP, step by step: the user reviews the batch"}}
    CP3 --> SND["Sound: synthesized with sound_kit by default<br/>(approved CC0 downloads only when the user chose recordings),<br/>loop, inspect by numbers, CREDITS.md"]
    SND --> PACK["Launcher icon + fonts, then pack (refuses an incomplete set):<br/>index.bin, art/packed, sound/assets, ids header, .pack_inputs.json"]

    PACK --> CODER["Stage 4, prompt N: coder subagent"]
    DET -->|"prompts left"| CODER
    CODER --> CHECKS["In parallel: code review (every tier: Requirements + Template,<br/>two separate reviewers);<br/>visual gate (every tier): the hidden, muted automatic checks, 24-screen frames, the agent looks"]
    CHECKS --> PLAY["Playtest Agent over the control socket<br/>(lite and full: every prompt; standard: mechanic prompts)"]
    PLAY --> PASS{"reviewers 90, no critical issue anywhere,<br/>no major visual finding, playtest 90,<br/>no open major from any agent?"}
    PASS -->|"no, rounds left (2 / 3 / 5 by tier)"| FIX["Fixer: all issues + the frames that show them"]
    FIX --> CHECKS
    PASS -->|"no, rounds used"| DEG{"Budget and scope_cuts allow a rescope?"}
    DEG -->|"yes (on my own): rescoped prompt, every gate again"| FIX
    DEG -->|"no, or step by step"| ASK(["Save progress; step by step: ask simplify / retry / stop;<br/>on my own: stop with the report"])
    PASS -->|"yes"| SAVE["Save context + frames"]
    SAVE --> CP4{{"STOP, step by step: per-prompt checkpoint with the frames"}}
    CP4 -->|"more prompts"| CODER
    CP4 -->|"all done"| S5

    DET -->|"no verified .oct"| S5["Stage 5: hooks off, version bump,<br/>build_device (public game API) into dist,<br/>mandatory verification"]
    S5 --> UPQ{{"STOP, always: make an install link and a QR code? (asked once)"}}
    UPQ -->|"yes"| UPL["scripts/store_upload.py: the game file to WowCube, verified;<br/>install QR code dist/app_<game>_qr.png + link; on-device checklist"]
    UPQ -->|"no"| REP
    UPL --> REP(["Final report (context/<game>_report.md): install QR, what was checked, cuts,<br/>temporary parts, credits, controls"])
    REP -.->|"balance pass or mod"| ORCH
```

## Legend

- Rounded nodes: start and end.
- Rectangles: work done by a sub-skill, a subagent or the orchestrator's own tools.
- Diamonds: decisions and gates.
- Hexagons `{{ … }}`: stops. `STOP, always` happens in every run mode unless the user explicitly
  waived it (the style lock and the install-link question); `STOP, step by step` only in
  *Step by step* (*On my own* prints a progress line and continues).

## Stage summary

| Stage | Owner | Produces |
|---|---|---|
| Setup (first use) | `wowcube-setup` | `~/.wowcube/config.json`, `<ws>/wowcube.project.json` |
| 1. Design | `cube_game-designer` | `plans/<game>_gdd.md` |
| 2. Prompts | `technical_prompter` | `plans/<game>_prompts.md`, `plans/<game>_assets.json` |
| Infra gate | `wowcube-boilerplate` | `app_<game>/`, the game built for the automatic checks, a hidden smoke run (`tools/sim/`) |
| 3. Assets | `cube_asset-builder` + `cube_art-director` + consistency reviewer | style lock, `assets_<game>/art/`, sounds, icon, packed `app_<game>/index.bin`, `art/packed/`, `sound/assets/`, `src/app_<game>_ids.h` |
| 4. Implement | coder, `cube_verifier` agents, fixer; the orchestrator's visual gate | `app_<game>/src/app_<game>.h`, frames per prompt |
| 5. Deliver | `wowcube-boilerplate`; `scripts/store_upload.py` | `dist/app_<game>.oct`, the install QR code and link, `context/<game>_report.md`, video, balance passes |

## Key points

- **Single entry point**: the user talks to `cube_orchestrator`; it routes and resumes
  from files (`plans/`, `assets_<game>/`, `app_<game>/`, `context/`).
- **Two planned stops on my own**: the style lock (style frame + in-game mock at cube resolution)
  is approved before mass generation (with the sound download list when the user chose recordings),
  and the install link is made only after the user's yes at the end.
- **Defaults made in code**: the art is drawn in code (a deliberate, final style) and the sounds are
  synthesized; Codex, an image service or downloaded sounds only when the user picked them; QA until
  every rule passes or is waived after a look (a false FAIL, `art.py waive`); once the image budget is
  spent a real FAIL left is accepted under budget on the record (`--under-budget`), never silently; a paid service only on opt-in, asked once per run
  with the quoted cost.
- **The agent looks at every build**: after every coder and fixer run the hidden,
  muted automatic checks dump all 24 screens and the orchestrator inspects them; the Playtest
  Agent drives taps, twists and tilt through the control socket. Code-only
  verification once missed a rendering bug on all 24 screens.
- **No prompt completes with a failing gate**: any critical issue fails its check
  whatever the score; fix rounds and rescopes are bounded by the tier and the budget; when they
  are spent the run saves and asks (*Step by step*) or stops with a report (*On my own*)
  (`skills/cube_orchestrator/references/RUN_MODES.md`).
- **Profiles**: `wowcube-setup` writes `~/.wowcube/config.json` (the machine) and
  `<ws>/wowcube.project.json` (the project's intent); every skill and brief gets the resolved
  snapshot.
- **Device package without the checker**: `build_device` builds the ARM module against the public
  game API (`api/apps` + `api/include`) and the container into `dist/`, verified every
  time (unverifiable = failed); only `dist/` is delivered.
- **Install from the phone**: after one yes, the verified `.oct` goes to WowCube's servers; the user
  scans the QR code with their phone and the WowCube app installs it on their cube.
- **Undo**: a snapshot before every change (`<ws>/.history/`); "undo the last change" restores it.
- **Safety**: no windows over the user's screen, no audio, no global input, PID-only
  process kills (`skills/cube_orchestrator/references/AGENT_SAFETY.md`).
