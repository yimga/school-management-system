#!/usr/bin/env python3
"""
Per-app depth gate: PATH_TO_100 plan stays aligned with SOT §6 spine (no §12 reopen).

Ensures ``docs/PATH_TO_100_PERCENT_EXECUTION_PLAN.md`` exists, references the SOT,
keeps Phase III §6.1–§6.24 headings, and preserves the discipline that §12 remains
the engineering gate (PATH is slice depth only).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "PATH_TO_100_PERCENT_EXECUTION_PLAN.md"

_MIN_CHARS = 8000

_REQUIRED_SNIPPETS = (
    "RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md",
    "§11.2",
    "## Phase III — App-by-app (§6.1–6.24)",
    "§6.1–6.24",
    "§12",
    "N/A_BLOCKERS_AND_RESOLUTION.md",
)


def _section_headers() -> tuple[str, ...]:
    return tuple(f"### §6.{n} " for n in range(1, 25))


def main() -> int:
    errors: list[str] = []
    if not PLAN.is_file():
        print("verify_path_to_100_plan_discipline: FAIL", file=sys.stderr)
        print(f"  - Missing {PLAN.relative_to(ROOT)}", file=sys.stderr)
        return 1

    text = PLAN.read_text(encoding="utf-8", errors="replace")
    if len(text.strip()) < _MIN_CHARS:
        errors.append(
            f"{PLAN.relative_to(ROOT)} too short ({len(text)} chars < {_MIN_CHARS}); "
            "likely truncated"
        )
    for needle in _REQUIRED_SNIPPETS:
        if needle not in text:
            errors.append(f"{PLAN.relative_to(ROOT)} missing required snippet: {needle!r}")
    for heading in _section_headers():
        if heading not in text:
            errors.append(
                f"{PLAN.relative_to(ROOT)} missing per-app section heading: {heading!r}"
            )

    if errors:
        print("verify_path_to_100_plan_discipline: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(
        "verify_path_to_100_plan_discipline: PASS "
        f"(Phase III sections 6.1-6.24 spine + SOT cross-links; {len(text)} chars)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
