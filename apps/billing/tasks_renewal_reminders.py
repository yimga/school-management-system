"""Renewal/expiry reminder — Celery task + scheduled entry point.

``apps.billing.renewal_reminders.run_subscription_renewal_reminders`` publishes
``tenant.subscription.expiring_soon`` (which the email matrix turns into the
admin reminder email) for every active subscription whose period end falls inside
the warning window, deduped per period. This task lets the beat
(``apps.billing.beat_schedule``) run that sweep daily instead of only by hand.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from celery import shared_task

    @shared_task(name="apps.billing.run_subscription_renewal_reminders")
    def run_subscription_renewal_reminders_task(*, warning_days: int | None = None) -> dict:
        """Beat entry point — publish renewal reminders for soon-to-renew subs."""
        from apps.billing.renewal_reminders import run_subscription_renewal_reminders

        summary = run_subscription_renewal_reminders(warning_days=warning_days)
        logger.info("subscription renewal reminders run: %s", summary)
        return summary

except ImportError:  # pragma: no cover - celery optional at import time
    run_subscription_renewal_reminders_task = None  # type: ignore[assignment]
