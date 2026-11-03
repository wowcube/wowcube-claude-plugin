#!/usr/bin/env python3
"""Source rules build_game checks before it compiles a game's simulator plugin.

    python game_lint.py <src_dir> [--allow-double-literals]

1. Unsuffixed floating literals (0.5, 1e3, 2.) are rejected. The cube compiles with -fsingle-precision-constant, so
   0.5 is a float there; clang (the Windows and macOS plugin compiler) has no such flag and evaluates it in double, so
   an expression like `0.1 + 0.2 == 0.3` can take different branches in the simulator and on the cube while both
   builds compile cleanly. Fix: write 0.5f. Old games that predate the rule build with --allow-double-literals
   (build_game -AllowDoubleLiterals / --allow-double-literals); their simulator floats may then differ from the cube.
2. Static constructors outside ordinary single-TU globals are rejected: __attribute__((constructor...)),
   [[gnu::constructor]] and init_priority. The plugin runs its globals' initializers after the import table is
   filled; such a function can run before that (on Linux before the plugin's own initializer) and call engine
   functions through empty imports. Initialize in on_init instead.

Comments, string and character literals are ignored. Exit 0 = clean, 1 = findings (file:line: what, fix), 2 = usage.
Standard library only (it runs before every plugin build).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EXTS = {".h", ".hpp", ".c", ".cpp", ".inc"}
MAX_REPORT = 60

# a preprocessing number: digits, letters, dots, digit separators and exponent signs
PP_NUMBER = re.compile(r"\.?[0-9](?:[eEpP][+-]|['\w.])*")
CTOR = re.compile(r"__attribute__\s*\(\(\s*(?:__)?constructor(?:__)?\b|\[\[\s*gnu\s*::\s*constructor\b|\binit_priority\b")


def strip_code(text: str) -> str:
    """Blank out comments, string and character literals (newlines kept, so line numbers hold)."""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif c == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(re.sub(r"[^\n]", " ", text[i:j]))
            i = j
        elif c == "R" and nxt == '"' and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_")):
            m = re.match(r'R"([^ ()\\\t\n]{0,16})\(', text[i:])
            if not m:
                out.append(c)
                i += 1
                continue
            end = text.find(")" + m.group(1) + '"', i + m.end())
            j = n if end < 0 else end + len(m.group(1)) + 2
            out.append(re.sub(r"[^\n]", " ", text[i:j]))
            i = j
        elif c in "\"'":
            # a digit separator (1'000) is not a character literal
            if c == "'" and i > 0 and text[i - 1].isalnum() and nxt.isalnum() and _in_number(text, i):
                out.append(c)
                i += 1
                continue
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            j = min(j + 1, n)
            out.append(re.sub(r"[^\n]", " ", text[i:j]))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _in_number(text: str, i: int) -> bool:
    k = i - 1
    while k >= 0 and (text[k].isalnum() or text[k] in "'._"):
        k -= 1
    return text[k + 1].isdigit() if k + 1 < i else False


def unsuffixed_float(tok: str) -> bool:
    t = tok.replace("'", "")
    low = t.lower()
    if low.startswith("0x"):
        if "p" not in low:
            return False  # a hex integer (0x1e5 has no exponent)
        return low[-1] not in "fl"
    if "." not in t and "e" not in low:
        return False  # an integer
    if "_" in t:
        return False  # a user-defined literal (1.5_deg)
    return low[-1] not in "fl"


def lint_file(path: Path, rel: str, allow_double: bool) -> list[str]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    code = strip_code(raw)
    found = []
    for lineno, line in enumerate(code.split("\n"), 1):
        if CTOR.search(line):
            found.append(f"{rel}:{lineno}: static constructor outside the plugin's init model "
                         f"(__attribute__((constructor)) / [[gnu::constructor]] / init_priority): unsupported, "
                         f"it may run before the engine imports are bound - initialize in on_init")
        if allow_double:
            continue
        for m in PP_NUMBER.finditer(line):
            s = m.start()
            if s > 0 and (line[s - 1].isalnum() or line[s - 1] == "_"):
                continue  # part of an identifier (vec3, x1)
            tok = m.group(0)
            if unsuffixed_float(tok):
                found.append(f"{rel}:{lineno}: unsuffixed floating literal '{tok}' is double in the simulator but float "
                             f"on the cube - add f: '{tok}f'")
    return found


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("src_dir")
    ap.add_argument("--allow-double-literals", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.src_dir)
    if not root.is_dir():
        print(f"game_lint: not a folder: {root}", file=sys.stderr)
        return 2
    found: list[str] = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in EXTS:
            found += lint_file(p, p.relative_to(root).as_posix(), a.allow_double_literals)
    for f in found[:MAX_REPORT]:
        print(f)
    if len(found) > MAX_REPORT:
        print(f"... and {len(found) - MAX_REPORT} more")
    if found:
        floats = sum("floating literal" in f for f in found)
        if floats:
            print(f"game_lint: {floats} unsuffixed floating literal(s). Add f (0.5 -> 0.5f); a game that predates the "
                  f"rule builds with build_game -AllowDoubleLiterals / --allow-double-literals (its simulator floats may "
                  f"then differ from the cube)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
