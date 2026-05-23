#!/usr/bin/env python3
"""Fail CI if marketing templates reference dict keys starting with underscore.

Django rejects ``{{ marketing_local._foo }}`` at compile time — production 500.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(
    r"\{\{[^}]*\bmarketing_local\._[a-zA-Z_][a-zA-Z0-9_]*",
    re.MULTILINE,
)
PATTERN_IF = re.compile(
    r"\{%\s*if[^%]*\bmarketing_local\._[a-zA-Z_][a-zA-Z0-9_]*",
    re.MULTILINE,
)


def main() -> int:
    errors: list[str] = []
    for path in sorted((ROOT / "templates" / "marketing").rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        for pat in (PATTERN, PATTERN_IF):
            for match in pat.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                errors.append(f"{path.relative_to(ROOT)}:{line}: {match.group(0)[:80]}")
    if errors:
        print("MARKETING_TEMPLATE_UNDERSCORE_VAR_FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("MARKETING_TEMPLATE_UNDERSCORE_VAR_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
