"""Pass 9.D: SLA-breach sweep for ExportJob + EraseRequest.

GDPR Art. 12(3) gives a one-month default response window; tenants can
shorten it via `due_at`. When that timer expires without a terminal
status, we stamp `sla_breach_at` so the data-rights queue can highlight
the row in red and SOC 2 auditors can sample against a single column.

The task is best-effort: a stamp is informational, not transactional —
failures log but never crash the beat worker.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from celery import shared_task
except ImportError:  # pragma: no cover - celery is installed in prod/test
    def shared_task(*dargs, **dkwargs):
        def _decorator(fn):
            return fn

        if dargs and callable(dargs[0]):
            return dargs[0]
        return _decorator


TERMINAL_EXPORT_STATUSES = {"completed", "failed"}
TERMINAL_ERASE_STATUSES = {"completed", "rejected"}


@shared_task(name="compliance.mark_sla_breaches")
def mark_sla_breaches() -> dict:
    """Stamp `sla_breach_at` on overdue Export + Erase rows."""
    from django.utils import timezone

    from apps.compliance.models import EraseRequest, ExportJob

    now = timezone.now()
    stamped = {"exports": 0, "erases": 0}

    # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
    overdue_exports = ExportJob.objects.filter(
        sla_breach_at__isnull=True,
        due_at__isnull=False,
        due_at__lt=now,
    ).exclude(status__in=list(TERMINAL_EXPORT_STATUSES))
    try:
        stamped["exports"] = overdue_exports.update(sla_breach_at=now)
    except Exception:  # noqa: BLE001 - never crash beat worker
        logger.exception("mark_sla_breaches: ExportJob update failed")
# tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep

    overdue_erases = EraseRequest.objects.filter(
        sla_breach_at__isnull=True,
        due_at__isnull=False,
        due_at__lt=now,
    ).exclude(status__in=list(TERMINAL_ERASE_STATUSES))
    try:
        stamped["erases"] = overdue_erases.update(sla_breach_at=now)
    except Exception:  # noqa: BLE001
        logger.exception("mark_sla_breaches: EraseRequest update failed")

    if stamped["exports"] or stamped["erases"]:
        logger.info(
            "mark_sla_breaches: stamped %s exports, %s erases",
            stamped["exports"],
            stamped["erases"],
        )
    return stamped
