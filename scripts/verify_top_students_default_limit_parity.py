#!/usr/bin/env python3
"""Siteconfig slice (1267): top_students_default_limit first-class on RuntimeDefaults."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELD = "top_students_default_limit"


def main() -> int:
    errors: list[str] = []
    fc = (ROOT / "apps/platform_runtime/runtime_defaults_first_class.py").read_text(
        encoding="utf-8"
    )
    if FIELD not in fc:
        errors.append(f"{FIELD} missing from runtime_defaults_first_class.py")
    models = (ROOT / "apps/platform_runtime/models.py").read_text(encoding="utf-8")
    if f"{FIELD} = models." not in models:
        errors.append(f"{FIELD} missing as RuntimeDefaults column")
    if errors:
        for e in errors:
            print(f"verify_top_students_default_limit_parity: {e}", file=sys.stderr)
        return 1
    print("verify_top_students_default_limit_parity: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
