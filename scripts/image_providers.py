"""Image-generation providers for cube_asset-builder.

Nothing external is used unless the user chose it. By default the art is
drawn in code (the procedural style, final quality): a Codex login or an API
key that merely exists on this machine is never picked up on its own.

A choice comes from the wowcube-setup profiles (`profile_provider.read_choice()`;
precedence documented once in skills/wowcube-setup/references/PROFILE.md,
"Image provider": `WOWCUBE_IMAGE_PROVIDER`, project `art.source` /
`art.provider`, machine `image_provider.id`). That provider is used with the
credential its reference names (`env:NAME`, `file:PATH`, or the provider's
standard variable). `codex` -> the Codex CLI, then the key chain steps 1-3
below; `image_api` -> the key chain steps 1-3; `none` -> None. A project whose
`data_policy.may_leave_machine` is `[]` allows only a server on this machine
(DataPolicyBlocked otherwise, Codex included).

No choice anywhere -> `resolve_provider()` looks only at the two settings
that exist for this pipeline alone and that a user creates on purpose, so
they count as a choice (`explicit_key_config()`):
  1. `IMAGE_API` env var - JSON object or a bare key/URL
  2. config file `~/.wowcube/image_api.json` - same JSON shape (written by
     `save_provider()` when the user pastes a key)
and otherwise returns None (drawn in code; `NO_CHOICE_HINT` says how to
choose). A Codex login and a general-purpose `OPENROUTER_API_KEY` alone are
never used without a choice.

Key chain (`paid_chain()`, first hit wins), used for an explicit `codex`
(when Codex is not logged in) or `image_api` choice:
  0. `codex` (only when chosen): a Codex CLI logged in with the user's
     ChatGPT account. Found as the newest
     %LOCALAPPDATA%\\OpenAI\\Codex\\bin\\*\\codex.exe (Windows installs are often
     not on PATH) or `codex` on PATH; `codex login status` must mention
     ChatGPT. Skipped when WOWCUBE_NO_CODEX=1 (forces the key chain below).
  1. `IMAGE_API` env var
  2. `~/.wowcube/image_api.json`
  3. `OPENROUTER_API_KEY` env var (backward compat, treated as OpenRouter key)
  4. nothing -> None (the procedural style, agent-drawn in code at final quality)

Steps 1-3 are paid (or at least external) APIs and are OPT-IN: a key that
merely sits in the environment (set for something else) is never used
silently. Without WOWCUBE_ALLOW_PAID_IMAGES=1 (or `allow_paid=True`; the
generate CLIs have `--allow-paid`), finding one raises PaidProviderNotAllowed
with the reason, instead of falling through to it. Set the opt-in only after
the user agreed to pay per image. Exception: a server on this machine
(`http://localhost`, `127.x.x.x`, `[::1]`) costs nothing and leaves no
machine, so it needs no opt-in (`is_local_url()`): a Stable Diffusion
(A1111) URL, or an `openai` config whose `base_url` is a local
OpenAI-compatible server. Any other URL does.

Codex never runs through this module's HTTP code: drawing is delegated to
cube_art-director's `art.py` (one code path for prompts, Codex quirks, chroma
keying, set fitting and colour lock). `codex_generate()` draws a whole
WowCube manifest (`art.py gen` then `art.py process`); `codex_draw()` draws
one image through a throw-away art.json (genimg one-offs).

Config JSON shape (every field optional):
    {"provider": "...", "key": "...", "base_url": "...", "model": "..."}
Missing `provider` is detected from `key`/`base_url` patterns.

Detection patterns — `detect_provider()`:
    sk-or-...     -> openrouter      sk-...    -> openai
    xai-...       -> xai             AIza...   -> gemini
    http(s)://... -> sd_a1111        else      -> UnknownProviderError
A bare `sk-` key is taken as OpenAI. DeepSeek keys look the same, but
DeepSeek has no image API: such a key fails authentication at OpenAI, which
is reported once (401/403 are never retried). A URL is assumed to be an
Automatic1111 server (`/sdapi/v1/...`); ComfyUI and other servers are not
supported and fail with a clear message (404 on `/sdapi`).

`save_provider(value)` persists a pasted key/URL (or config dict) to the
config file so the intake question never repeats. The file holds a secret: it
is created owner-only (0600, its folder 0700) on POSIX; on Windows chmod cannot
express that, so it relies on the per-user ACL of the user profile folder
(best effort, documented in cube_asset-builder/references/ART.md).

The HTTP providers are non-streaming, use `(15, 180)` (connect, read)
timeouts and the same 4-attempt retry-with-backoff loop the original genimg
used (an authentication failure, 401/403, is not retried). `validate()` is the cheapest possible authenticated call per provider
(for codex: `codex login status`); failures raise ProviderValidationError.
"""
from __future__ import annotations

import base64
import glob
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

from dataclasses import dataclass, asdict
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image

import profile_provider

API_KEY_ENV = 'OPENROUTER_API_KEY'
IMAGE_API_ENV = 'IMAGE_API'
CONFIG_PATH = Path.home() / '.wowcube' / 'image_api.json'

CODEX_PROVIDER = 'codex'
# '1' skips Codex detection, so the key chain (IMAGE_API -> config file
# -> OPENROUTER_API_KEY) decides even when a logged-in Codex CLI is installed.
NO_CODEX_ENV = 'WOWCUBE_NO_CODEX'
# The message for "no provider chosen" (resolve_provider() returned None without a `none` choice).
NO_CHOICE_HINT = (
    'no image tool was chosen, so the art is drawn in code (the procedural style, final quality). A Codex login '
    'or an API key found on this machine is never used on its own. To use one, say which tool you want (for '
    'this run: WOWCUBE_IMAGE_PROVIDER=codex|openai|gemini|xai|openrouter|local_sd), or run setup '
    '(wowcube-setup) to save the choice in wowcube.project.json / ~/.wowcube/config.json. A key put in the '
    f'IMAGE_API variable or in {CONFIG_PATH} also counts as a choice.')
