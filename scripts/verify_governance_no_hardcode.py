#!/usr/bin/env python3
"""Ensure group governance features stay behind flags — no mandatory org membership."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCHOOLS_APP = REPO / "apps" / "schools"

# Patterns that would force group membership without configurability.
BANNED_PATTERNS = (
    re.compile(r"organization_id\s*=\s*models\.ForeignKey\([^)]*null=False"),
    re.compile(r"if\s+not\s+school\.organization\b"),
    re.compile(r"raise\s+.*must\s+belong\s+to\s+(an\s+)?org"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Governance no-hardcode verifier")
    parser.add_argument("--strict", action="store_true", help="Fail on any suspicious pattern")
    args = parser.parse_args()

    failures: list[str] = []
    if not SCHOOLS_APP.is_dir():
        print("FAIL: apps/schools missing", file=sys.stderr)
        return 1

    for path in SCHOOLS_APP.rglob("*.py"):
        if "migrations" in path.parts or "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in BANNED_PATTERNS:
            if pattern.search(text):
                rel = path.relative_to(REPO)
                failures.append(f"{rel}: matched mandatory-org pattern {pattern.pattern}")

    governance_app = REPO / "apps" / "governance"
    if not governance_app.is_dir() and args.strict:
        failures.append("apps/governance/ not present (Phase 2)")

    if failures:
        print("verify_governance_no_hardcode: FAIL", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print("verify_governance_no_hardcode: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
