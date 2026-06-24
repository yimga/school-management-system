#!/usr/bin/env python3
"""Verify B4 holding-company multi-currency rollup (batch 1708)."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    required = (
        ROOT / "apps/billing/holding_rollup.py",
        ROOT / "apps/billing/tests/test_holding_currency_rollup.py",
        ROOT / "apps/siteconfig/migrations/0202_b2_sku_overrides_b4_holding_rollup.py",
    )
    for path in required:
        if not path.is_file():
            errors.append(f"missing {path.relative_to(ROOT)}")

    catalog = ROOT / "apps/siteconfig/models_platform_catalog.py"
    if catalog.is_file():
        text = catalog.read_text(encoding="utf-8")
        if "class HoldingCurrencyRollup" not in text:
            errors.append("models_platform_catalog missing HoldingCurrencyRollup")

    rollup = ROOT / "apps/billing/holding_rollup.py"
    if rollup.is_file():
        body = rollup.read_text(encoding="utf-8")
        for sym in (
            "compute_holding_currency_totals",
            "materialize_holding_currency_rollups",
        ):
            if sym not in body:
                errors.append(f"holding_rollup.py missing {sym}")
        ast.parse(body)

    if errors:
        for err in errors:
            print(f"HOLDING_CURRENCY_ROLLUP_B4_FAIL: {err}")
        return 1

    print("HOLDING_CURRENCY_ROLLUP_B4_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
