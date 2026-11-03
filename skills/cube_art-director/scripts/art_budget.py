"""The image budget: one ledger of every real image request, and the cap it is held to.

Every request that can produce (and bill) a picture is one ledger entry: each Codex
attempt of `art.py gen` (a retry is a new request), each panorama picture, each style
candidate, each paid-provider call. Copies of the artist's own `source` images and
processing cost nothing.

Where the ledger lives (`ledger_path`):
  - a WowCube manifest (plans/<game>_assets.json) inside a pipeline workspace that has
    `context/`: `<ws>/context/<game>_images.json`, next to the game's context file. The
    count is mirrored into the context's `spend.images_used` (cube_orchestrator
    AGENT_BRIEFS.md, "Context file") whenever that file exists;
  - anything else (an art.json project, a manifest outside a pipeline workspace):
    `<workspace>/image_ledger.json`.

The budget (`resolve_budget`), first hit wins:
  1. the context: `art_budget.images`, else `profile.budget.images`
     (wowcube-setup PROFILE.md, "Resolved snapshot");
  2. `<ws>/wowcube.project.json`: `budget.images`, else the tier of `verification`
     (lite 30, standard 80, full 200; cube_orchestrator RUN_MODES.md);
  3. an art.json project's own `"budget": {"images": N}`;
  4. a WowCube manifest with no profile at all: the built-in tier `standard` (80);
     an art.json project without a budget: no cap (the ledger still counts).
A context or project file that exists but does not parse is an error (`UnreadableFile`), never a
silent fall back to the tier default.

`--budget N` on the command line caps THIS run only and is never written to the ledger. It may only
lower the cap: a number above the resolved budget is refused unless the run also has the explicit
override (`--over-budget`, only on the user's yes), and then every entry drawn past the resolved
budget is marked `over_budget`. Past the budget nothing is drawn unless the caller passes that
override; overridden entries are marked. A run that needs nothing (everything is drawn) always
passes, however much is spent.

The count: the ledger's entries (an entry may carry `count`, default 1). A context whose
`spend.images_used` is larger than the ledger (a project that counted before the ledger existed)
seeds the ledger with one `seed` entry for the difference; `spend.images_used` never goes down.

Several processes may share a ledger (two `art.py gen` runs, the paid path next to Codex): every
charge is a read-modify-write under a cross-process lock file (`<ledger>.lock`, msvcrt on Windows,
fcntl elsewhere), the ledger and the context mirror are re-read inside the lock and replaced
atomically (temp file + os.replace); the mirror only touches `spend.images_used`.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

TIER_IMAGES = {"lite": 30, "standard": 80, "full": 200}
DEFAULT_TIER = "standard"
EXIT_OVER_BUDGET = 4
EXIT_UNREADABLE = 2
LOCK_TIMEOUT_S = 60.0


class BudgetError(ValueError):
    """The run cannot be budgeted (a refused --budget raise); nothing was drawn."""
    exit_code = EXIT_OVER_BUDGET


class UnreadableFile(BudgetError):
    """A context / project / ledger file exists but does not parse: fail loudly, never guess a budget."""
    exit_code = EXIT_UNREADABLE


def _read(path: Path) -> dict:
    """The JSON object in `path`; {} when the file does not exist; UnreadableFile when it exists but is not
    a JSON object (a corrupted context must not silently become the tier default)."""
    path = Path(path)
    if not path.is_file():
        return {}
    for i in range(20):                     # Windows: a concurrent os.replace can briefly deny the open
        try:
            text = path.read_text(encoding="utf-8-sig")
            break
        except PermissionError:
            if i == 19:
                raise UnreadableFile(f"{path} exists but cannot be read (locked or no permission)") from None
            time.sleep(0.05)
        except OSError as e:
            raise UnreadableFile(f"{path} exists but cannot be read: {e}") from None
    try:
        data = json.loads(text)
    except ValueError as e:
        raise UnreadableFile(f"{path} exists but is not valid JSON ({e}): fix the file (or restore it); the "
                             f"image budget is not guessed from a file that does not parse") from None
    if not isinstance(data, dict):
        raise UnreadableFile(f"{path} is valid JSON but not an object; the image budget cannot be read from it")
    return data


def _write_atomic(path: Path, text: str) -> None:
    """Write `text` to a temp file next to `path`, then os.replace it (retried while Windows denies it)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        for i in range(50):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if i == 49:
                    raise
                time.sleep(0.05)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class _FileLock:
    """A cross-process exclusive lock on `path` (created when missing). The OS releases it when the holder
    dies, so a crashed run never leaves a stale lock."""

    def __init__(self, path: Path, timeout: float = LOCK_TIMEOUT_S):
        self.path, self.timeout, self.fh = Path(path), timeout, None

    def _try(self) -> bool:
        try:
            if os.name == "nt":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.path, "a+b")
        deadline = time.monotonic() + self.timeout
        while not self._try():
            if time.monotonic() > deadline:
                self.fh.close()
                raise BudgetError(f"could not lock {self.path} within {self.timeout:.0f} s (another run holds it)")
            time.sleep(0.01)
        return self

    def __exit__(self, *exc) -> None:
        try:
            if os.name == "nt":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        finally:
            self.fh.close()


