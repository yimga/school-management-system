#!/usr/bin/env python3
"""Fix the `_pages/` static path bug.

Templates reference `{% static '_pages/X.js' %}` which resolves to
`static/_pages/X.js`. But the generator writes files to `static/js/_pages/X.js`.
Every page-level JS bundle 404s on the wrong path.

This script rewrites every `{% static "_pages/..." %}` / `{% static '_pages/...' %}`
to `js/_pages/...`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Allow optional Django filters (|something) after the static path argument and
# permit any whitespace inside the tag.
PAT = re.compile(
    r"(\{%\s*static\s+)(['\"])_pages/([^'\"]+)\2",
)


def fix_text(text: str) -> tuple[str, int]:
    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return f"{m.group(1)}{m.group(2)}js/_pages/{m.group(3)}{m.group(2)}"

    return PAT.sub(repl, text), count


def main(root: Path) -> int:
    total = 0
    files = 0
    for p in sorted(root.rglob("*.html")):
        try:
            src = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new, n = fix_text(src)
        if n:
            p.write_text(new, encoding="utf-8")
            files += 1
            total += n
            print(f"fixed {n:>3}: {p.relative_to(root)}")
    print(f"\nRewrote {total} reference(s) across {files} file(s).")
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("templates")
    raise SystemExit(main(target))
