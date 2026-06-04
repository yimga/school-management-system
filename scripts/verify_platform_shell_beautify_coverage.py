#!/usr/bin/env python3
"""Ensure platform beautify partial is wired on all root shells."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BEAUTIFY_PARTIAL = 'partials/rmc_platform_shell_beautify_styles.html'
BEAUTIFY_CSS = "rmc-platform-beautify-v4.css"

# Root shells that must load the shared beautify partial (directly or via chrome bundle).
REQUIRED = (
    "templates/partials/rmc_platform_chrome_styles.html",
    "templates/marketing/base_marketing.html",
    "templates/studio_os/studio_embed_minimal.html",
)

# Shells that include rmc_platform_chrome_styles inherit beautify automatically.
CHROME_PARENTS = (
    "templates/base.html",
    "templates/portal_base.html",
    "templates/control_plane_skeleton.html",
    "templates/admin/base_site.html",
)


def main() -> int:
    errors: list[str] = []
    chrome = ROOT / "templates/partials/rmc_platform_chrome_styles.html"
    text = chrome.read_text(encoding="utf-8")
    if BEAUTIFY_PARTIAL not in text:
        errors.append(f"{chrome}: missing include of {BEAUTIFY_PARTIAL}")
    if BEAUTIFY_CSS not in text and BEAUTIFY_PARTIAL not in text:
        errors.append(f"{chrome}: missing {BEAUTIFY_CSS}")

    for rel in REQUIRED:
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"missing file: {rel}")
            continue
        body = path.read_text(encoding="utf-8")
        if BEAUTIFY_PARTIAL not in body and BEAUTIFY_CSS not in body:
            errors.append(f"{rel}: missing beautify partial or css link")

    for rel in CHROME_PARENTS:
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"missing file: {rel}")
            continue
        body = path.read_text(encoding="utf-8")
        if "rmc_platform_chrome_styles.html" not in body:
            errors.append(f"{rel}: must include rmc_platform_chrome_styles.html")

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1
    print("OK: platform shell beautify coverage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