def _num(v):
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 else None


def _count(entries: list) -> int:
    """Images the entries stand for: one each, or an entry's `count` (a seed entry)."""
    n = 0
    for e in entries:
        c = _num(e.get("count")) if isinstance(e, dict) else None
        n += 1 if c is None else c
    return n


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def context_path(root: Path, game: str) -> Path:
    return Path(root) / "context" / f"{game}_context.json"


def ledger_path(root: Path, game: str | None, workspace: Path, cube: bool) -> Path:
    """Next to the game's context file when the pipeline workspace has `context/`, else in the art workspace."""
    if cube and game and (Path(root) / "context").is_dir():
        return Path(root) / "context" / f"{game}_images.json"
    return Path(workspace) / "image_ledger.json"


def resolve_budget(root: Path, game: str | None, cube: bool, spec_data: dict | None = None) -> tuple[int | None, str]:
    """(images allowed in total for this game/project or None = no cap, where that number came from).
    A one-run `--budget N` is not a budget source: for_workspace() turns it into a run cap."""
    if cube and game:
        ctx_f = context_path(root, game)
        ctx = _read(ctx_f)
        v = _num((ctx.get("art_budget") or {}).get("images"))
        if v is not None:
            return v, f"{ctx_f} (art_budget.images)"
        v = _num(((ctx.get("profile") or {}).get("budget") or {}).get("images"))
        if v is not None:
            return v, f"{ctx_f} (profile.budget.images)"
    proj_f = Path(root) / "wowcube.project.json"
    proj = _read(proj_f)
    if proj:
        v = _num((proj.get("budget") or {}).get("images"))
        if v is not None:
            return v, f"{proj_f} (budget.images)"
        tier = str(proj.get("verification") or DEFAULT_TIER)
        if tier in TIER_IMAGES:
            return TIER_IMAGES[tier], f"{proj_f} (verification: {tier})"
    if spec_data:
        v = _num((spec_data.get("budget") or {}).get("images"))
        if v is not None:
            return v, "art.json (budget.images)"
    if cube:
        return TIER_IMAGES[DEFAULT_TIER], f"built-in tier {DEFAULT_TIER}"
    return None, "no budget set (counted only)"


