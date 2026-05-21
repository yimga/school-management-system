#!/usr/bin/env python3
"""
Portal theme token spine — zero legacy indigo (102,126,234) in portal CSS bundle.

Canonical mixes live in design-tokens.css (--portal-brand-mix-*).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "static/css/design-tokens.css"
SPINE_FILES = (
    "static/css/portal-theme-modes.css",
    "static/css/portal-base-shell.css",
    "static/css/workflow-center.css",
    "static/css/phase2-portal-bundle.css",
    "static/css/dashboard-layout-controls.css",
)
FORBIDDEN = re.compile(r"102,\s*126,\s*234|102,126,234")
ALLOW_MARKERS = (
    "off-token-allow",
    "portal-theme-spine-allow",
    "theme-locked-allow",
    "theme-attr-contract-allow",
)
REQUIRED_TOKEN = "--portal-brand-mix-14"


def _scan_file(rel: str) -> list[str]:
    path = ROOT / rel
    if not path.is_file():
        return [f"missing {rel}"]
    errors: list[str] = []
    for idx, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if FORBIDDEN.search(line) and not any(m in line for m in ALLOW_MARKERS):
            errors.append(f"{rel}:{idx} legacy indigo literal")
    return errors


def main() -> int:
    errors: list[str] = []
    if not TOKENS.is_file():
        errors.append("missing design-tokens.css")
    else:
        token_text = TOKENS.read_text(encoding="utf-8", errors="replace")
        if REQUIRED_TOKEN not in token_text:
            errors.append("design-tokens.css missing --portal-brand-mix-14 spine token")
        for mix in (
            "--portal-brand-mix-08",
            "--portal-brand-mix-10",
            "--portal-brand-mix-12-accent",
            "--portal-brand-mix-50",
        ):
            if mix not in token_text:
                errors.append(f"design-tokens.css missing {mix}")

    for rel in SPINE_FILES:
        errors.extend(_scan_file(rel))

    if errors:
        print("verify_portal_theme_token_spine: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("verify_portal_theme_token_spine: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
