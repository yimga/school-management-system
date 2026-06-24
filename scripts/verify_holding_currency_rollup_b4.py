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
            "materialize_all_holding_currency_rollups",
        ):
            if sym not in body:
                errors.append(f"holding_rollup.py missing {sym}")
        ast.parse(body)

    beat = ROOT / "apps/billing/beat_schedule.py"
    if beat.is_file() and "holding-currency-rollup-daily" not in beat.read_text(
        encoding="utf-8"
    ):
        errors.append("billing beat_schedule missing holding-currency-rollup-daily")

    task = ROOT / "apps/billing/tasks_holding_rollup.py"
    if not task.is_file():
        errors.append("missing apps/billing/tasks_holding_rollup.py")

    operator_tpl = ROOT / "templates/schools/holding_currency_rollup_dashboard.html"
    if not operator_tpl.is_file():
        errors.append("missing holding_currency_rollup_dashboard template")
    elif "currency_buckets" not in operator_tpl.read_text(encoding="utf-8"):
        errors.append("holding_currency_rollup_dashboard missing currency_buckets")

    super_urls = (ROOT / "apps/schools/super_urls.py").read_text(encoding="utf-8")
    if "holding_currency_rollup_dashboard" not in super_urls:
        errors.append("super_urls missing holding_currency_rollup_dashboard route")

    parent_tpl = ROOT / "templates/schools/parent_tenant_dashboard.html"
    if parent_tpl.is_file():
        tpl = parent_tpl.read_text(encoding="utf-8")
        if "currency_buckets" not in tpl:
            errors.append("parent_tenant_dashboard missing currency_buckets UI")

    parent_view = ROOT / "apps/schools/parent_tenant_views.py"
    if parent_view.is_file():
        pv = parent_view.read_text(encoding="utf-8")
        if "materialize_holding_currency_rollups" not in pv:
            errors.append("parent_tenant_views missing holding rollup materialize")

    if errors:
        for err in errors:
            print(f"HOLDING_CURRENCY_ROLLUP_B4_FAIL: {err}")
        return 1

    print("HOLDING_CURRENCY_ROLLUP_B4_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
