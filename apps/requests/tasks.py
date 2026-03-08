"""
Optional Celery task: remind assignees of pending AccessRequests.
Configure interval in Site Settings (requests_reminder_interval_hours); 0 = disabled.
"""
from __future__ import annotations

import logging
from django.utils import timezone

from celery import shared_task
from apps.automation.models import AutomationExecutionLog
from apps.platform_runtime.helpers import get_effective_site_settings

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="requests.remind_pending_assignees")
def remind_pending_assignees_task(self) -> dict:
    """
    Notify staff who are assigned to pending AccessRequests.
    Run on a schedule (e.g. daily); interval configurable via SiteSettings.requests_reminder_interval_hours.
    """
    from apps.finance.models import Notification
    from .models import AccessRequest

    execution_log = AutomationExecutionLog.objects.create(
        task_name="requests.remind_pending_assignees",
        execution_type=AutomationExecutionLog.ExecutionType.SCHEDULED,
        status=AutomationExecutionLog.Status.PENDING,
    )
    try:
        pending = AccessRequest.objects.filter(
            status=AccessRequest.Status.PENDING,
            assigned_to__isnull=False,
            assigned_to__is_active=True,
        ).select_related("assigned_to", "requester", "school")

        pending_enabled = []
        for req in pending:
            site = get_effective_site_settings(school=getattr(req, "school", None))
            interval_hours = getattr(site, "requests_reminder_interval_hours", 0) or 0
            if interval_hours > 0:
                pending_enabled.append(req)

        if not pending_enabled:
            result = {"notified": 0, "message": "Reminder disabled (interval 0)"}
            execution_log.mark_completed(
                AutomationExecutionLog.Status.SUCCESS,
                records_processed=0,
                summary=result,
            )
            return result

        by_assignee = {}
        for req in pending_enabled:
            uid = req.assigned_to_id
            if uid not in by_assignee:
                by_assignee[uid] = []
            by_assignee[uid].append(req)

        notified = 0
        for assignee_id, reqs in by_assignee.items():
            assignee = reqs[0].assigned_to
            count = len(reqs)
            try:
                Notification.objects.create(
                    recipient=assignee,
                    title="Pending access requests",
                    message=f"You have {count} pending access request(s) assigned to you. Please review in Requests.",
                    severity=Notification.Severity.INFO,
                    link="/requests/",
                )
                notified += 1
            except Exception as e:
                logger.warning("Failed to notify assignee %s: %s", assignee_id, e)

        result = {"notified": notified, "assignees": len(by_assignee), "pending_total": len(pending_enabled)}
        execution_log.mark_completed(
            AutomationExecutionLog.Status.SUCCESS,
            records_processed=notified,
            summary=result,
        )
        return result
    except Exception as e:
        logger.exception("remind_pending_assignees_task failed: %s", e)
        execution_log.mark_completed(
            AutomationExecutionLog.Status.FAILED,
            error_message=str(e),
        )
        raise
