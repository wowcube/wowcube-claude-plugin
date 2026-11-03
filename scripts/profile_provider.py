"""The image provider the resolved profile asks for (wowcube-setup profiles).

Reads `~/.wowcube/config.json` (machine: `image_provider.id`, its
`credential_ref`, `art.local_sd`) and `<ws>/wowcube.project.json` (project:
`art.source`, `art.provider`, `data_policy`) and returns a ProfileChoice.
`image_providers.resolve_provider()` turns that into a ProviderConfig.
Profiles hold credential *references* only (`env:NAME`, `file:PATH`); this
module reads the named variable or file at run time and never writes a secret.

Which provider (first hit wins; skills/wowcube-setup/references/PROFILE.md,
"Image provider"):
  1. `WOWCUBE_IMAGE_PROVIDER` env var (this run only, e.g. "use Codex now");
  2. project `art.source`: `codex` -> codex; `provider` -> project
     `art.provider`, else the machine `image_provider.id`;
     `procedural` / `placeholder` -> none (nothing is drawn by a provider);
     `original` (a mod keeping the game's own art) -> codex when `art.new` is
     `codex`, else none (new pictures are drawn in code);
  3. machine `image_provider.id`;
  4. nothing -> None: no choice. Then only IMAGE_API or ~/.wowcube/image_api.json
     (pipeline settings a user creates on purpose) count; otherwise the art is
     drawn in code. A Codex login or OPENROUTER_API_KEY alone is never used.
The paid opt-in is separate and unchanged: a configured key is never consent.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

MACHINE_CONFIG = Path.home() / '.wowcube' / 'config.json'
PROJECT_FILE = 'wowcube.project.json'
PROVIDER_ENV = 'WOWCUBE_IMAGE_PROVIDER'

KNOWN_IDS = ('codex', 'openai', 'gemini', 'xai', 'openrouter', 'image_api', 'local_sd', 'none')
_ALIASES = {'sd_a1111': 'local_sd', 'sd': 'local_sd', 'google': 'gemini', '': None, 'null': None}
# standard variable names per provider, used when the profile has no credential_ref for it
DEFAULT_KEY_ENVS = {
    'openai': ('OPENAI_API_KEY',),
    'gemini': ('GEMINI_API_KEY', 'GOOGLE_API_KEY'),
    'xai': ('XAI_API_KEY',),
    'openrouter': ('OPENROUTER_API_KEY',),
}
DEFAULT_LOCAL_SD = 'http://127.0.0.1:7860'


@dataclass
class ProfileChoice:
    provider: str | None = None          # a KNOWN_IDS entry; None = no choice (drawn in code unless IMAGE_API / image_api.json)
    credential_ref: str | None = None    # 'env:NAME' | 'file:PATH' | None (only when it belongs to `provider`)
    local_sd: str | None = None          # machine `art.local_sd` URL
    local_only: bool = False             # project data_policy.may_leave_machine == []
    source: str = 'no choice'


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def find_project_file(workspace=None, manifest=None) -> Path | None:
    """<workspace>/wowcube.project.json; else the nearest one at most three
    folders above `manifest` (<ws>/plans/<game>_manifest.json); else the
    current folder's. None when there is none."""
    candidates = []
    if workspace is not None:
        candidates.append(Path(workspace) / PROJECT_FILE)
    elif manifest is not None:
        candidates += [p / PROJECT_FILE for p in list(Path(manifest).resolve().parents)[:3]]
    else:
        candidates.append(Path.cwd() / PROJECT_FILE)
    return next((c for c in candidates if c.is_file()), None)


def _norm(pid) -> str | None:
    if pid is None:
        return None
    pid = str(pid).strip().lower()
    return _ALIASES.get(pid, pid)


def read_choice(workspace=None, manifest=None, *, machine_config: Path | None = None) -> ProfileChoice:
    """The provider the profiles ask for (precedence: module docstring)."""
    machine = _read_json(Path(machine_config) if machine_config else MACHINE_CONFIG)
    project_path = find_project_file(workspace, manifest)
    project = _read_json(project_path) if project_path else {}

    m_prov = machine.get('image_provider') or {}
    m_id = _norm(m_prov.get('id'))
    art = project.get('art') or {}
    policy = (project.get('data_policy') or {}).get('may_leave_machine')
    local_sd = (machine.get('art') or {}).get('local_sd')
    choice = ProfileChoice(local_sd=local_sd if isinstance(local_sd, str) and local_sd else None,
                           local_only=isinstance(policy, list) and not policy)

    env_id = _norm(os.environ.get(PROVIDER_ENV))
    src_art = _norm(art.get('source'))
    if env_id:
        choice.provider, choice.source = env_id, f'the {PROVIDER_ENV} environment variable'
    elif src_art == 'codex':
        choice.provider, choice.source = 'codex', f'{project_path} (art.source)'
    elif src_art == 'provider' and _norm(art.get('provider')):
        choice.provider, choice.source = _norm(art.get('provider')), f'{project_path} (art.provider)'
    elif src_art == 'original':
        # a mod that keeps the game's own art: new or changed pictures come from art.new (default: in code)
        if _norm(art.get('new')) == 'codex':
            choice.provider, choice.source = 'codex', f'{project_path} (art.source: original, art.new: codex)'
        else:
            choice.provider, choice.source = 'none', f'{project_path} (art.source: original)'
    elif src_art in ('procedural', 'placeholder'):
        choice.provider, choice.source = 'none', f'{project_path} (art.source: {src_art})'
    elif m_id:
        choice.provider, choice.source = m_id, f'{MACHINE_CONFIG if not machine_config else machine_config} (image_provider.id)'

    if choice.provider and choice.provider not in KNOWN_IDS:
        raise ValueError(f'unknown image provider {choice.provider!r} in {choice.source}; '
                         f'known: {", ".join(KNOWN_IDS)}')
    if choice.provider and choice.provider == m_id:
        ref = m_prov.get('credential_ref')
        choice.credential_ref = ref if isinstance(ref, str) and ref else None
    return choice


