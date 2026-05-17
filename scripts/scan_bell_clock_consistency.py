#!/usr/bin/env python
"""Ensure bell-clock SVG is only defined in the canonical partial (Phase 4)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL = REPO_ROOT / "templates" / "components" / "_bell_clock_mark.html"
SCAN_ROOTS = (REPO_ROOT / "templates", REPO_ROOT / "static")

# The canonical file itself is allowed.
ALLOWED_FILES = {CANONICAL.resolve()}

BELL_CLOCK_SVG_RE = re.compile(
    r"<svg[^>]*class=[\"'][^\"']*bell[-_]?clock",
    re.IGNORECASE,
)


def main() -> int:
    if not CANONICAL.is_file():
        print("FAIL: canonical partial missing:", CANONICAL)
        return 1

    violations: list[str] = []
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix not in {".html", ".svg", ".js", ".css"}:
                continue
            if path.resolve() in ALLOWED_FILES:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if BELL_CLOCK_SVG_RE.search(text) and "bell_clock_mark" not in text:
                violations.append(str(path.relative_to(REPO_ROOT)))

    if violations:
        print("FAIL: hand-rolled bell-clock SVG outside canonical partial:")
        for v in sorted(violations):
            print(" ", v)
        return 1

    print("OK: bell-clock mark uses canonical partial only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
