#!/usr/bin/env python3
"""Verify VISUAL-ENGINE homepage sections and assets are wired."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

SECTION_PARTIALS = (
    "templates/marketing/partials/sections/_sovereign_kernel.html",
    "templates/marketing/partials/sections/_clinical_ledger.html",
    "templates/marketing/partials/sections/_rugged_engine.html",
    "templates/marketing/partials/sections/_fluid_classroom.html",
)

HOME = REPO / "templates" / "schools" / "marketing_landing_v2.html"
CSS = REPO / "static" / "marketing" / "css" / "marketing-visual-engine.css"
TAGS = REPO / "apps" / "schools" / "templatetags" / "marketing_media.py"


def main() -> int:
    errors: list[str] = []
    for rel in SECTION_PARTIALS:
        if not (REPO / rel).is_file():
            errors.append(f"missing partial: {rel}")
    if not CSS.is_file():
        errors.append("missing marketing-visual-engine.css")
    if not TAGS.is_file():
        errors.append("missing marketing_media templatetags")
    if HOME.is_file():
        text = HOME.read_text(encoding="utf-8")
        for marker in (
            "_sovereign_kernel.html",
            "_clinical_ledger.html",
            "_rugged_engine.html",
            "_fluid_classroom.html",
            "marketing-visual-engine.css",
            "mkt-split-ledger.js",
        ):
            if marker not in text:
                errors.append(f"marketing_landing_v2.html missing: {marker}")
    else:
        errors.append("marketing_landing_v2.html missing")
    if errors:
        print("verify_marketing_visual_engine_sections: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("verify_marketing_visual_engine_sections: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
