#!/usr/bin/env python3
"""Verify B1 timezone-aware scheduled fee invoicing is wired end-to-end."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    module = ROOT / "apps/finance/scheduled_invoicing.py"
    tasks = ROOT / "apps/finance/tasks.py"
    settings = ROOT / "config/settings.py"
    tests = ROOT / "apps/finance/tests/test_scheduled_invoicing.py"

    for path in (module, tasks, settings, tests):
        if not path.is_file():
            errors.append(f"missing {path.relative_to(ROOT)}")

    tasks_text = tasks.read_text(encoding="utf-8")
    if "is_invoice_generation_due_for_school" not in tasks_text:
        errors.append("finance/tasks.py does not call is_invoice_generation_due_for_school")

    settings_text = settings.read_text(encoding="utf-8")
    if '"auto-generate-fee-invoices"' not in settings_text:
        errors.append("CELERY_BEAT missing auto-generate-fee-invoices")
    elif "3600.0" not in settings_text.split("auto-generate-fee-invoices", 1)[1][:200]:
        errors.append("auto-generate-fee-invoices beat should be hourly (3600.0)")

    for py in (module, tasks):
        ast.parse(py.read_text(encoding="utf-8"))

    if errors:
        for err in errors:
            print(f"SCHEDULED_INVOICING_B1_FAIL: {err}")
        return 1

    print("SCHEDULED_INVOICING_B1_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
