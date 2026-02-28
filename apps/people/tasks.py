"""
Celery tasks for people app (e.g. Plan XI: certification/badge expiry alerts).
"""
from __future__ import annotations

import logging
from django.core.management import call_command

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="people.check_badge_expiry_alerts")
def check_badge_expiry_alerts_task(self, days: int = 60) -> dict:
    """
    Plan XI: Create notifications for badges/certifications expiring within N days.
    Run daily via Celery Beat. Delegates to management command check_badge_expiry_alerts.
    """
    try:
        call_command("check_badge_expiry_alerts", days=days)
        return {"ok": True, "days": days}
    except Exception as e:
        logger.exception("check_badge_expiry_alerts failed: %s", e)
        raise
