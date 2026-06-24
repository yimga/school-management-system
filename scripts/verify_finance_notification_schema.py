#!/usr/bin/env python3
"""Gate: finance Notification retention columns + schema_repair heal (0071/0072)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main() -> int:
    findings: list[str] = []

    for rel in (
        "apps/finance/migrations/0071_notification_dismissed_at_notification_expires_at_and_more.py",
        "apps/finance/migrations/0072_ensure_finance_notification_columns.py",
        "apps/finance/schema_repair.py",
        "apps/finance/tests/test_finance_notification_schema_repair.py",
        "apps/accounts/tests/test_notification_inbox_retention.py",
    ):
        if not (REPO / rel).is_file():
            findings.append(f"missing {rel}")

    models = (REPO / "apps/finance/models.py").read_text(encoding="utf-8")
    for field in ("dismissed_at", "expires_at", "school = models.ForeignKey"):
        if field not in models:
            findings.append(f"finance.models.Notification missing {field}")

    repair = (REPO / "apps/finance/schema_repair.py").read_text(encoding="utf-8")
    if "ensure_finance_notification_columns" not in repair:
        findings.append("schema_repair missing ensure_finance_notification_columns")

    api = (REPO / "apps/api/notification_api.py").read_text(encoding="utf-8")
    for needle in ("dismissed_at__isnull=True", "expires_at__isnull=True"):
        if needle not in api:
            findings.append(f"notification_api.py missing filter {needle}")

    views = (REPO / "apps/accounts/views.py").read_text(encoding="utf-8")
    if "def notification_dismiss" not in views:
        findings.append("accounts.views missing notification_dismiss")
    if "_notification_inbox_queryset" not in views:
        findings.append("accounts.views missing _notification_inbox_queryset")

    if findings:
        print("verify_finance_notification_schema: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_finance_notification_schema: FINANCE_NOTIFICATION_SCHEMA_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
