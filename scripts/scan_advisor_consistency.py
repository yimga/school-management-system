#!/usr/bin/env python
"""Ensure the editorial advisor SVG is only defined in the canonical partial.

Parallel to `scan_bell_clock_consistency.py`. Catches hand-rolled `<svg class="mkt-advisor"
...>` elsewhere in the tree so the figure stays consistent.

Pattern:
- Canonical: templates/marketing/components/_advisor_character.html
- Allowed callers: every other .html may *include* the partial via
  `{% include "marketing/components/_advisor_character.html" ... %}` but must NOT
  re-declare an `<svg class="mkt-advisor ...">` element.
- This scanner walks templates/ + static/ for files containing `<svg ... class="mkt-advisor`
  and reports any that are not the canonical partial.

Run:
    python scripts/scan_advisor_consistency.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL = REPO_ROOT / "templates" / "marketing" / "components" / "_advisor_character.html"
SCAN_ROOTS = (REPO_ROOT / "templates", REPO_ROOT / "static")

# Only the canonical partial may declare the SVG.
ALLOWED_FILES = {CANONICAL.resolve()}

ADVISOR_SVG_RE = re.compile(
    r"<svg[^>]*class=[\"'][^\"']*mkt-advisor\b",
    re.IGNORECASE,
)


def main() -> int:
    if not CANONICAL.is_file():
        print("FAIL: canonical advisor partial missing:", CANONICAL)
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
            # Allow JS / CSS files to reference the class name for styling without
            # declaring the SVG markup itself; only flag <svg ...> declarations.
            if path.suffix in {".js", ".css"}:
                continue
            if ADVISOR_SVG_RE.search(text) and "_advisor_character.html" not in text:
                violations.append(str(path.relative_to(REPO_ROOT)))

    if violations:
        print("FAIL: hand-rolled advisor SVG outside canonical partial:")
        for v in sorted(violations):
            print(" ", v)
        return 1

    print("OK: advisor character uses canonical partial only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
