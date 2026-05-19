#!/usr/bin/env python3
"""Gate: marketing base_marketing.html uses consolidated CSS bundles (no link sprawl)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASE = REPO / "templates" / "marketing" / "base_marketing.html"

# Per-file stylesheets that must NOT reappear once bundled (duplicates hurt cache + bytes).
FORBIDDEN_INDIVIDUAL = (
    "marketing/css/tokens-marketing.css",
    "marketing/css/tokens-editorial.css",
    "marketing/css/tokens-schoolhouse.css",
    "marketing/css/marketing-v3-shell.css",
    "marketing/css/marketing-v3-narrative.css",
    "marketing/css/marketing-shell.css",
    "marketing/css/marketing-accessibility-hardening.css",
    "fonts.googleapis.com",
)

REQUIRED = (
    "marketing/css/marketing-critical.min.css",
    "marketing/css/marketing-enhanced.min.css",
    "marketing/js/mkt-theme-bootstrap.js",
    "marketing/fonts/source-serif-4/",
)


def main() -> int:
    text = BASE.read_text(encoding="utf-8")
    errors: list[str] = []

    for token in REQUIRED:
        if token not in text and token.replace("/", "\\") not in text:
            errors.append(f"missing required token: {token}")

    for token in FORBIDDEN_INDIVIDUAL:
        if token in text:
            errors.append(f"forbidden duplicate stylesheet/CDN: {token}")

    # Count blocking stylesheet links (exclude print-onload deferred pattern in partial)
    blocking = len(
        re.findall(r'<link\s+rel="stylesheet"[^>]*>', text, flags=re.I)
    )
    # Deferred enhanced bundle is loaded via partial (media=print onload), not counted here.
    blocking_in_base = blocking
    if blocking_in_base > 5:
        errors.append(
            f"too many blocking stylesheets in base_marketing: {blocking_in_base} (max 5)"
        )

    if errors:
        for e in errors:
            print(f"verify_marketing_public_shell: {e}", file=sys.stderr)
        return 1

    print(
        f"verify_marketing_public_shell: OK ({blocking_in_base} blocking stylesheet links)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
