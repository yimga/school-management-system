#!/usr/bin/env python3
"""
§0.4 performance targets (N9/N10) — documentation discipline (no Django).

Ensures ``docs/NORTH_STAR_TRUST_AND_OPS.md`` keeps the operator contract that
links PERFORMANCE_BUDGETS.md, check_performance_budgets.py, strict env flags,
Lighthouse docs, and RUM. Does not run smoke requests.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NORTH_STAR = ROOT / "docs" / "NORTH_STAR_TRUST_AND_OPS.md"

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


def main() -> int:
    errors: list[str] = []
    if not NORTH_STAR.is_file():
        errors.append(f"Missing {NORTH_STAR.relative_to(ROOT)}")
        return _fail(errors)

    text = NORTH_STAR.read_text(encoding="utf-8", errors="replace")
    for needle in _REQUIRED:
        if needle not in text:
            errors.append(
                f"{NORTH_STAR.relative_to(ROOT)} missing performance anchor: {needle!r}"
            )

    if errors:
        return _fail(errors)

    print(
        "verify_performance_targets_doc_discipline: PASS "
        f"({NORTH_STAR.relative_to(ROOT)} N9/N10 contract OK)"
    )
    return 0


def _fail(errors: list[str]) -> int:
    print("verify_performance_targets_doc_discipline: FAIL", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
