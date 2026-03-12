#!/usr/bin/env python3
"""
Block runtime-visible Gilead residue in the active platform surface.

Historical references inside migrations, archived docs, and tests are allowed
until the data migration history is retired. Runtime-visible defaults, fixtures,
deployment config, and user-facing surfaces are not.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERN = re.compile(r"gilead", re.IGNORECASE)
SCAN_ROOTS = (
    ROOT / "apps",
    ROOT / "services",
    ROOT / "fixtures",
    ROOT / "templates",
    ROOT / "config",
)
SCAN_FILES = (
    ROOT / "render.yaml",
    ROOT / "QUICK_START.md",
)
SKIP_PARTS = {"migrations", "tests", "__pycache__", "docs", "tmp", "artifacts"}


def _safe_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _iter_candidate_files():
    for base in SCAN_ROOTS:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            yield path
    for path in SCAN_FILES:
        if path.exists():
            yield path


def main() -> int:
    violations: list[str] = []
    for path in sorted(set(_iter_candidate_files())):
        for line_no, line in enumerate(_safe_text(path).splitlines(), start=1):
            if PATTERN.search(line):
                rel = path.relative_to(ROOT).as_posix()
                violations.append(f"{rel}:{line_no}: {line.strip()}")
    if violations:
        print("lint_gilead_residue: runtime-visible Gilead residue detected:\n", file=sys.stderr)
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        return 1
    print("lint_gilead_residue: no runtime-visible Gilead residue found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
