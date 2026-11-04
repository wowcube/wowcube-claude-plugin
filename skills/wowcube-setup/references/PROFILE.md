# Profiles: files, fields, resolution (wowcube-setup reference)

Three files, one resolution order. Every skill reads the **resolved snapshot**, and every subagent
brief carries it (`profile` in the brief JSON, `cube_orchestrator/references/AGENT_BRIEFS.md`).

| File | Holds | Shared? | Secrets? |
|---|---|---|---|
| `~/.wowcube/config.json` | the machine: OS, host, tools found, paths, provider choice, credential references | no (per machine) | never: references only |
| `<ws>/wowcube.project.json` | the project's intent: entry mode, guidance, verification tier, budgets, provider id, data policy, the source document | yes (commit it with the project) | never |
| `<ws>/context/<game>_context.json` | run state of one game (stage, scores, cuts, spend so far) | with the project | never |

`~/.wowcube/image_api.json` is older and different: the scripts' provider file
(`scripts/image_providers.py`), which may hold a key. The profiles point at it
(`"credential_ref": "file:~/.wowcube/image_api.json"`) and never copy from it.

## `~/.wowcube/config.json` (schema_version 1)

```json
{
  "schema_version": 1,
  "updated": "2026-11-02",
  "os": "windows|linux|macos",
  "host": {"name": "claude-code|other", "subagents": true, "skills": true},
  "paths": {"workspaces": ["C:/games/ws"]},
  "tools": {"sim": "ok|missing|unknown", "build_kit": "ok|missing|unknown", "arm": true,
            "ffmpeg": true, "node": true, "playwright": false},
  "install_consent": {"answer": "yes|not_now", "date": "2026-11-03"},
  "art": {"codex": "chatgpt|api_key_login|not_logged_in|absent",
          "keys_found": ["OPENAI_API_KEY"], "local_sd": "http://127.0.0.1:7860|null"},
  "image_provider": {"id": "codex|openai|gemini|xai|openrouter|image_api|local_sd|none",
                     "credential_ref": "env:OPENAI_API_KEY|file:~/.wowcube/image_api.json|null"}
}
```

`install_consent` has one shape, `{"answer": "yes"|"not_now", "date": "YYYY-MM-DD"}`, written by the
one-command installers (`install.sh`, `install.ps1`: running them is the yes), the environment-only install
and setup's Step 2b, always merged into the file (other keys kept). Readers use
`profile_provider.install_consent`, which also accepts an older plain string (`"yes"`, `"not_now"`). `yes`
means no install question again: setup only installs what is still missing, under that consent.

`art.codex` and `art.keys_found` are detection facts, never a choice: `image_provider` is written only
from what the user picked (never from a detected login or key; `none` until they pick one). An older file's
`cube` (a paired cube) is ignored: nothing goes to a cube from this computer.

## `<ws>/wowcube.project.json` (schema_version 1)

```json
{
  "schema_version": 1,
  "entry": "new|gdd|mod|tools|art",
  "source": {"document": "refs/design.pdf", "approved": true,
             "app_dir": "app_<game>", "mod": "update|fork", "rights": "yes|no|unsure"},
  "role": "creator|developer|staff",
  "guidance": "guided|autonomous",
  "experience": "new|cpp",
  "resources": {"have": ["claude", "codex"], "note": "I have Claude and ChatGPT"},
  "verification": "lite|standard|full",
  "budget": {"hours": null, "images": null,
             "fix_rounds": null, "rescopes": null, "scope_cuts": "ask|auto"},
  "art": {"source": "codex|own|procedural|provider|placeholder|original", "provider": "openai|null",
          "new": "procedural|codex", "animation": "frames|video", "animation_provider": "higgsfield|null"},
  "sound": {"source": "synth|cc0"},
  "data_policy": {"may_leave_machine": ["prompts", "reference_images"]}
}
```

- `entry` routes the orchestrator (its SKILL.md, "Entry checks"). `art` = *Art only*: sprites, a sprite
  sheet, icons or backgrounds in one style and no game code; it goes to `cube_art-director` standalone and
  never needs the build components (no install question, no build kit, no ARM toolchain). `source.document` is the one design
  file the pipeline reads, relative to `<ws>`: a file the studio already put under `refs/` stays where it
  is (e.g. `refs/design.pdf`); only a document from outside `refs/` is copied, to `refs/design/<name>`.
  `source.approved: true` marks an approved studio GDD (setup asks "approved or draft?" whenever
  `entry` is `gdd`): every scope or mechanic change waits for the user's yes.
