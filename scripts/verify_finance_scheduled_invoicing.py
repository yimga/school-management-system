#!/usr/bin/env python3
"""Verifier for B1 timezone-aware scheduled fee invoicing."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    mod = ROOT / "apps/finance/scheduled_invoicing.py"
    if not mod.is_file():
        errors.append("missing apps/finance/scheduled_invoicing.py")
    else:
        tree = ast.parse(mod.read_text(encoding="utf-8"))
        names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        for fn in (
            "is_invoice_generation_due_for_school",
            "is_local_billing_window",
            "billing_period_key",
            "monthly_invoice_already_run",
        ):
            if fn not in names:
                errors.append(f"scheduled_invoicing missing {fn}")

    tasks = (ROOT / "apps/finance/tasks.py").read_text(encoding="utf-8")
    if "scheduled_invoicing" not in tasks:
        errors.append("finance/tasks.py does not import scheduled_invoicing")
    if "billing_period" not in tasks:
        errors.append("finance/tasks.py missing billing_period idempotency")

    settings = (ROOT / "config/settings.py").read_text(encoding="utf-8")
    if '"auto-generate-fee-invoices"' not in settings:
        errors.append("CELERY_BEAT missing auto-generate-fee-invoices")
    elif "86400.0" in settings.split('"auto-generate-fee-invoices"')[1].split("},")[0]:
        errors.append("auto-generate-fee-invoices still daily-only (expected hourly)")

    tests = ROOT / "apps/finance/tests/test_scheduled_invoicing.py"
    if not tests.is_file():
        errors.append("missing apps/finance/tests/test_scheduled_invoicing.py")

    if errors:
        for err in errors:
            print(f"FINANCE_SCHEDULED_INVOICING_FAIL: {err}")
        return 1

    print("FINANCE_SCHEDULED_INVOICING_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
