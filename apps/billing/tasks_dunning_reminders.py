"""Delinquency dunning-reminder ladder — Celery task + scheduled entry point.

``apps.billing.dunning_reminders.run_subscription_dunning_reminders`` publishes
``tenant.subscription.past_due`` (which the email matrix turns into the escalating
tenant-admin dunning email) for every delinquent subscription, advancing one rung
per run and deduped per rung per delinquency episode. This task lets the beat
(``apps.billing.beat_schedule``) run that sweep daily instead of only by hand.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from celery import shared_task

    @shared_task(name="apps.billing.run_subscription_dunning_reminders")
    def run_subscription_dunning_reminders_task() -> dict:
        """Beat entry point — advance the dunning ladder for delinquent tenants."""
        from apps.billing.dunning_reminders import run_subscription_dunning_reminders

        summary = run_subscription_dunning_reminders()
        logger.info("subscription dunning reminders run: %s", summary)
        return summary

except ImportError:  # pragma: no cover - celery optional at import time
    run_subscription_dunning_reminders_task = None  # type: ignore[assignment]