- `source.rights` (entry `mod`): the user's plain answer to "Do you have the right to change this game and
  publish your version?". `yes` → mod it; `no` → it is not modded (the owner's permission is needed);
  `unsure` → the mod is made for private testing only (the automatic checks and the user's own cube),
  never published or shared, and the report says so. Asked whenever the game was not made by this user in this workspace.
- `art.source: original` (mods): keep the game's own art, extracted from its pack
  (`scripts/extract_art.py`; the context's `style_lock.status` is `user_art`); `art.new` says how changed or
  new pictures are made: `procedural` (default, in code on this machine) or `codex` (only when the user has
  Codex and chose it).
- `guidance: guided` = the stepwise run mode; `autonomous` = the autonomous run mode within `budget`
  (*Just show me results* is `autonomous` with `experience: new` and `scope_cuts: ask`).
- `resources` is the user's own answer to "What AI tools and subscriptions do you have?": `have` holds the
  ids of what they picked or wrote (`claude`, `codex`, `gemini`, `image_key`, `local_model`, `own_art`,
  `video` for an image-to-video service such as Higgsfield;
  `scripts/profile_provider.py` `RESOURCE_IDS`), `note` their words. It is the source of truth for the art
  routes (`profile_provider.art_routes`): a tool that detection found but the user did not name is never
  used; it is at most mentioned once. Drawn in code (`procedural`) is always possible; the user's own art
  (`own`) when they named it (`own_art`: an artist, their own pictures), and a mod's kept art (`original`)
  on entry `mod`. Nothing in a profile names a subscription plan.
- `art.animation`: how animation frame sets are made. `frames` (the default, also when absent): every
  frame is drawn by the picture route. `video`: looping idles, walk/run cycles and short actions are
  animated by the image-to-video service in `art.animation_provider` (e.g. `higgsfield`) from one approved
  picture and cut into frames (`cube_art-director/references/ANIMATION_VIDEO.md`). Written `video` only
  when the user named such a service (`resources.have` holds `video`; `profile_provider.animation_for`).
  Resolution: the current request ("animate it with Higgsfield", "draw every frame") wins, then the project
  file, then `frames`. Using it at run time also needs the connector's tools in the session (missing: the
  frames are drawn, said once) and the user's yes to the quoted credits once per run; a connector found in
  the session is never the answer, and the consent is never stored. It adds `animation_frames` to
  `data_policy.may_leave_machine` (the base picture and the motion description go to the service);
  `may_leave_machine: []` rules it out. The service animates; it does not draw the pictures: its own image
  models draw a base picture only when the user also named it as their picture tool, and its GPT image
  model never when the user has ChatGPT (`cube_art-director/references/ANIMATION_VIDEO.md`, "The base
  picture").
- `verification` follows the guidance answer; there is no question about it
  (`profile_provider.verification_for_guidance`): `autonomous` (*On my own*, *Just show me results*, the
  defaults) = `lite`, `guided` (both *Step by step* answers) = `full`. `lite` is the quick structure (one or
  two prompts, 2 fix rounds) with the full set of checks on every prompt: two separate code reviewers, the
  24-screen review and the playtest. `standard` is never offered; it is written only when the user asks
  for it in their own words (an explicit "standard", or "check it more but not every detail"); "check
  everything thoroughly" writes `full`, "quick" or "fast" `lite`; any other word ("normal") changes nothing
  (`profile_provider.verification_for`). No answer makes the checks lighter than `lite`. The
  tier sets the reviewers, playtests, fix rounds, rescopes, the image budget and the art review rounds
  (RUN_MODES.md, "Verification tiers"). A project file without `verification` resolves it from
  `guidance` the same way.
- `budget.images`, `fix_rounds`, `rescopes`: `null` (or absent) = the verification tier's value
  (`lite` 30 / 2 / 2, `standard` 80 / 3 / 3, `full` 200 / 5 / 5; RUN_MODES.md). Set a number only to
  override the tier. `budget.images` is enforced by the tools: every image request is counted in
  `context/<game>_images.json` (`cube_art-director/scripts/art_budget.py`) and a run past it is refused;
  `build_pipeline.py validate` holds the images the manifest still needs drawn to 60% of it.
- `budget.scope_cuts`: `ask` = a rescope (cutting or simplifying scope) waits for the user's yes; `auto` =
  the autonomous run rescopes on its own within `rescopes` and lists every cut in the report. How it
  combines with guidance and `source.approved`: "Precedence of `scope_cuts`" below.
- `experience: new` (the default) = plain-language messages (`cube_orchestrator/references/RUN_MODES.md`,
  "Plain language"). Always written (setup, Step 2: *Step by step* and the defaults → `new`, *Step by
  step, I know C++* → `cpp`, *On my own* → `cpp` only when the user showed it, else `new`).
- `art.source: procedural` is a deliberate, final style drawn in code; `placeholder` is a temporary
  stand-in. Never confuse the two in a report.
- `sound.source: synth` (the default) = synthesized by `sound_kit.py` recipes, final; `cc0` = CC0
  recordings from an approved list, only when the user asked for real recordings (synthesis only fills
  gaps, temporary).
- `data_policy.may_leave_machine` lists what may leave the machine (`profile_provider.data_policy_for`):
  Codex or a cloud provider `["prompts", "reference_images"]`, plus `animation_frames` with
  `art.animation: video`; a local model, the user's own art, drawn-in-code art and a mod's kept art `[]`.
  The design text is never sent anywhere, so it is never listed. `[]` rules out Codex and every cloud
  provider; the pipeline then uses the user's own art or the procedural style.
- Paid consent is **never** stored: it is asked per run (RUN_MODES.md).
- The plugin folder `<skills>` is **never** stored either: a plugin update or a move would leave a stale
  path. Every entry skill resolves it from its own location (two levels above its SKILL.md) on every entry.
  An older `paths.skills` in `config.json` is ignored and may be removed.

## Role defaults (defaults only; they grant nothing)

| Role | guidance | experience | scope_cuts |
|---|---|---|---|
| creator | autonomous | new | auto |
| developer | autonomous | cpp | ask |
| staff | autonomous | cpp | auto |

The role never sets `verification`: it follows `guidance` (above). Tier limits (fix rounds, rescopes,
playtests, image budget) come from the tier: `cube_orchestrator/references/RUN_MODES.md`, "Verification
tiers".

## Precedence of `scope_cuts` (one rule)

From strongest to weakest; the first that applies decides:

1. `source.approved: true` (an approved studio GDD): every change of scope or mechanic waits for the
   user's yes, in every mode, whatever `scope_cuts` says. Simplifying one sprite inside the approved
   scope (same name and size) is not a scope change.
2. The current request ("cut what you need", "ask before cutting").
3. The project file's `budget.scope_cuts`, which the setup survey writes: *On my own* (and the defaults)
   writes `auto` (the checking tier it sets changes the checks and the image budget, never the
   stops); *Just show me results* and "ask me before cutting" write `ask`.
4. The role default (table above): only when the project file has no `scope_cuts`.

A guided (stepwise) run asks before any cut whatever this says: it stops at every step anyway.

## Resolution

For each field, the first source that sets it wins:

1. the current request ("stepwise", "use Codex", "check everything thoroughly", "spend at most 20 images");
2. `context/<game>_context.json` for run state only (stage, spend so far); never for a profile field;
3. `<ws>/wowcube.project.json`;
4. `~/.wowcube/config.json` (machine facts and the provider choice);
5. role defaults (table above);
6. built-in defaults: `guidance: autonomous`, `experience: new`, `verification` from `guidance`
   (`lite` when autonomous), `art.source: procedural` (drawn in code), `sound.source: synth`, `resources.have: ["claude"]`: the AI the user came
   with and everything made in code. Codex, an image service or downloaded sounds only when the user
   picked them; a login or key found on the machine is never a default. "I don't know", "you choose",
   "skip setup", "just do it" and an unanswered question resolve to these.

Facts beat wishes: a project that asks for Codex on a machine without a ChatGPT login resolves to the
fallback and says so once. The run mode follows one rule (`cube_orchestrator/references/RUN_MODES.md`):
a word in the current request for this run, else the resolved `guidance`; a reconfigure that changes
`guidance` applies from the next entry, also for a game already running.

## Resolved snapshot

The orchestrator writes it into the context as `profile` at every entry and passes it to every skill
and brief (`cube_orchestrator/references/AGENT_BRIEFS.md`, "Context file"). One shape: the project
file's fields, with every gap resolved, the tier's limits filled into `budget`, and no machine data:

```json
{"resolved_at": "2026-11-02T10:00", "entry": "new", "role": "developer", "guidance": "autonomous",
 "experience": "cpp", "verification": "lite", "resources": {"have": ["claude", "codex"]},
 "budget": {"hours": null, "images": 30, "fix_rounds": 2, "rescopes": 2, "scope_cuts": "ask"},
 "art": {"source": "codex", "provider": null, "animation": "frames"}, "sound": {"source": "cc0"},
 "data_policy": {"may_leave_machine": ["prompts", "reference_images"]}}
```

## Image provider

Which provider draws (`scripts/profile_provider.py`, used by `image_providers.resolve_provider()`); the first
that sets it wins:

1. `WOWCUBE_IMAGE_PROVIDER=<id>` in the environment (this run only, e.g. "use Codex now");
2. the project: `art.source: codex` → codex; `art.source: provider` → `art.provider`, else the machine id;
   `procedural` / `placeholder` → none;
3. the machine: `image_provider.id`;
4. nothing → no choice: the art is drawn in code. A Codex login or a key found in the environment
   (`OPENROUTER_API_KEY`, ...) is never used on its own; the run says how to choose (say which tool, or run
   setup). The only exception is the pipeline's own key settings, which a user creates on purpose and which
   therefore count as a choice: the `IMAGE_API` variable, then `~/.wowcube/image_api.json`
   (`cube_asset-builder/references/ART.md`, "Provider chain").

The credential: the machine `credential_ref` when it belongs to the chosen id (`env:NAME` reads that variable,
`file:PATH` a provider file), else the provider's standard variable (`OPENAI_API_KEY`; `GEMINI_API_KEY` or
`GOOGLE_API_KEY`; `XAI_API_KEY`; `OPENROUTER_API_KEY`). `local_sd` uses `art.local_sd` (default
`http://127.0.0.1:7860`). A missing variable stops with its name. Consent is separate and unchanged: a cloud
provider draws only with `WOWCUBE_ALLOW_PAID_IMAGES=1` / `--allow-paid` from this run's yes; a configured key is never
consent; a server on this machine is free. `data_policy.may_leave_machine: []` allows only a server on this machine
(Codex included in the refusal).

## Versions

`schema_version` is 1 in both files. A reader that finds a higher number uses the fields it knows and
leaves the rest untouched; a lower number is upgraded in place by `wowcube-setup` (keep unknown keys).

## Setup answers (wowcube-setup Step 2)

| Question | Answer | Writes |
|---|---|---|
| Starting point | *A new game* / *My design document* / *An existing game* / *Art only* | `entry`: `new` / `gdd` / `mod` or `tools` (follow-up "What should I do with it?") / `art` |
| Guidance | *On my own* (default) / *Step by step* / *Step by step, I know C++* / *Just show me results* | `guidance` + `experience` + `budget.scope_cuts` (setup SKILL.md, Step 2) + `verification`: `lite` for *On my own* / *Just show me results*, `full` for both *Step by step* answers |
| AI tools and subscriptions | multi-select + free text | `resources.have` / `resources.note`; then `art.source` (follow-up only when more than one route), `art.provider`, `art.animation` / `art.animation_provider` (an image-to-video service named in the free text), `data_policy` (`profile_provider.data_policy_for`) |
| Free text in any answer (no question of its own) | "check everything thoroughly" / "standard" or "check it more but not every detail" / "quick" or "fast" / hours / a maximum of pictures / "cut without asking" | `verification` `full` / `standard` / `lite` (any other word: nothing); `budget.hours`, `budget.images`, `budget.scope_cuts` |
| Install the build components (not on *Art only*; not asked when `install_consent` is already `yes`) | *Install them* / *Not now* | `~/.wowcube/config.json` `install_consent` (`{"answer", "date"}`); *Not now* stops every build until the user agrees |

An older project file may still carry `budget.usage` (`lean|normal|unlimited`): it is ignored.