class Ledger:
    """One game's / project's image ledger. Safe across threads (`art.py gen` draws in parallel) and
    processes (every charge re-reads the file under `<ledger>.lock`).

    `budget` is the resolved budget (stored in the ledger); `run_cap` a one-run `--budget N` (never
    stored); `override` the user's yes to draw past the budget (`--over-budget`)."""

    def __init__(self, path: Path, budget: int | None, source: str, *, mirror: Path | None = None,
                 override: bool = False, run_cap: int | None = None):
        self.path, self.budget, self.source = Path(path), budget, source
        self.mirror, self.override, self.run_cap = mirror, override, run_cap
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self._tlock = threading.Lock()
        self._mine = 0
        self.entries: list = self._load()

    # ------------------------------------------------------------------ reading
    def _context_used(self) -> int:
        if self.mirror is None:
            return 0
        spend = _read(self.mirror).get("spend")
        return (_num(spend.get("images_used")) or 0) if isinstance(spend, dict) else 0

    def _load(self) -> list:
        """The ledger's entries as stored, plus a seed entry (written with the next charge) when the
        context already counted more images than the ledger holds."""
        entries = _read(self.path).get("entries")
        entries = [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []
        seed = self._context_used() - _count(entries)
        if seed > 0:
            entries.append({"t": _now(), "name": "_seed", "kind": "seed", "count": seed,
                            "note": "spend.images_used of the context, counted before this ledger"})
        return entries

    def refresh(self) -> None:
        """Re-read the ledger (another process may have charged since)."""
        with self._tlock:
            self.entries = self._load()

    @property
    def spent(self) -> int:
        return _count(self.entries)

    @property
    def this_run(self) -> int:
        return self._mine

    @property
    def cap(self) -> int | None:
        """What this run may reach: the run cap, else nothing with the override, else the budget."""
        if self.run_cap is not None:
            return self.run_cap
        return None if self.override else self.budget

    def remaining(self) -> int | None:
        limit = self.cap if self.cap is not None else self.budget
        return None if limit is None else max(0, limit - self.spent)

    def status(self) -> str:
        cap = "no cap" if self.budget is None else f"budget {self.budget}"
        run = ""
        if self.run_cap is not None:
            run = f"; this run capped at {self.run_cap} (--budget)"
        elif self.override and self.budget is not None:
            run = "; --over-budget: past the budget on the user's yes"
        return (f"image budget: {self.spent} spent ({self.this_run} this run), {cap} [{self.source}]{run}; "
                f"ledger {self.path}")

    def _cap_source(self) -> str:
        return "--budget" if self.run_cap is not None else self.source

    def refusal(self, need: int) -> str:
        return (f"image budget: {self.spent} of {self.cap} already spent [{self._cap_source()}] and this run "
                f"needs {need} more request(s) (retries cost extra). Nothing was drawn. Draw fewer (--only), "
                f"waive what is left (STAGE3_ASSETS.md §3, 'A budget ends the redraws'), or ask the user: only "
                f"on their yes raise budget.images in the profile, or rerun with --over-budget.")

    def can_afford(self, need: int) -> bool:
        """Does a run that needs `need` more requests fit? A run that needs nothing always fits."""
        if need <= 0:
            return True
        self.refresh()
        cap = self.cap
        return cap is None or self.spent + need <= cap

    # ------------------------------------------------------------------ writing
    def charge(self, name: str, kind: str, attempt: int = 1) -> tuple[bool, str]:
        """Record one image request before it is made; (False, why) when the budget is spent. A
        read-modify-write under the cross-process lock: entries other runs added are kept."""
        with self._tlock, _FileLock(self.lock_path):
            self.entries = self._load()
            cap = self.cap
            if cap is not None and self.spent >= cap:
                return False, (f"image budget spent ({self.spent}/{cap}, {self._cap_source()}); not drawn "
                               f"(--over-budget only on the user's yes)")
            entry = {"t": _now(), "name": name, "kind": kind, "attempt": attempt}
            if self.budget is not None and self.spent >= self.budget:
                entry["over_budget"] = True
            self.entries.append(entry)
            self._mine += 1
            _write_atomic(self.path, json.dumps({"budget": self.budget, "budget_source": self.source,
                                                 "spent": self.spent, "entries": self.entries}, indent=1))
            self._mirror_spent()
            return True, ""

    def _mirror_spent(self) -> None:
        """Copy the count into the context's spend.images_used (never lower), re-reading the context first
        and leaving every other field as it is. Runs inside the ledger lock."""
        if self.mirror is None or not self.mirror.is_file():
            return
        try:
            ctx = _read(self.mirror)
        except UnreadableFile as e:
            print(f"WARNING: {e}; spend.images_used not updated (the ledger {self.path} still counts)",
                  file=sys.stderr)
            return
        spend = ctx.get("spend") if isinstance(ctx.get("spend"), dict) else {}
        old = _num(spend.get("images_used")) or 0
        spend["images_used"] = max(old, self.spent)
        ctx["spend"] = spend
        _write_atomic(self.mirror, json.dumps(ctx, indent=2, ensure_ascii=False))


def for_workspace(root: Path, game: str | None, workspace: Path, *, cube: bool, spec_data: dict | None = None,
                  cli_budget: int | None = None, override: bool = False) -> Ledger:
    """The ledger of this game/project. `cli_budget` (`--budget N`) caps this run: it may lower the
    budget freely; raising it above the resolved budget needs `override` (the user's yes), else
    BudgetError. UnreadableFile when the context, project or ledger file does not parse."""
    budget, source = resolve_budget(root, game, cube, spec_data)
    if cli_budget is not None:
        if int(cli_budget) < 0:
            raise BudgetError(f"--budget {cli_budget}: must be 0 or more")
        if budget is not None and int(cli_budget) > budget and not override:
            raise BudgetError(
                f"--budget {cli_budget} is above the image budget of {budget} [{source}]. Raising the cap needs "
                f"the user's explicit yes: ask them, then raise budget.images in the profile (or the context's "
                f"art_budget.images), or rerun with --over-budget --budget {cli_budget}. Nothing was drawn.")
    mirror = context_path(root, game) if (cube and game) else None
    return Ledger(ledger_path(root, game, workspace, cube), budget, source, mirror=mirror, override=override,
                  run_cap=None if cli_budget is None else int(cli_budget))