# '1' = the user agreed to pay per image: only then may the key chain
# (IMAGE_API -> config file -> OPENROUTER_API_KEY) be used.
ALLOW_PAID_ENV = 'WOWCUBE_ALLOW_PAID_IMAGES'
# Optional override for where cube_art-director's art.py lives.
ART_PY_ENV = 'WOWCUBE_ART_PY'
_ART_PY_REL = Path('skills') / 'cube_art-director' / 'scripts' / 'art.py'
# `codex login status` per CLI path, checked once per process (resolve_provider
# runs more than once per pipeline run).
_codex_login_cache: dict[str, tuple[bool, str]] = {}


class _LazyRequests:
    """Stand-in for the `requests` module, imported on first attribute use.
    Only the HTTP providers need it, so `build_pipeline.py validate` / `pack`
    and Codex drawing work without it installed (tests still patch
    `image_providers.requests.post`). A missing module raises ImageGenError
    with the install hint (the generate CLIs report it as a one-line error)."""

    def __getattr__(self, name):
        try:
            import requests as module
        except ImportError as e:
            raise ImageGenError("python module 'requests' is needed for the HTTP image providers - "
                                "install with: pip install requests") from e
        return getattr(module, name)


requests = _LazyRequests()

# (connect timeout, read timeout) — without this a stalled socket hangs
# forever and the retry loop never triggers.
TIMEOUT = (15, 180)

_SUPPORTED_FORMS = (
    'supported forms: OpenRouter key (sk-or-...), OpenAI key (sk-...), '
    'xAI key (xai-...), Google Gemini key (AIza...), or a local Stable '
    'Diffusion URL (http://... / https://...)'
)


class ImageGenError(RuntimeError):
    """Raised when the API call fails or returns no image."""


class UnknownProviderError(ImageGenError):
    """Raised when a pasted key/URL matches no known provider pattern."""


class ProviderValidationError(ImageGenError):
    """Raised when the cheap `validate()` call fails (bad key, endpoint down)."""


class PaidProviderNotAllowed(ImageGenError):
    """Codex is not available and the only provider found is a paid/external
    API that was not opted in (WOWCUBE_ALLOW_PAID_IMAGES=1 / --allow-paid)."""


class DataPolicyBlocked(ImageGenError):
    """The project's data policy keeps everything on this machine
    (`data_policy.may_leave_machine: []`) and the provider is not local."""


@dataclass
class ProviderConfig:
    provider: str
    key: str | None = None
    base_url: str | None = None
    model: str | None = None
    cli: str | None = None          # codex: path of the Codex CLI binary


@dataclass(frozen=True)
class ProviderSnapshot:
    """What a provider object was built from, frozen (ImageProvider.config)."""
    provider: str
    key: str | None = None
    base_url: str | None = None
    model: str | None = None
    cli: str | None = None
    paid_consent: bool = False


def detect_provider(value: str) -> str:
    """Map a pasted key/URL to a provider name (spec §4 detection table)."""
    v = value.strip()
    if v.startswith('sk-or-'):
        return 'openrouter'
    if v.startswith('sk-'):
        return 'openai'
    if v.startswith('xai-'):
        return 'xai'
    if v.startswith('AIza'):
        return 'gemini'
    if v.startswith('http://') or v.startswith('https://'):
        return 'sd_a1111'
    raise UnknownProviderError(
        f'cannot identify an image provider from {_key_prefix(redact(v))!r}; {_SUPPORTED_FORMS}'
    )


def _key_prefix(key: str | None) -> str:
    """The recognisable start of a key for messages (`sk-or-...`, `sk-...`,
    `xai-...`, `AIza...`), never the secret part."""
    if not key:
        return '(none)'
    for prefix in ('sk-or-', 'sk-', 'xai-', 'AIza'):
        if key.startswith(prefix):
            return f'{prefix}...'
    return f'{key[:2]}...'


_KEY_RE = re.compile(r'\b(sk-or-|sk-|xai-|AIza)[A-Za-z0-9_\-]{4,}')
# userinfo up to the last '@' before the path, also across spaces ("user:two words@host"), never across lines
_USERINFO_RE = re.compile(r'(?i)\b([a-z][a-z0-9+.\-]*://)[^/?#\r\n]*@')
# environment variables whose VALUES are secrets wherever they show up (art_codex strips the same from Codex)
_SECRET_ENV = ('OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENROUTER_API_KEY', 'IMAGE_API', 'GEMINI_API_KEY',
               'GOOGLE_API_KEY', 'XAI_API_KEY', 'ANTHROPIC_API_KEY', 'DEEPSEEK_API_KEY', 'FAL_KEY',
               'REPLICATE_API_TOKEN', 'ELEVENLABS_API_KEY')
# keys of every provider built in this process (ImageProvider registers its config's key)
_KNOWN_SECRETS: set[str] = set()


def _secret_values() -> list[str]:
    vals = set(_KNOWN_SECRETS)
    for k, v in os.environ.items():
        if v and (k.upper() in _SECRET_ENV or k.upper().endswith(('_API_KEY', '_API_TOKEN'))):
            vals.add(v.strip())
    return sorted((v for v in vals if len(v) >= 6), key=len, reverse=True)


