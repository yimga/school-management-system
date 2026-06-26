"""Celery tasks for tenant immutable DR snapshots."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="lifecycle.capture_tenant_immutable_snapshots_daily", ignore_result=True)
def capture_tenant_immutable_snapshots_daily() -> int:
    from apps.lifecycle.tenant_dr_snapshot import capture_daily_snapshot
    from apps.schools.models import School

    count = 0
    for school in School.objects.filter(is_active=True, deleted_at__isnull=True).iterator():
        try:
            capture_daily_snapshot(school)
            count += 1
        except Exception:
            logger.warning(
                "tenant_dr_snapshot.capture_failed school_id=%s",
                getattr(school, "pk", "?"),
                exc_info=True,
            )
    return count
