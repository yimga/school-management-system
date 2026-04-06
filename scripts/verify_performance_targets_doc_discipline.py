#!/usr/bin/env python3
"""
§0.4 performance targets (N9/N10) — documentation discipline (no Django).

Ensures ``docs/NORTH_STAR_TRUST_AND_OPS.md`` keeps the operator contract that
links PERFORMANCE_BUDGETS.md, check_performance_budgets.py, strict env flags,
Lighthouse docs, and RUM. Does not run smoke requests.

Usage: python scripts/verify_performance_targets_doc_discipline.py [--base REPO_ROOT]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_ROOT

_REQUIRED = (
    "Performance targets (operator contract",
    "PERFORMANCE_BUDGETS.md",
    "check_performance_budgets.py",
    "PERF_BUDGET_STRICT",
    "PERF_BUDGET_STRICT_GATE_ROWS",
    "LHCI_CI_URLS.md",
    "RUM_HOOK.md",
    "verify_performance_targets_doc_discipline.py",
)


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify NORTH_STAR performance targets doc anchors (§0.4 N9/N10)."
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
        print(f"verify_performance_targets_doc_discipline: {exc}", file=sys.stderr)
        return 1

    north_star = root / "docs" / "NORTH_STAR_TRUST_AND_OPS.md"
    errors: list[str] = []
    if not north_star.is_file():
        errors.append(f"Missing {north_star.relative_to(root)}")
        return _fail(errors)

    text = north_star.read_text(encoding="utf-8", errors="replace")
    for needle in _REQUIRED:
        if needle not in text:
            errors.append(
                f"{north_star.relative_to(root)} missing performance anchor: {needle!r}"
            )

    if errors:
        return _fail(errors)

    print(
        "verify_performance_targets_doc_discipline: PASS "
        f"({north_star.relative_to(root)} N9/N10 contract OK)"
    )
    return 0


def _fail(errors: list[str]) -> int:
    print("verify_performance_targets_doc_discipline: FAIL", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(None))
