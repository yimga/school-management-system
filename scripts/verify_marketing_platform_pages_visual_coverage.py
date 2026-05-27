#!/usr/bin/env python3
"""Every type_platform_*.html (except hub) must wire VISUAL-ENGINE strip."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAGES = REPO / "templates" / "marketing" / "pages"
SKIP = frozenset({"type_platform_hub.html"})
MARKERS = ("marketing_platform_visual_strip", "_platform_visual_engine_strip")


def main() -> int:
    errors: list[str] = []
    for path in sorted(PAGES.glob("type_platform_*.html")):
        if path.name in SKIP:
            continue
        text = path.read_text(encoding="utf-8")
        if not any(m in text for m in MARKERS):
            errors.append(path.name)
    if errors:
        print("verify_marketing_platform_pages_visual_coverage: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("verify_marketing_platform_pages_visual_coverage: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
