#!/usr/bin/env python3
"""Tier-A platform pages must wire VISUAL-ENGINE viz or loop partials."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

TIER_A: dict[str, tuple[str, ...]] = {
    "type_platform_fees_payments.html": ("_platform_visual_engine_strip", "split_ledger_viz"),
    "type_platform_offline_first.html": ("_platform_visual_engine_strip", "transit_viz"),
    "type_platform_grading_report_cards.html": ("_platform_visual_engine_strip", "gradebook_viz"),
    "type_platform_admissions.html": (
        "_platform_visual_engine_strip",
        "_platform_loop_hero",
        "mkt-admissions-steps",
    ),
    "type_platform_security.html": ("_platform_visual_engine_strip", "transit_viz"),
    "type_pricing.html": ("_platform_visual_engine_strip", "split_ledger_viz"),
}


def main() -> int:
    errors: list[str] = []
    for rel, needles in TIER_A.items():
        path = REPO / "templates" / "marketing" / "pages" / rel
        if not path.is_file():
            errors.append(f"missing template: {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle not in text:
                errors.append(f"{rel} missing: {needle}")
    if errors:
        print("verify_marketing_platform_visual_wiring: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("verify_marketing_platform_visual_wiring: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
