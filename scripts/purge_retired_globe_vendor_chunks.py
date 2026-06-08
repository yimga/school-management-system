#!/usr/bin/env python3
"""Remove retired world-globe.vendor-* chunks from static/js/dist and staticfiles."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "world-globe.vendor-"


def _purge(directory: Path) -> list[str]:
    removed: list[str] = []
    if not directory.is_dir():
        return removed
    for path in directory.iterdir():
        if path.is_file() and path.name.startswith(PREFIX):
            path.unlink()
            removed.append(str(path.relative_to(ROOT)))
    return removed


def main() -> int:
    removed = _purge(ROOT / "static/js/dist") + _purge(ROOT / "staticfiles/js/dist")
    if removed:
        print("Removed retired globe vendor chunks:")
        for rel in removed:
            print(f"  - {rel}")
    else:
        print("No retired globe vendor chunks found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