def redact(text) -> str:
    """Any diagnostic, safe to print: every configured secret (a provider key, the value of a key variable)
    becomes its recognisable prefix (`sk-...`) wherever it appears, URL userinfo (`user:password@`, spaces
    included) becomes `***@`, and any other key-shaped token keeps only its prefix. Used for every message
    that may carry a URL, a key or an exception's text."""
    text = str(text)
    for secret in _secret_values():
        if secret in text:
            text = text.replace(secret, _key_prefix(secret))
    text = _USERINFO_RE.sub(lambda m: m.group(1) + '***@', text)
    return _KEY_RE.sub(lambda m: m.group(1) + '...', text)


def url_problem(url) -> str | None:
    """Why a provider URL is refused, or None. Ambiguous forms parse differently in urlsplit and in
    requests/urllib3 (`https://remote.example\\@localhost/v1` is `localhost` to one and `remote.example` to
    the other), so they never reach a request: a backslash, whitespace or a control character, userinfo
    (`@` in the authority), a scheme other than http/https, or no host."""
    if not isinstance(url, str) or not url:
        return 'empty URL'
    if '\\' in url or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url):
        return 'a backslash, whitespace or a control character'
    try:
        parts = urlsplit(url)
        host = parts.hostname
        parts.port                      # raises on a malformed port
    except ValueError:
        return 'unparsable'
    if parts.scheme not in ('http', 'https'):
        return f'scheme {parts.scheme or "(none)"!r} (http or https only)'
    if '@' in parts.netloc:
        return 'userinfo (user:password@) in the URL'
    if not host:
        return 'no host'
    return None


def check_url(url) -> str:
    """`url` unchanged, or ImageGenError (redacted) naming why it is refused."""
    why = url_problem(url)
    if why:
        raise ImageGenError(f'refused provider URL {redact(url)!r}: {why}')
    return url


def _config_from_value(value: str) -> ProviderConfig:
    """Build a ProviderConfig from a bare key or URL."""
    v = value.strip()
    provider = detect_provider(v)
    if provider == 'sd_a1111':
        return ProviderConfig(provider=provider, base_url=v)
    return ProviderConfig(provider=provider, key=v)


def _config_from_dict(d: dict) -> ProviderConfig:
    """Build a ProviderConfig from a JSON object; detect provider if missing."""
    provider = d.get('provider')
    if not provider:
        seed = d.get('key') or d.get('base_url')
        if not seed:
            raise UnknownProviderError(
                f'image API config has neither "provider" nor a detectable '
                f'"key"/"base_url"; {_SUPPORTED_FORMS}'
            )
        provider = detect_provider(seed)
    return ProviderConfig(
        provider=provider,
        key=d.get('key'),
        base_url=d.get('base_url'),
        model=d.get('model'),
    )


def _parse_config_text(text: str) -> ProviderConfig:
    """Parse IMAGE_API / config-file content: JSON object or bare key/URL."""
    text = text.strip()
    if text.startswith('{'):
        return _config_from_dict(json.loads(text))
    return _config_from_value(text)


# --------------------------------------------------------------------------
# Codex CLI (ChatGPT subscription): detection
# --------------------------------------------------------------------------

def _run(argv, **kwargs):
    """The one subprocess seam of this module (Codex login check, art.py).
    Tests replace it; nothing in the test suite ever reaches a real Codex."""
    return subprocess.run(argv, **kwargs)


def find_codex_cli() -> str | None:
    """Newest %LOCALAPPDATA%\\OpenAI\\Codex\\bin\\*\\codex.exe, else `codex` on
    PATH, else None (same discovery as cube_art-director's art_codex.py)."""
    local = os.environ.get('LOCALAPPDATA')
    if local:
        found = glob.glob(os.path.join(local, 'OpenAI', 'Codex', 'bin', '*', 'codex.exe'))
        if found:
            return max(found, key=os.path.getmtime)
    return shutil.which('codex')


def codex_login_status(exe: str, *, use_cache: bool = True) -> tuple[bool, str]:
    """(logged in with ChatGPT?, first line of `codex login status`).

    An API-key login does not count: the pipeline only uses Codex on the
    user's ChatGPT subscription. Never logs in or types credentials; when this
    is False the user runs `codex login` themselves."""
    if use_cache and exe in _codex_login_cache:
        return _codex_login_cache[exe]
    try:
        r = _run([exe, 'login', 'status'], capture_output=True, text=True, env=_codex_env(),
                 encoding='utf-8', errors='replace', timeout=60)
        out = f'{r.stdout or ""}\n{r.stderr or ""}'.strip()
        low = out.lower()
        ok = (r.returncode == 0 and 'chatgpt' in low and 'not logged in' not in low
              and 'api key' not in low and 'api_key' not in low)
        first = next((ln.strip() for ln in out.splitlines() if ln.strip()), 'no output')
        result = (ok, first)
    except (OSError, subprocess.TimeoutExpired) as e:
        result = (False, f'`codex login status` failed: {e}')
    _codex_login_cache[exe] = result
    return result


def _codex_env() -> dict:
    """The environment for every Codex subprocess: cube_art-director's `art_codex.codex_env()` (ours minus
    every key Codex could bill or read). Fallback when art_codex cannot be imported: the same suffix rule."""
    try:
        art_dir = str(find_art_py().parent)
        if art_dir not in sys.path:
            sys.path.insert(0, art_dir)
        import art_codex
        return art_codex.codex_env()
    except (ImportError, ImageGenError, OSError):
        drop = _SECRET_ENV + ('OPENAI_BASE_URL',)
        return {k: v for k, v in os.environ.items()
                if k.upper() not in drop and not k.upper().endswith(('_API_KEY', '_API_TOKEN'))}


