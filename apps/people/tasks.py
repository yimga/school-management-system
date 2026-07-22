"""
Celery tasks for people app (e.g. Plan XI: certification/badge expiry alerts).
Runs in tenant context (per school_id or all active schools).
"""

from __future__ import annotations

import logging
from django.core.management import call_command

from celery import shared_task
from apps.schools.celery_tasks import _run_with_tenant_context, get_active_school_ids

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="people.check_badge_expiry_alerts")
def check_badge_expiry_alerts_task(
    self, days: int = 60, school_id: str | None = None
) -> dict:
    """
    Plan XI: Create notifications for badges/certifications expiring within N days.
    Runs in tenant context (per school_id or all active schools).
    """

    def _run(d):
        call_command("check_badge_expiry_alerts", days=d)

    if school_id:
        _run_with_tenant_context(school_id=school_id, runnable=lambda: _run(days))
        return {"ok": True, "days": days}
    for sid in get_active_school_ids():
        _run_with_tenant_context(school_id=sid, runnable=lambda d=days: _run(d))
    return {"ok": True, "days": days}


@shared_task(name="people.continue_applying_transfers", ignore_result=False)
def continue_applying_transfers_task(*, limit: int = 20) -> dict:
    """Finish APPLYING transfer cases once Migration Cloud bundles land."""
    from apps.people.transfer_service import continue_applying_transfers

    return continue_applying_transfers(limit=limit)
