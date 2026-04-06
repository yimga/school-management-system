#!/usr/bin/env python3
"""
Ensure docs/RUNMYCAMPUS_45_WEDGE_SCORECARD.md lists wedges 1–45 exactly once each.

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Project root (parent of scripts/); may be overridden per-run via ``_configure_root``.
ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT
DOC = REPO / "docs" / "RUNMYCAMPUS_45_WEDGE_SCORECARD.md"

# Table data rows: | ID | ... (ID 1–45 only, not "23–30" prose)
ROW_RE = re.compile(r"^\|\s*(\d{1,2})\s*\|")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify the 45 wedge scorecard document."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root to inspect (default: this repository root).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"Base path is not a directory: {base}")
    return base


def _configure_root(base: Path) -> None:
    global REPO, DOC
    REPO = base
    DOC = REPO / "docs" / "RUNMYCAMPUS_45_WEDGE_SCORECARD.md"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        _configure_root(_resolve_base(args.base))
    except ValueError as exc:
        print(f"verify_45_wedge_scorecard: {exc}", file=sys.stderr)
        return 1

    if not DOC.is_file():
        print(f"verify_45_wedge_scorecard: missing {DOC}", file=sys.stderr)
        return 1
    text = DOC.read_text(encoding="utf-8", errors="replace")
    found: list[int] = []
    for line in text.splitlines():
        m = ROW_RE.match(line.strip())
        if not m:
            continue
        n = int(m.group(1))
        if 1 <= n <= 45:
            found.append(n)

    counts: dict[int, int] = {}
    for n in found:
        counts[n] = counts.get(n, 0) + 1

    missing = [i for i in range(1, 46) if counts.get(i, 0) == 0]
    dupes = [i for i in range(1, 46) if counts.get(i, 0) > 1]

    errors: list[str] = []
    if missing:
        errors.append(f"Missing wedge IDs (no table row): {missing}")
    if dupes:
        errors.append(f"Duplicate wedge rows: {dupes} (counts: { {d: counts[d] for d in dupes} })")

    if errors:
        print("verify_45_wedge_scorecard FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("verify_45_wedge_scorecard: PASS (45 wedge rows, unique IDs 1–45)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
