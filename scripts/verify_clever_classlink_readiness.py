#!/usr/bin/env python3
"""Verify Clever/ClassLink integration readiness that is controllable in-repo.

Run (from repo root):
  python scripts/verify_clever_classlink_readiness.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = DEFAULT_ROOT

REQUIRED_FILES = [
    "apps/interop/clever_classlink_client.py",
    "apps/interop/tests/test_clever_classlink_client.py",
    "docs/interop/CLEVER_CLASSLINK_PARTNERSHIP.md",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default=str(DEFAULT_ROOT),
        help="Repository root to inspect (default: directory containing this script's parent).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"Base path is not a directory: {base}")
    return base


def _configure_root(base: Path) -> None:
    global ROOT
    ROOT = base


def check_required_files() -> list[str]:
    missing: list[str] = []
    for rel in REQUIRED_FILES:
        if not (ROOT / rel).exists():
            missing.append(rel)
    return missing


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _configure_root(_resolve_base(args.base))
    missing = check_required_files()
    if missing:
        print("CLEVER/CLASSLINK READINESS: FAIL")
        for rel in missing:
            print(f" - missing required file: {rel}")
        return 1
    print("CLEVER/CLASSLINK READINESS: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
