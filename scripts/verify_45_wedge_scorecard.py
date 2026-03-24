#!/usr/bin/env python3
"""
Ensure docs/RUNMYCAMPUS_45_WEDGE_SCORECARD.md lists wedges 1–45 exactly once each.

Run from repo root: python scripts/verify_45_wedge_scorecard.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOC = REPO / "docs" / "RUNMYCAMPUS_45_WEDGE_SCORECARD.md"

# Table data rows: | ID | ... (ID 1–45 only, not "23–30" prose)
ROW_RE = re.compile(r"^\|\s*(\d{1,2})\s*\|")


def main() -> int:
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
    raise SystemExit(main())
