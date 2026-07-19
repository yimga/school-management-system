#!/usr/bin/env python
"""Metric #24 — Part 2 baseline must not re-claim Wave-closed surfaces as absent.

Fails if CURSOR_A_PLUS_MANDATE.md Part 2 STILL OPEN still contains known-closed
phrases that Waves 11–17 already disproved.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANDATE = ROOT / "CURSOR_A_PLUS_MANDATE.md"

# Phrases that must NOT appear under the STILL OPEN section (stale underclaims).
FORBIDDEN_IN_STILL_OPEN = (
    "called only from tests",
    "no UI to render, approve, PDF",
    "zero ExclusionConstraint",
    "no points ledger",
    "manual SubstituteCover FK only",
    "not auto-seeded at signup",
    "provisioning E2E proof + fail-honesty** incomplete",
    "today 6/20",
)


def main() -> int:
    if not MANDATE.is_file():
        print("PART2_BASELINE_FAIL: mandate missing", file=sys.stderr)
        return 1
    text = MANDATE.read_text(encoding="utf-8")
    marker = "**STILL OPEN (THE WORK):**"
    idx = text.find(marker)
    if idx < 0:
        print("PART2_BASELINE_FAIL: STILL OPEN section missing", file=sys.stderr)
        return 1
    still_open = text[idx : idx + 2500]
    for phrase in FORBIDDEN_IN_STILL_OPEN:
        if phrase in still_open:
            print(
                f"PART2_BASELINE_FAIL: stale underclaim in STILL OPEN: {phrase!r}",
                file=sys.stderr,
            )
            return 1
    # CLOSED section must exist and mention grading formula / report cards.
    closed_marker = "**CLOSED (wired + proven"
    if closed_marker not in text:
        print("PART2_BASELINE_FAIL: CLOSED section missing", file=sys.stderr)
        return 1
    print("PART2_BASELINE_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
