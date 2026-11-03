"""Run the local Codex CLI (logged in with a ChatGPT subscription) to draw one
image with its built-in image generation tool.

No API key is involved: Codex bills the user's ChatGPT plan - but only when it
is logged in WITH ChatGPT. A Codex CLI logged in with an OpenAI API key bills
that key per call, so `run()` first requires `codex login status` to report a
ChatGPT login (checked once per process) and otherwise stops with a message:
the user runs `codex login` themselves. Model choice: the strongest listed
model in ~/.codex/models_cache.json (lowest priority value) at "high"
reasoning effort (the model's own default when it lists no "high"). Without
a readable cache no -m is passed: Codex uses its own default model.
ART_CODEX_MODEL picks the model, ART_CODEX_EFFORT the effort (e.g. "xhigh"
or "max" on request: slower, rarely better for images).

Every key of another provider is removed from the codex child environment
(codex_env), so nothing the user set for something else can be billed.

Lessons baked in (each one cost a broken batch once):
- parallel runs share ~/.codex/generated_images; Codex's own "copy the newest
  PNG" step grabs a sibling's picture -> take the image from THIS run's
  session folder (session id parsed from the CLI output);
- long working-directory paths break the CLI on Windows -> short temp dir;
- "model is at capacity" is transient -> retry with back-off;
- references are attached with -i and kept OUT of the work dir, so they can
  never be mistaken for the output.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


def find_codex() -> str:
    found = sorted(glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\OpenAI\Codex\bin\*\codex.exe")),
                   key=os.path.getmtime, reverse=True)
    if found:
        return found[0]
    on_path = shutil.which("codex")
    if on_path:
        return on_path
    raise SystemExit("codex not found: install the Codex CLI and run `codex login` with a ChatGPT account")


# `codex login status` verdict per CLI path, once per process (a batch draws
# dozens of images; the login does not change mid-run).
_login_ok: dict[str, tuple[bool, str]] = {}

# Keys the Codex CLI would bill instead of the ChatGPT login (codex exec reads CODEX_API_KEY; an
# OPENAI_API_KEY set for something else must not reach it either), plus every other provider key this
# repo knows: the agent Codex runs has no business seeing them. Removed from every codex call, together
# with anything named *_API_KEY / *_API_TOKEN.
_BILLABLE_ENV = ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENROUTER_API_KEY", "IMAGE_API",
                 "GEMINI_API_KEY", "GOOGLE_API_KEY", "XAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY",
                 "FAL_KEY", "REPLICATE_API_TOKEN", "ELEVENLABS_API_KEY")
_BILLABLE_SUFFIXES = ("_API_KEY", "_API_TOKEN")


def codex_env() -> dict[str, str]:
    """The environment for a codex subprocess: ours minus every key it could bill."""
    return {k: v for k, v in os.environ.items()
            if k.upper() not in _BILLABLE_ENV and not k.upper().endswith(_BILLABLE_SUFFIXES)}


_KEY_RE = re.compile(r"\b(sk-or-|sk-|xai-|AIza)[A-Za-z0-9_\-]{4,}")
_USERINFO_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)[^/?#\r\n]*@")


def _prefix(secret: str) -> str:
    for p in ("sk-or-", "sk-", "xai-", "AIza"):
        if secret.startswith(p):
            return p + "..."
    return secret[:2] + "..."


def redact(text: str) -> str:
    """Text for a log file or a message: the value of every key variable codex_env() strips (wherever it
    appears), URL userinfo and key-shaped tokens are cut to a prefix. Prompts stay readable."""
    text = str(text)
    secrets = sorted({v.strip() for k, v in os.environ.items()
                      if v and v.strip() and len(v.strip()) >= 6
                      and (k.upper() in _BILLABLE_ENV or k.upper().endswith(_BILLABLE_SUFFIXES))},
                     key=len, reverse=True)
    for v in secrets:
        text = text.replace(v, _prefix(v))
    text = _USERINFO_RE.sub(lambda m: m.group(1) + "***@", text)
    return _KEY_RE.sub(lambda m: m.group(1) + "...", text)


def login_status(exe: str) -> tuple[bool, str]:
    """(logged in with ChatGPT?, first line of `codex login status`).
    An API-key login ("Logged in using an API key") is NOT ok: it bills the
    key instead of the subscription."""
    try:
        r = subprocess.run([exe, "login", "status"], capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace", env=codex_env())
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"`codex login status` failed: {e}"
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    out = out.strip()
    low = out.lower()
    ok = (r.returncode == 0 and "chatgpt" in low and "not logged in" not in low
          and "api key" not in low and "api_key" not in low)
    first = next((ln.strip() for ln in out.splitlines() if ln.strip()), "no output")
    return ok, first


def require_chatgpt_login(exe: str) -> None:
    """Stop (SystemExit) unless `exe` is logged in with ChatGPT. Never logs in
    or types credentials. Only a positive verdict is cached."""
    if exe in _login_ok and _login_ok[exe][0]:
        return
    ok, info = login_status(exe)
    if ok:
        _login_ok[exe] = (ok, info)
        return
    raise SystemExit(
        f"codex is not logged in with a ChatGPT account ({info}). Nothing was generated: a Codex CLI logged in "
        f"with an OpenAI API key (or not at all) would bill that key or fail. Ask the user to run `codex login` "
        f"and sign in with ChatGPT, then rerun.")


DEFAULT_EFFORT = "high"


def pick_model() -> tuple[str | None, str | None]:
    """(model, effort); None = do not pass it (Codex's own default).

    Model: ART_CODEX_MODEL, else the strongest listed model of
    ~/.codex/models_cache.json, else None - a guessed slug this account
    cannot use would fail every image. Effort: ART_CODEX_EFFORT, else "high"
    (when the model's cache entry does not list "high": its default, else None). With ART_CODEX_MODEL set,
    the levels come from that model's own cache entry; not cached -> "high".)"""
    model, effort = os.environ.get("ART_CODEX_MODEL"), os.environ.get("ART_CODEX_EFFORT")
    if model and effort:
        return model, effort
    cache = Path.home() / ".codex" / "models_cache.json"
    best = None
    try:
        data = json.loads(cache.read_text(encoding="utf-8-sig"))
        entries = [m for m in data.get("models", []) if isinstance(m, dict) and m.get("slug")]
        if model:
            # ART_CODEX_MODEL alone: the effort levels are that model's own (any visibility), never another's
            best = next((m for m in entries if m.get("slug") == model), None)
        else:
            listed = [m for m in entries if m.get("visibility") == "list"]
            best = min(listed, key=lambda m: m.get("priority", 999)) if listed else None
    except (OSError, ValueError, AttributeError):
        pass
    if best is None:
        return model, effort or DEFAULT_EFFORT
    if not effort:
        levels = [lv.get("effort") for lv in best.get("supported_reasoning_levels", []) if isinstance(lv, dict)]
        if not levels or DEFAULT_EFFORT in levels:
            effort = DEFAULT_EFFORT
        else:
            effort = best.get("default_reasoning_level") or None
    return model or best["slug"], effort


def build_prompt(name: str, body: str, *, n_anchors: int, subject: bool, sketch: bool,
                 background: str, key: str, n_style_refs: int = 0) -> str:
    refs = ""
    if n_style_refs:
        refs += (f"The first {n_style_refs} attached image(s) are the ARTIST'S STYLE REFERENCES (not yet a locked "
                 "style): render the subject so it would sit naturally among them - same rendering technique, "
                 "palette family, outline and detail level. Copy only the style, never their content. ")
    if n_anchors:
        refs += (f"The first {n_anchors} attached image(s) are the APPROVED STYLE ANCHORS. Pass them to the image "
                 "tool as style references and match their rendering exactly: pixel size, outline colour and "
                 "weight, shading steps, light direction, palette, level of detail. Copy ONLY the style, never "
                 "their content, characters, composition or background. ")
    idx = n_style_refs + n_anchors + 1
    if subject:
        refs += (f"Attached image #{idx} is the SUBJECT REFERENCE: keep that exact character/object (same design, "
                 "proportions, colours, scale, costume details) and change only what the prompt asks for. ")
        idx += 1
    if sketch:
        refs += (f"Attached image #{idx} is the ARTIST'S SKETCH: follow its pose, composition and proportions "
                 "precisely and render it in the anchors' style. ")
    if refs:
        refs += "Never edit, return or paste a reference image itself. "
    if background == "key":
        hexkey = "#00FF00 pure green" if key == "green" else "#FF00FF pure magenta"
        bg = (f"Background: one flat uniform {hexkey} colour filling the whole canvas, no gradient, no floor, "
              "no cast shadow, no vignette; the subject must not use that colour anywhere. Single subject "
              "centred with a clear margin, nothing touching the canvas edge. ")
    else:
        bg = "The picture fills the whole canvas edge to edge (opaque, no border, no frame). "
    return (
        "Use your built-in image generation tool exactly once to create this image. "
        f"{refs}Canvas: square 1024x1024. {bg}No text, watermark, signature, border or UI unless the prompt asks "
        "for text.\n\nImage prompt (use it verbatim):\n\n"
        f"{body.strip()}\n\n"
        f"Save the generated PNG into the current directory as {name}.png (copy it from wherever the tool stores "
        "it). Do not edit the image yourself. Reply with the saved absolute path only."
    )


def doctor() -> list[tuple[bool, str]]:
    """Setup check for the artist: binary, ChatGPT login, model choice."""
    out = []
    try:
        exe = find_codex()
        out.append((True, f"codex CLI: {exe}"))
    except SystemExit as e:
        return [(False, str(e))]
    ok, info = login_status(exe)
    out.append((ok, "login: " + info +
                ("" if ok else " (run `codex login` and sign in with the ChatGPT account, not an API key)")))
    m, e = pick_model()
    model = m or "Codex's default (no ~/.codex/models_cache.json to pick from; ART_CODEX_MODEL chooses one)"
    out.append((True, f"model: {model} at effort {e or 'the model default'}"
                      + ("" if os.environ.get("ART_CODEX_EFFORT") else " (ART_CODEX_EFFORT=xhigh|max for more)")))
    return out


def _log_tail(text: str, n: int = 5) -> str:
    """The last `n` non-empty lines of a Codex log, joined for a one-line message."""
    lines = [ln.strip() for ln in redact(text).splitlines() if ln.strip() and ln.strip() != "--- stderr ---"]
    return " | ".join(lines[-n:]) or "(empty)"


def run(name: str, prompt: str, refs: list[Path], out_png: Path, log_dir: Path,
        retries: int = 3, timeout: int = 900, gate=None) -> tuple[bool, str]:
    """Draw one image. `gate(attempt) -> (ok, why)` is asked before EVERY Codex request (a retry is a new
    request that can be billed): the image budget ledger (art_budget.py) records it or refuses it."""
    codex = find_codex()
    require_chatgpt_login(codex)          # before anything can be billed
    model, effort = pick_model()
    base = Path(tempfile.gettempdir()) / "artgen"
    base.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    last = ""
    for attempt in range(1, retries + 1):
        if gate is not None:
            ok, why = gate(attempt)
            if not ok:
                return False, why if not last else f"{why}; earlier attempt: {last}"
        # unique short dir per call: two projects drawing "hero" at once must not share it
        work = Path(tempfile.mkdtemp(prefix="g", dir=base))
        cmd = [codex, "exec"]
        if model:
            cmd += ["-m", model]
        if effort:
            cmd += ["-c", f'model_reasoning_effort="{effort}"']
        cmd += ["--skip-git-repo-check", "-C", str(work), "-s", "workspace-write", "--ephemeral"]
        for r in refs:
            cmd += ["-i", str(r)]
        cmd.append("-")
        t0 = time.time()
        try:
            proc = subprocess.run(cmd, input=prompt, text=True, capture_output=True,
                                  encoding="utf-8", errors="replace", timeout=timeout, env=codex_env())
            out = proc.stdout + "\n--- stderr ---\n" + proc.stderr
        except subprocess.TimeoutExpired as e:
            out = f"timeout after {timeout}s\n{e.stdout or ''}"
            proc = None
        log = log_dir / f"{name}.log"
        log.write_text(redact(f"model={model or 'default'} effort={effort or 'default'} attempt={attempt}\n"
                              f"--- prompt ---\n{prompt}\n--- output ---\n{out}"), encoding="utf-8")
        pngs = []
        sid = re.search(r"session id:\s*([0-9a-f-]{36})", out)
        if sid:
            own = Path.home() / ".codex" / "generated_images" / sid.group(1)
            pngs = sorted(own.glob("*.png"), key=os.path.getmtime)
        if not pngs:
            pngs = sorted(work.glob("*.png"), key=os.path.getmtime)
        if pngs:
            out_png.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(pngs[-1], out_png)
            shutil.rmtree(work, ignore_errors=True)
            return True, f"{time.time() - t0:.0f}s ({model or 'default model'}/{effort or 'default effort'})"
        shutil.rmtree(work, ignore_errors=True)
        last = f"no PNG (rc={proc.returncode if proc else 'timeout'}); {log} ends: {_log_tail(out)}"
        if "capacity" in out.lower() or "rate limit" in out.lower() or "429" in out:
            time.sleep(30 * attempt)
            continue
        if attempt < retries:
            time.sleep(5)
    return False, last
