#!/usr/bin/env python3
"""
North star N21 — i18n: key tenant/manager templates must load i18n and use trans for user-facing strings.

Scans key base and high-traffic templates for {% load i18n %} and reports missing.
Use --strict to exit 1 when a required template lacks i18n load.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"

# Key templates that must have {% load i18n %} (or load i18n in parent they extend)
REQUIRED_I18N = [
    "base.html",
    "control_plane_skeleton.html",
    "control_plane_base.html",
    "portal_base.html",
    "backend_base.html",
    "accounts/backend_dashboard.html",
    "accounts/login.html",
    "errors/404.html",
    "errors/500.html",
]


def main() -> int:
    ap = argparse.ArgumentParser(description="North star N21: i18n in key templates")
    ap.add_argument(
        "--strict", action="store_true", help="Exit 1 when required template lacks i18n"
    )
    args = ap.parse_args()
    failures = []
    for name in REQUIRED_I18N:
        path = TEMPLATES / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "load i18n" not in text and "{% trans " not in text:
            failures.append(name + ": missing {% load i18n %} or trans (N21)")
    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        if args.strict:
            return 1
    if not failures:
        print("North star i18n lint: key templates have i18n.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