# --------------------------------------------------------------------------- setup answers -> profile fields
# wowcube-setup asks "What AI tools and subscriptions do you have?" (the user's own words are the source of
# truth, detection only pre-fills or adds a note) and "How thorough should checking be?". These map the answers
# onto the project file (skills/wowcube-setup/references/PROFILE.md, "Setup answers").
RESOURCE_IDS = ('claude', 'codex', 'gemini', 'image_key', 'local_model', 'own_art')
THOROUGHNESS = {'quick': 'lite', 'normal': 'standard', 'thorough': 'full'}
_CLOUD_LEAVES = ['prompts', 'reference_images']


def verification_for(thoroughness: str) -> str:
    """'quick' / 'normal' / 'thorough' (the setup answer) -> the verification tier lite / standard / full."""
    key = str(thoroughness or '').strip().lower()
    if key in THOROUGHNESS.values():
        return key
    if key not in THOROUGHNESS:
        raise ValueError(f'unknown thoroughness {thoroughness!r}; known: {", ".join(THOROUGHNESS)}')
    return THOROUGHNESS[key]


def art_routes(have, entry: str = 'new') -> list[str]:
    """The ways the art can be made, given what the user SAID they have (`resources.have`), best first:
    `original` (a mod keeps the game's own art), `codex`, `provider` (Gemini, an image API key or a local
    model), `own` (an artist or their own art); `procedural` (drawn in code) is always possible. A tool that
    detection found but the user did not name is never a route."""
    have = {str(h).strip().lower() for h in (have or [])}
    unknown = have - set(RESOURCE_IDS)
    if unknown:
        raise ValueError(f'unknown resource(s) {sorted(unknown)}; known: {", ".join(RESOURCE_IDS)}')
    routes = ['original'] if entry == 'mod' else []
    if 'codex' in have:
        routes.append('codex')
    if have & {'gemini', 'image_key', 'local_model'}:
        routes.append('provider')
    if 'own_art' in have:
        routes.append('own')
    routes.append('procedural')
    return routes


def provider_hint(have) -> str | None:
    """The provider id a `provider` route starts from when the answer names only one kind; None = ask which
    (an image API key could be OpenAI, xAI or OpenRouter)."""
    have = {str(h).strip().lower() for h in (have or [])}
    kinds = [k for k in ('gemini', 'local_model', 'image_key') if k in have]
    if kinds == ['gemini']:
        return 'gemini'
    if kinds == ['local_model']:
        return 'local_sd'
    return None


def data_policy_for(art_source: str, provider: str | None = None) -> list[str]:
    """What may leave the machine for the chosen art route: Codex or a cloud provider get the prompts and the
    reference images; a local model, the artist's own art, drawn-in-code art and a mod's kept art send nothing."""
    src = str(art_source or '').lower()
    if src == 'codex':
        return list(_CLOUD_LEAVES)
    if src == 'provider' and _norm(provider) not in ('local_sd', 'none'):   # not yet chosen: assume a cloud one
        return list(_CLOUD_LEAVES)
    return []


def credential(choice: ProfileChoice) -> tuple[str | None, str]:
    """(value, where from) for an `env:` reference or the provider's standard
    variables; `file:` references are parsed by the caller. The value is never
    printed by this module."""
    ref = choice.credential_ref
    if ref and ref.startswith('env:'):
        name = ref[4:].strip()
        return (os.environ.get(name) or None), name
    names = DEFAULT_KEY_ENVS.get(choice.provider, ())
    for name in names:
        if os.environ.get(name):
            return os.environ[name], name
    return None, ' or '.join(names) or '(none)'


def credential_file(choice: ProfileChoice) -> Path | None:
    ref = choice.credential_ref
    if ref and ref.startswith('file:'):
        return Path(os.path.expanduser(ref[5:].strip()))
    return None
