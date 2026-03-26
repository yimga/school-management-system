#!/usr/bin/env python3
"""Verify Clever/ClassLink integration readiness that is controllable in-repo."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "apps/interop/clever_classlink_client.py",
    "apps/interop/tests/test_clever_classlink_client.py",
    "docs/interop/CLEVER_CLASSLINK_PARTNERSHIP.md",
]


def check_required_files() -> list[str]:
    missing: list[str] = []
    for rel in REQUIRED_FILES:
        if not (ROOT / rel).exists():
            missing.append(rel)
    return missing


def main() -> int:
    missing = check_required_files()
    if missing:
        print("CLEVER/CLASSLINK READINESS: FAIL")
        for rel in missing:
            print(f" - missing required file: {rel}")
        return 1
    print("CLEVER/CLASSLINK READINESS: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