def detect_codex() -> ProviderConfig | None:
    """The codex step of the chain: a ProviderConfig when a Codex CLI is
    installed and logged in with ChatGPT (and WOWCUBE_NO_CODEX is not set)."""
    if os.environ.get(NO_CODEX_ENV, '').strip().lower() not in ('', '0', 'false', 'no'):
        return None
    exe = find_codex_cli()
    if not exe:
        return None
    ok, _ = codex_login_status(exe)
    return ProviderConfig(provider=CODEX_PROVIDER, cli=exe) if ok else None


def paid_allowed() -> bool:
    """True when the user opted in to paid image APIs (WOWCUBE_ALLOW_PAID_IMAGES=1)."""
    return os.environ.get(ALLOW_PAID_ENV, '').strip().lower() in ('1', 'true', 'yes', 'on')


def explicit_key_config() -> tuple[ProviderConfig, str] | None:
    """Steps 1-2 of the key chain: the pipeline's own settings (IMAGE_API, ~/.wowcube/image_api.json), which
    a user creates on purpose and which therefore count as a choice even without a profile. Never checks the
    opt-in - resolve_provider() does."""
    image_api = os.environ.get(IMAGE_API_ENV)
    if image_api and image_api.strip():
        return _parse_config_text(image_api), f'the {IMAGE_API_ENV} environment variable'

    if CONFIG_PATH.is_file():
        return _parse_config_text(CONFIG_PATH.read_text(encoding='utf-8-sig')), str(CONFIG_PATH)
    return None


def paid_chain() -> tuple[ProviderConfig, str] | None:
    """The key chain alone (steps 1-3): (config, where it came from) or None. Only for an explicit `codex`
    or `image_api` choice. Never checks the opt-in - resolve_provider() does."""
    found = explicit_key_config()
    if found is not None:
        return found

    # last: an OpenRouter key in the environment may have been set for something else
    key = os.environ.get(API_KEY_ENV)
    if key:
        return ProviderConfig(provider='openrouter', key=key), f'the {API_KEY_ENV} environment variable'

    return None


def is_local_url(url: str | None) -> bool:
    """True only for an unambiguous http(s) URL (`url_problem()` finds nothing) whose host is exactly
    `localhost`, a 127.0.0.0/8 address or `::1`. A LAN or hosted URL, `localhost.evil.com`,
    `127.0.0.1.nip.io` or anything with userinfo or a backslash is False (someone else's server, possibly
    billed)."""
    if url_problem(url):
        return False
    host = urlsplit(url).hostname.lower()
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_free_local(config: ProviderConfig) -> bool:
    """A server on this machine - a local Stable Diffusion, or a local
    OpenAI-compatible server as the `openai` base_url: no paid opt-in needed."""
    return config.provider in ('sd_a1111', 'openai') and is_local_url(config.base_url)


def _config_from_profile(choice) -> tuple[ProviderConfig, str]:
    """ProviderConfig for an explicit profile choice (not codex/image_api/none)."""
    pid = choice.provider
    if pid == 'local_sd':
        url = choice.local_sd or profile_provider.DEFAULT_LOCAL_SD
        return ProviderConfig(provider='sd_a1111', base_url=url), choice.source
    if pid not in profile_provider.DEFAULT_KEY_ENVS:
        raise UnknownProviderError(f'unknown image provider {redact(pid)!r} in {choice.source}')
    path = profile_provider.credential_file(choice)
    if path is not None:
        if not path.is_file():
            raise ImageGenError(f'{choice.source} chose {pid} with the credential file {path}, which does not exist')
        config = _parse_config_text(path.read_text(encoding='utf-8-sig'))
        if config.provider != pid:
            raise ImageGenError(f'{choice.source} chose {pid}, but {path} holds a {config.provider} config')
        return config, f'{choice.source}, credential {path}'
    key, name = profile_provider.credential(choice)
    if not key:
        raise ImageGenError(f'{choice.source} chose {pid}, but {name} is not set: the user sets it in their own '
                            f'shell (never in a profile), or runs setup again to pick another provider')
    return ProviderConfig(provider=pid, key=key), f'{choice.source}, key from {name}'


def _check_policy(config: ProviderConfig, choice) -> None:
    if choice.local_only and not is_free_local(config):
        raise DataPolicyBlocked(
            f'the project data policy keeps everything on this machine (data_policy.may_leave_machine: []), '
            f'and {config.provider} is not a server on this machine: use the own art of the user or the procedural '
            f'style, a local Stable Diffusion, or change the policy with the user (setup)')


def resolve_provider(*, allow_paid: bool | None = None, workspace=None, manifest=None) -> ProviderConfig | None:
    """The provider to draw with; None means draw in code: nothing was chosen
    (NO_CHOICE_HINT says how to choose), or the choice is `none`. A Codex
    login or a stray key is never used without a choice (module docstring).
    `workspace` / `manifest` locate wowcube.project.json (default: the
    current folder).

    A paid/external provider is returned only when `allow_paid` is True, or
    (when it is None) WOWCUBE_ALLOW_PAID_IMAGES=1; otherwise
    PaidProviderNotAllowed explains what was found and how to proceed - a
    configured or inherited key is never used silently. A server on this
    machine needs no opt-in."""
    try:
        choice = profile_provider.read_choice(workspace, manifest)
    except ValueError as e:
        raise UnknownProviderError(redact(e)) from None
    pid = choice.provider

    if pid == 'none':
        return None
    if pid is None:
        # no choice: only the pipeline's own key settings count; never a Codex login or a stray key
        found = explicit_key_config()
        if found is None:
            return None
    elif pid in (CODEX_PROVIDER, 'image_api'):
        if pid == CODEX_PROVIDER:
            codex = detect_codex()
            if codex is not None:
                _check_policy(codex, choice)
                return codex
        found = paid_chain()
        if found is None:
            return None
    else:
        found = _config_from_profile(choice)
    config, source = found
    _check_policy(config, choice)
    if is_free_local(config):
        return config
    if allow_paid is None:
        allow_paid = paid_allowed()
    if not allow_paid:
        raise PaidProviderNotAllowed(
            f'the image provider chosen is a PAID/external API ({config.provider}, from {source}). It is never '
            f'used silently: only after the user agreed to pay per image, set {ALLOW_PAID_ENV}=1 '
            f'(build_pipeline.py generate / gen_sprites.py: --allow-paid). Or the user picks another tool '
            f'(say which one, or run setup). Without either, the asset builder draws the art in code (the '
            f'procedural style, final quality).')
    config._paid_consent = True         # not a dataclass field: never saved, never set by a caller's constructor
    return config


