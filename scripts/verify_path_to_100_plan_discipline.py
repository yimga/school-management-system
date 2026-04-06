#!/usr/bin/env python3
"""
Per-app depth gate: PATH_TO_100 plan stays aligned with SOT §6 spine (no §12 reopen).

Ensures ``docs/PATH_TO_100_PERCENT_EXECUTION_PLAN.md`` exists, references the SOT,
keeps Phase III §6.1–§6.24 headings, and preserves the discipline that §12 remains
the engineering gate (PATH is slice depth only).

Usage: python scripts/verify_path_to_100_plan_discipline.py [--base REPO_ROOT]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_ROOT

_MIN_CHARS = 8000

_REQUIRED_SNIPPETS = (
    "RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md",
    "§11.2",
    "## Phase III — App-by-app (§6.1–6.24)",
    "§6.1–6.24",
    "§12",
    "N/A_BLOCKERS_AND_RESOLUTION.md",
)


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def _section_headers() -> tuple[str, ...]:
    return tuple(f"### §6.{n} " for n in range(1, 25))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify PATH_TO_100 plan discipline vs SOT §6 spine."
    )
    parser.add_argument(
        "--base",
        default=str(DEFAULT_ROOT),
        help="Repository root (default: directory containing this script's parent).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"verify_path_to_100_plan_discipline: {exc}", file=sys.stderr)
        return 1

    plan = root / "docs" / "PATH_TO_100_PERCENT_EXECUTION_PLAN.md"
    errors: list[str] = []
    if not plan.is_file():
        print("verify_path_to_100_plan_discipline: FAIL", file=sys.stderr)
        print(f"  - Missing {plan.relative_to(root)}", file=sys.stderr)
        return 1

    text = plan.read_text(encoding="utf-8", errors="replace")
    if len(text.strip()) < _MIN_CHARS:
        errors.append(
            f"{plan.relative_to(root)} too short ({len(text)} chars < {_MIN_CHARS}); "
            "likely truncated"
        )
    for needle in _REQUIRED_SNIPPETS:
        if needle not in text:
            errors.append(f"{plan.relative_to(root)} missing required snippet: {needle!r}")
    for heading in _section_headers():
        if heading not in text:
            errors.append(
                f"{plan.relative_to(root)} missing per-app section heading: {heading!r}"
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
    raise SystemExit(main(None))
