#!/usr/bin/env python3
"""Gate: manager marketplace control-plane pages use compact surface + paginate policy."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates" / "marketplace"

REQUIRED = (
    "app_catalog.html",
    "governance_console.html",
    "blueprint_marketplace.html",
    "compatibility_matrix.html",
    "sandbox_inspector.html",
    "installation_health.html",
)

MARKERS = (
    'data-rmc-scroll-policy="paginate"',
    "rmc-cp-compact",
    "rmc-cp-compact__fold-nav",
    "components/pagination.html",
)


def main() -> int:
    failures: list[str] = []
    for name in REQUIRED:
        path = TEMPLATES / name
        if not path.is_file():
            failures.append(f"missing template: {path.relative_to(ROOT)}")
            continue
        text = path.read_text(encoding="utf-8")
        for marker in MARKERS:
            if marker not in text:
                failures.append(f"{name}: missing {marker}")
    if failures:
        print("MARKETPLACE_CP_COMPACT_CONTRACT: FAIL")
        for line in failures:
            print(f"  - {line}")
        return 1
    print(f"MARKETPLACE_CP_COMPACT_CONTRACT: PASS ({len(REQUIRED)} templates)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