def save_provider(value: str | dict) -> ProviderConfig:
    """Persist a pasted key/URL (or a config dict) to the config file.

    Used by the orchestrator intake flow: the user pastes a key once, it is
    detected, written to `~/.wowcube/image_api.json`, and every later run
    resolves it from there. Raises UnknownProviderError (before writing
    anything) if the value matches no known pattern.
    """
    if isinstance(value, dict):
        config = _config_from_dict(value)
    else:
        config = _config_from_value(value)

    data = {k: v for k, v in asdict(config).items() if v is not None}
    _write_private(CONFIG_PATH, json.dumps(data, indent=2))
    return config


def _write_private(path: Path, text: str) -> None:
    """Write a secret readable by the owner only: the folder 0700 and the
    file created 0600 (no window where it is world-readable), then chmod'ed
    0600 again in case it already existed with wider bits. On Windows the
    mode bits only toggle read-only; the file then relies on the per-user ACL
    of the profile folder it lives in (best effort)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != 'nt':
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(text)
    if os.name != 'nt':
        os.chmod(path, 0o600)


# --------------------------------------------------------------------------
# Image helpers (moved from genimg.py)
# --------------------------------------------------------------------------

def base64_to_image(base64_string):
    """Decode a base64 PNG/JPEG (optionally a data: URI) into a fully loaded PIL Image. Any decoding
    failure (bad base64, a truncated or corrupt image) raises ImageGenError, so one bad answer fails one
    sprite, never the batch."""
    try:
        for prefix in ('data:image/png;base64,', 'data:image/jpeg;base64,', 'data:image/webp;base64,'):
            if base64_string.startswith(prefix):
                base64_string = base64_string[len(prefix):]
                break
        image = Image.open(BytesIO(base64.b64decode(base64_string)))
        image.load()                    # PIL decodes lazily: force it here, inside the guard
        return image
    except Exception as e:
        raise ImageGenError(f'the provider returned an image that cannot be decoded: {redact(e)}') from None


def png_image_to_base64(filename):
    """Encode an image file into a base64 encoded PNG data URI."""
    try:
        image = Image.open(filename)
        buffered = BytesIO()
        image.save(buffered, format='PNG')
        img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return f'data:image/png;base64,{img_str}'
    except Exception as e:
        print(f'Error encoding image to base64: {e}')
        return None


# --------------------------------------------------------------------------
# Codex drawing: delegated to cube_art-director's art.py
# --------------------------------------------------------------------------

def find_art_py() -> Path:
    """cube_art-director's art.py: $WOWCUBE_ART_PY, else
    skills/cube_art-director/scripts/art.py next to this scripts/ folder (or
    in any ancestor, for the packaged plugin layout)."""
    env = os.environ.get(ART_PY_ENV)
    if env:
        p = Path(env)
        if p.is_file():
            return p
        raise ImageGenError(f'{ART_PY_ENV}={env} does not exist')
    here = Path(__file__).resolve().parent
    for base in (here, *here.parents):
        cand = base / _ART_PY_REL
        if cand.is_file():
            return cand
    raise ImageGenError(f'cube_art-director art.py not found (looked for {_ART_PY_REL.as_posix()} '
                        f'above {here}); set {ART_PY_ENV}')


def run_art(cmd: str, spec, *, workspace=None, extra=()) -> int:
    """Run one art.py command (`gen`, `process`, `qa`, ...) on a spec (a
    WowCube manifest or an art.json); output streams to the console so the
    agent sees Codex progress and the copy-pasteable retry commands."""
    argv = [sys.executable, str(find_art_py()), cmd, str(spec)]
    if workspace is not None:
        argv += ['--workspace', str(workspace)]
    argv += [str(x) for x in extra]
    print('  $ ' + ' '.join(argv), flush=True)
    return _run(argv).returncode


def codex_generate(manifest_path, workspace, *, only=None, force=False, jobs=None, over_budget=False) -> None:
    """Draw a WowCube manifest with Codex through cube_art-director.

    `art.py gen` draws every sprite without a raw image (style anchors and the
    STYLE.md Prompt block attached, the sprite's flat chroma-key backdrop or
    opaque canvas, subject references from <workspace>/fixes.json, dependency
    order), then `art.py process` keys and fits them into
    <workspace>/art/<name>.png (shared scale + centroid alignment per
    animation set, colour lock per fixes.json). `process` also runs after a
    partial `gen` failure: it never refits a set with a missing member, so the
    finished sprites are ready for QA while the failed ones are retried.
    Raises ImageGenError naming the failed step(s)."""
    sel = ['--only', ','.join(only)] if only else []
    gen_extra = (sel + (['--force'] if force else []) + (['--jobs', str(int(jobs))] if jobs else [])
                 + (['--over-budget'] if over_budget else []))
    rc_gen = run_art('gen', manifest_path, workspace=workspace, extra=gen_extra)
    rc_process = run_art('process', manifest_path, workspace=workspace, extra=sel)
    if rc_gen == 4:      # art_budget.EXIT_OVER_BUDGET: nothing was drawn
        raise ImageGenError('art.py gen refused the run: the image budget does not cover it (the line above says '
                            'how much is spent and left)')
    failed = [step for step, rc in (('gen', rc_gen), ('process', rc_process)) if rc != 0]
    if failed:
        raise ImageGenError(
            f'art.py {" + ".join(failed)} failed (exit {rc_gen}/{rc_process}); the lines above name the '
            f'sprites and print the retry command (a rerun of `gen` only draws what is still missing)')


def codex_draw(prompt, *, size=None, reference=None, background='opaque', key='auto') -> Image.Image:
    """One image with Codex, through a throw-away art.json run by art.py
    (`gen` + `process`): `background` "key" = drawn on a flat chroma-key
    backdrop and cut out (binary alpha), "opaque" = full-canvas picture;
    `size` (w, h) = final size (default: the 1024x1024 canvas); `reference` =
    an image to keep as the subject. For a whole manifest use codex_generate()
    (sets, anchors and colour lock only exist there)."""
    w, h = (int(size[0]), int(size[1])) if size else (1024, 1024)
    work = Path(tempfile.mkdtemp(prefix='wcx'))     # short path: long ones break Codex on Windows
    try:
        asset = {'name': 'image', 'size': [w, h], 'prompt': str(prompt), 'background': background,
                 'key': key, 'alpha': 'binary'}
        if reference:
            asset['subject_ref'] = str(Path(reference).resolve())
        spec = work / 'art.json'
        spec.write_text(json.dumps({'project': 'genimg', 'workspace': 'ws', 'assets': [asset]}, indent=1),
                        encoding='utf-8')
        if run_art('gen', spec) != 0:
            raise ImageGenError('codex drew no image (see the art.py output above)')
        if run_art('process', spec) != 0:
            raise ImageGenError('art.py process failed on the codex image')
        out = work / 'ws' / 'final' / 'image.png'
        if not out.is_file():
            raise ImageGenError(f'art.py produced no {out.name}')
        with Image.open(out) as im:
            im.load()
            return im.copy()
    finally:
        shutil.rmtree(work, ignore_errors=True)


# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------

class ImageProvider:
    """Base class: shared retry loop + auth header; subclasses implement
    `_request(prompt, reference)` (one HTTP call -> PIL Image or None) and
    `validate()` (cheapest authenticated call)."""

    #: default model, overridable via ProviderConfig.model
    default_model = None

    #: True only for providers whose endpoint comes from base_url and may be a server on this machine
    #: (OpenAI-compatible, A1111). A provider with a hard-coded external endpoint never gets the local exemption.
    local_capable = False

    def __init__(self, config: ProviderConfig):
        if config.base_url:
            check_url(config.base_url)
        # an immutable private snapshot: changing the caller's ProviderConfig later changes nothing here
        self.config = ProviderSnapshot(provider=config.provider, key=config.key, base_url=config.base_url,
                                       model=config.model, cli=config.cli,
                                       paid_consent=bool(getattr(config, '_paid_consent', False)))
        if config.key:
            _KNOWN_SECRETS.add(config.key)
        self.model = self.config.model or self.default_model

    def _local_destination(self, url: str) -> bool:
        """Is this exact (prepared) URL a server on this machine, for a provider that may use one?"""
        return self.local_capable and is_local_url(url)

    def _require_consent(self, url: str) -> None:
        """Paid consent at the HTTP boundary, judged on the URL actually sent, whatever built this provider
        (resolve_provider, a ProviderConfig passed to genimg, get_provider().generate()): a billable call
        needs WOWCUBE_ALLOW_PAID_IMAGES=1 (--allow-paid) or a config that resolve_provider(allow_paid=True)
        returned."""
        if not self._local_destination(url) and not (paid_allowed() or self.config.paid_consent):
            raise PaidProviderNotAllowed(
                f'{self.name} is a PAID/external image API ({redact(url)}) and the user did not opt in for this '
                f'run: set {ALLOW_PAID_ENV}=1 (--allow-paid) only after the user agreed to pay per image')

    def _send(self, method, url, **kwargs):
        """The one HTTP call of every provider. The URL is prepared the way requests sends it, checked, and
        judged for consent (POST) on that prepared form; a request to this machine ignores environment
        proxies (a proxy would carry the key and prompt off the machine); redirects are never followed (a
        3xx is an error naming where it pointed, redacted)."""
        prepared = requests.PreparedRequest()
        prepared.prepare_url(url, None)
        url = check_url(prepared.url)
        if method == 'post':
            self._require_consent(url)
        if self._local_destination(url):
            kwargs['proxies'] = {'http': None, 'https': None, 'all': None}
        response = getattr(requests, method)(url, allow_redirects=False, **kwargs)
        status = getattr(response, 'status_code', 200)
        if isinstance(status, int) and 300 <= status < 400:
            where = (getattr(response, 'headers', None) or {}).get('Location', '?')
            raise ImageGenError(f'{self.name}: {redact(url)} answered a redirect (HTTP {status} to '
                                f'{redact(where)}); redirects are not followed')
        return response

    @property
    def name(self) -> str:
        return self.config.provider

    def generate(self, prompt: str, *, reference=None, gate=None):
        """Call the provider and return a PIL Image, or None if the model
        answered without an image (e.g. a content refusal — NOT retried).

        Transient network failures (premature close, chunked-encoding error,
        timeouts) are common on slow image endpoints, so each request is
        retried up to 4 times with linear backoff — the exact behaviour of the
        original genimg OpenRouter client. An authentication failure (HTTP
        401/403) is not transient: it raises at once, naming the provider.

        `gate(attempt) -> (ok, why)` (attempt 1..4) is asked before EVERY
        HTTP attempt, a retry included, exactly like art_codex.run: the image
        budget ledger charges each one; (False, why) raises ImageGenError(why)
        and no request is made.
        """
        last_err = None
        for attempt in range(4):
            if gate is not None:
                ok, why = gate(attempt + 1)
                if not ok:
                    raise ImageGenError(why)
            try:
                return self._request(prompt, reference=reference)
            except requests.exceptions.RequestException as e:
                status = getattr(getattr(e, 'response', None), 'status_code', None)
                if status in (401, 403):
                    raise ImageGenError(self._auth_failed(status)) from None     # the cause may echo the key
                last_err = e
                if attempt < 3:
                    time.sleep(2.0 * (attempt + 1))
        raise ImageGenError(
            f'{self.name} request failed after retries: {redact(last_err)}') from None

    def _auth_failed(self, status) -> str:
        """The one-line message for a rejected key (never retried)."""
        msg = (f'authentication failed for provider {self.name} (HTTP {status}, key prefix '
               f'{_key_prefix(self.config.key)}): the key is wrong, revoked, out of credit or not a '
               f'{self.name} key - not retried')
        if self.name == 'openai':
            msg += ('. A bare sk- key is taken as an OpenAI key; DeepSeek keys look the same, but DeepSeek '
                    'has no image API')
        return msg

    def _auth_headers(self) -> dict:
        headers = {'Content-Type': 'application/json'}
        if self.config.key:
            headers['Authorization'] = f'Bearer {self.config.key}'
        return headers

    def _request(self, prompt, *, reference=None):
        raise NotImplementedError

    def validate(self) -> None:
        raise NotImplementedError

    def _validated_get(self, url, **kwargs):
        """GET that converts any failure into ProviderValidationError."""
        try:
            response = self._send('get', url, timeout=(15, 30), **kwargs)
            response.raise_for_status()
            return response
        except (requests.exceptions.RequestException, ImageGenError) as e:
            err = ProviderValidationError(f'{self.name} validation failed ({redact(url)}): {redact(e)}')
            err.status = getattr(getattr(e, 'response', None), 'status_code', None)   # the cause is dropped
        raise err


class OpenRouterProvider(ImageProvider):
    """OpenRouter chat-completions image generation (the original genimg code).

    Endpoint: POST https://openrouter.ai/api/v1/chat/completions
    The model returns the generated image in the final assistant message
    (choices[0].message.images), not in streaming deltas.
    """

    API_URL = 'https://openrouter.ai/api/v1/chat/completions'
    default_model = 'openai/gpt-5.4-image-2'

    def _request(self, prompt, *, reference=None):
        content = [{'type': 'text', 'text': prompt}]
        if reference:
            content.append({
                'type': 'image_url',
                'image_url': {'url': png_image_to_base64(str(reference))},
            })

        payload = {
            'model': self.model,
            'messages': [{'role': 'user', 'content': content}],
            'stream': False,
        }

        response = self._send(
            'post', self.API_URL,
            headers=self._auth_headers(),
            data=json.dumps(payload),
            timeout=TIMEOUT,
        )
        response.raise_for_status()

        data = response.json()
        choices = data.get('choices') or []
        if not choices:
            return None

        message = choices[0].get('message') or {}
        images = message.get('images') or []
        if images:
            base64_url = images[0]['image_url']['url']
            return base64_to_image(base64_url)

        return None

    def validate(self) -> None:
        # GET /api/v1/key returns the key's own metadata (limits/usage) —
        # authenticated, free, no model invocation.
        self._validated_get('https://openrouter.ai/api/v1/key',
                            headers={'Authorization': f'Bearer {self.config.key}'})


class OpenAIProvider(ImageProvider):
    """OpenAI Images API, or any OpenAI-compatible server via `base_url`.

    Endpoint: POST {base_url}/images/generations (default base_url
    https://api.openai.com/v1). gpt-image-* models return the image as
    base64 in data[0].b64_json. Reference images are not sent (that needs the
    multipart /images/edits endpoint); the reference argument is ignored here.
    """

    API_BASE = 'https://api.openai.com/v1'
    API_URL = f'{API_BASE}/images/generations'
    local_capable = True                # an OpenAI-compatible server on this machine via base_url
    default_model = 'gpt-image-1'

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = (config.base_url or self.API_BASE).rstrip('/')

    def _request(self, prompt, *, reference=None):
        payload = {'model': self.model, 'prompt': prompt}
        response = self._send(
            'post', f'{self.base_url}/images/generations',
            headers=self._auth_headers(),
            json=payload,
            timeout=TIMEOUT,
        )
        response.raise_for_status()

        data = (response.json().get('data') or [])
        if data and data[0].get('b64_json'):
            return base64_to_image(data[0]['b64_json'])
        return None

    def validate(self) -> None:
        # GET /v1/models — cheapest authenticated call (no generation billed).
        self._validated_get(f'{self.base_url}/models',
                            headers={'Authorization': f'Bearer {self.config.key}'} if self.config.key else {})


class XAIProvider(ImageProvider):
    """xAI (Grok) image generation — OpenAI-compatible images endpoint.

    Endpoint: POST https://api.x.ai/v1/images/generations
    `response_format: "b64_json"` puts the image bytes in data[0].b64_json.
    Reference images are not supported; the argument is ignored.
    """

    API_URL = 'https://api.x.ai/v1/images/generations'
    default_model = 'grok-2-image'

    def _request(self, prompt, *, reference=None):
        payload = {
            'model': self.model,
            'prompt': prompt,
            'response_format': 'b64_json',
        }
        response = self._send(
            'post', self.API_URL,
            headers=self._auth_headers(),
            json=payload,
            timeout=TIMEOUT,
        )
        response.raise_for_status()

        data = (response.json().get('data') or [])
        if data and data[0].get('b64_json'):
            return base64_to_image(data[0]['b64_json'])
        return None

    def validate(self) -> None:
        # GET /v1/models — cheapest authenticated call.
        self._validated_get('https://api.x.ai/v1/models',
                            headers={'Authorization': f'Bearer {self.config.key}'})


class GeminiProvider(ImageProvider):
    """Google Gemini image generation ("nano banana").

    Endpoint: POST https://generativelanguage.googleapis.com/v1beta/models/
              {model}:generateContent   (header x-goog-api-key)
    Image comes back as a base64 inlineData part inside the first candidate.
    Reference images are not sent; the argument is ignored.
    """

    API_BASE = 'https://generativelanguage.googleapis.com/v1beta'
    default_model = 'gemini-2.5-flash-image'

    def _request(self, prompt, *, reference=None):
        payload = {
            'contents': [{'parts': [{'text': prompt}]}],
            # ask for an image back explicitly — text-only is the default
            'generationConfig': {'responseModalities': ['TEXT', 'IMAGE']},
        }
        response = self._send(
            'post', f'{self.API_BASE}/models/{self.model}:generateContent',
            headers={'x-goog-api-key': self.config.key,
                     'Content-Type': 'application/json'},
            json=payload,
            timeout=TIMEOUT,
        )
        response.raise_for_status()

        candidates = response.json().get('candidates') or []
        if not candidates:
            return None
        parts = (candidates[0].get('content') or {}).get('parts') or []
        for part in parts:
            # REST responses use camelCase; some client shims emit snake_case
            inline = part.get('inlineData') or part.get('inline_data')
            if inline and inline.get('data'):
                return base64_to_image(inline['data'])
        return None

    def validate(self) -> None:
        # GET /v1beta/models — cheapest authenticated call (lists models).
        self._validated_get(f'{self.API_BASE}/models',
                            headers={'x-goog-api-key': self.config.key})


class SDA1111Provider(ImageProvider):
    """Local/self-hosted Stable Diffusion, Automatic1111-compatible API.

    Endpoint: POST {base_url}/sdapi/v1/txt2img
    Response: {"images": ["<base64 png>", ...]} — no auth by default.
    Reference images are not sent (img2img is a different endpoint); the
    argument is ignored. Any other server behind the URL (ComfyUI, ...) is not
    supported: its 404 on /sdapi is reported as such, not retried.
    """

    local_capable = True

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = (config.base_url or '').rstrip('/')

    def _not_a1111(self, url) -> str:
        return (f'{redact(self.base_url)} is not an Automatic1111-compatible Stable Diffusion server '
                f'({redact(url)} answered 404). '
                f'Only the A1111 API (/sdapi/v1/...; start A1111 or Forge with --api) is supported; ComfyUI and '
                f'other servers are not')

    def _request(self, prompt, *, reference=None):
        payload = {'prompt': prompt}
        if self.model:
            # A1111 selects the checkpoint via an override, not a 'model' field
            payload['override_settings'] = {'sd_model_checkpoint': self.model}
        url = f'{self.base_url}/sdapi/v1/txt2img'
        response = self._send(
            'post', url,
            json=payload,
            timeout=TIMEOUT,
        )
        if response.status_code == 404:
            raise ImageGenError(self._not_a1111(url))
        response.raise_for_status()

        images = response.json().get('images') or []
        if images:
            return base64_to_image(images[0])
        return None

    def validate(self) -> None:
        # GET /sdapi/v1/sd-models — cheapest call proving the server is an
        # A1111-compatible endpoint that is up and has checkpoints loaded.
        url = f'{self.base_url}/sdapi/v1/sd-models'
        try:
            self._validated_get(url)
        except ProviderValidationError as e:
            status = getattr(e, 'status', None)
            if status == 404:
                raise ProviderValidationError(self._not_a1111(url)) from None
            raise


class CodexProvider(ImageProvider):
    """Codex CLI on the user's ChatGPT subscription: no key, nothing billed
    per call, the strongest listed model at high effort (cube_art-director's
    art_codex.py picks it). Drawing goes through art.py (codex_draw /
    codex_generate), never through HTTP."""

    def generate(self, prompt, *, reference=None, gate=None):
        # art.py's own run counts the Codex requests of this throw-away project; `gate` (a game's ledger)
        # is asked once for the call
        if gate is not None:
            ok, why = gate(1)
            if not ok:
                raise ImageGenError(why)
        return codex_draw(prompt, reference=reference)

    def validate(self) -> None:
        exe = self.config.cli or find_codex_cli()
        if not exe:
            raise ProviderValidationError(
                'codex CLI not found: install the Codex CLI and run `codex login` with the ChatGPT account')
        ok, info = codex_login_status(exe, use_cache=False)
        if not ok:
            raise ProviderValidationError(
                f'codex is not logged in with ChatGPT ({info}): the user runs `codex login` themselves')


PROVIDERS = {
    CODEX_PROVIDER: CodexProvider,
    'openrouter': OpenRouterProvider,
    'openai': OpenAIProvider,
    'xai': XAIProvider,
    'gemini': GeminiProvider,
    'sd_a1111': SDA1111Provider,
}


def get_provider(config: ProviderConfig) -> ImageProvider:
    """Instantiate the provider implementation for `config`."""
    cls = PROVIDERS.get(config.provider)
    if cls is None:
        raise UnknownProviderError(
            f'unknown image provider {redact(config.provider)!r}; '
            f'known: {", ".join(sorted(PROVIDERS))}'
        )
    return cls(config)


def validate(config: ProviderConfig) -> None:
    """Cheapest possible authenticated call for `config`'s provider.

    Raises ProviderValidationError on any failure (bad key, endpoint down).
    """
    get_provider(config).validate()
