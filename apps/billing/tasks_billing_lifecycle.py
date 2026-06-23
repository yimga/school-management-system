"""Platform billing lifecycle — Celery task + scheduled entry point.

The billing FSM (``apps.billing.services.run_platform_billing_lifecycle``)
converts expired trials, raises renewal charges when a billing period ends, ages
past-due subscriptions, and suspends/restores accounts. It already evaluates
due-ness **per subscription** (``current_period_end <= as_of``), so a single
daily beat invoices every tenant exactly when its own cycle rolls over — no
per-tenant cron is needed.

Previously this only advanced when an operator manually ran the management
command; the beat (``apps.billing.beat_schedule``) makes it autonomous.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from celery import shared_task

    @shared_task(name="apps.billing.run_platform_billing_lifecycle")
    def run_platform_billing_lifecycle_task(
        *, grace_days: int = 7, suspension_days: int = 30
    ) -> dict:
        """Beat entry point — advance every active subscription's billing state."""
        from apps.billing.services import run_platform_billing_lifecycle

        summary = run_platform_billing_lifecycle(
            grace_days=grace_days, suspension_days=suspension_days
        )
        logger.info("platform billing lifecycle run: %s", summary)
        return summary

except ImportError:  # pragma: no cover - celery optional at import time
    run_platform_billing_lifecycle_task = None  # type: ignore[assignment]
