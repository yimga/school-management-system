"""
Celery tasks for automation / migration cloud (§0.1.5 scheduled parity & exception visibility).
"""

from datetime import timedelta

from celery import shared_task
from django.utils import timezone


@shared_task(name="automation.migration_scheduled_parity_tick")
def migration_scheduled_parity_tick():
    """
    Daily tick: record open migration exceptions + quarantine depth for ops dashboards.
    Full CSV diff vs source remains operator/BR-API driven; this task provides scheduled
    telemetry and audit log (AutomationExecutionLog).
    """
    from apps.automation.models import (
        AutomationExecutionLog,
        MigrationQuarantineRecord,
        MigrationRun,
    )

    # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
    open_runs = MigrationRun.objects.filter(
        exception_ack_status=MigrationRun.ExceptionAck.OPEN
    # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
    ).count()
    pending_q = MigrationQuarantineRecord.objects.filter(
        # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
        status=MigrationQuarantineRecord.Status.PENDING
    ).count()
    # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
    runs_7d = MigrationRun.objects.filter(
        started_at__gte=timezone.now() - timedelta(days=7)
    ).count()
    AutomationExecutionLog.objects.create(
        task_name="migration.scheduled_parity_tick",
        execution_type=AutomationExecutionLog.ExecutionType.SCHEDULED,
        status=AutomationExecutionLog.Status.SUCCESS,
        records_processed=runs_7d,
        records_failed=open_runs + pending_q,
        execution_summary={
            "open_exception_runs": open_runs,
            "pending_quarantine_rows": pending_q,
            "migration_runs_last_7d": runs_7d,
        },
    )
    return {
        "open_exception_runs": open_runs,
        "pending_quarantine_rows": pending_q,
        "migration_runs_last_7d": runs_7d,
    }
