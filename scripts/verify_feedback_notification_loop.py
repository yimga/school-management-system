#!/usr/bin/env python3
"""Batch 1519 — feedback notification loop gate."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _contains(rel: str, needle: str) -> bool:
    path = ROOT / rel
    return path.is_file() and needle in path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    failures: list[str] = []

    if not _contains("apps/feedback/signals.py", "_notify_operators_on_critical_feedback"):
        failures.append("signals missing critical feedback notifier")
    if not _contains("apps/feedback/signals.py", "notify_critical_feedback_submission"):
        failures.append("signals must call notify_critical_feedback_submission")
    if not _contains("apps/feedback/notification_services.py", "publish_event"):
        failures.append("notification_services must publish to event bus")
    if not _contains("apps/feedback/views.py", "Reference ticket #"):
        failures.append("views must surface GlobalSupportTicket id on confirm")
    if not _contains("apps/customersuccess/models.py", "FEEDBACK_CRITICAL"):
        failures.append("AutoTicketRule.FEEDBACK_CRITICAL trigger missing")
    if not _contains("apps/customersuccess/auto_ticket_runner.py", "evaluate_feedback_critical_rules"):
        failures.append("auto_ticket_runner missing evaluate_feedback_critical_rules")
    if not _contains("apps/siteconfig/views.py", "feedback:product_feedback"):
        failures.append("ProductFeedback legacy redirect to apps.feedback missing")

    if failures:
        for item in failures:
            print(f"FAIL: {item}", file=sys.stderr)
        return 1

    print("FEEDBACK_NOTIFICATION_LOOP_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
