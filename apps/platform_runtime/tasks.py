"""
Celery tasks for platform_runtime (beat-discovered via autodiscover_tasks).
"""

from __future__ import annotations

import os
from io import StringIO

from celery import shared_task
from django.core.management import call_command
from django.utils import timezone

from apps.platform_runtime.backlog_unlock_engine import normalize_profile


@shared_task(name="platform_runtime.sync_ollama_models_beat")
def sync_ollama_models_beat() -> str:
    """
    Weekly (when ENABLE_OLLAMA_MODEL_SYNC_BEAT=1): guarded `ollama pull` for env + optional registry.

    See docs/OLLAMA_OPERATIONS_AND_UPDATES.md.
    """
    out = StringIO()
    err = StringIO()
    include_registry = os.getenv("OLLAMA_SYNC_INCLUDE_REGISTRY", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if include_registry:
        call_command("sync_ollama_models", "--include-registry", stdout=out, stderr=err)
    else:
        call_command("sync_ollama_models", "--no-registry", stdout=out, stderr=err)
    return (out.getvalue() + err.getvalue())[-4000:]


@shared_task(name="platform_runtime.backlog_unlock_eval_and_cache")
def backlog_unlock_eval_and_cache() -> str:
    """
    Daily (when ENABLE_BACKLOG_UNLOCK_BEAT=1): refresh cache + emit backlog_dependency_met on transitions.

    Set BACKLOG_UNLOCK_PROFILE=smoke for a fast tick; default full matrix.
    """
    out = StringIO()
    err = StringIO()
    prof = normalize_profile(os.getenv("BACKLOG_UNLOCK_PROFILE", "full"))
    strict = os.getenv("BACKLOG_UNLOCK_FAIL_ON_SLA_BREACH", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    call_command(
        "evaluate_backlog_unlocks",
        profile=prof,
        update_cache=True,
        emit_events=True,
        fail_on_sla_breach=strict,
        timeout=600,
        stdout=out,
        stderr=err,
    )
    return (out.getvalue() + err.getvalue())[-4000:]


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes")


def _ensure_db_connection() -> None:
    from django.db import connection

    connection.ensure_connection()


@shared_task(name="platform_runtime.operator_visibility_heartbeat")
def operator_visibility_heartbeat() -> str:
    """
    Opt-in daily beat (ENABLE_OPERATOR_VISIBILITY_HEARTBEAT_BEAT=1): write AutomationExecutionLog
    so operators can confirm Celery + DB path from platform admin.
    """
    if not _env_truthy("ENABLE_OPERATOR_VISIBILITY_HEARTBEAT_BEAT"):
        return "skipped"
    from apps.automation.models import AutomationExecutionLog

    log = AutomationExecutionLog.objects.create(
        task_name="platform.operator_visibility_heartbeat",
        execution_type=AutomationExecutionLog.ExecutionType.SCHEDULED,
        status=AutomationExecutionLog.Status.PENDING,
    )
    log.mark_completed(
        AutomationExecutionLog.Status.SUCCESS,
        records_processed=1,
        summary={"ok": True, "ts": timezone.now().isoformat()},
    )
    return "ok"


@shared_task(name="platform_runtime.database_connectivity_heartbeat")
def database_connectivity_heartbeat() -> str:
    """
    Opt-in daily beat (ENABLE_DATABASE_CONNECTIVITY_HEARTBEAT_BEAT=1): ensure_connection + log outcome.
    """
    if not _env_truthy("ENABLE_DATABASE_CONNECTIVITY_HEARTBEAT_BEAT"):
        return "skipped"
    from apps.automation.models import AutomationExecutionLog

    log = AutomationExecutionLog.objects.create(
        task_name="platform.database_connectivity_heartbeat",
        execution_type=AutomationExecutionLog.ExecutionType.SCHEDULED,
        status=AutomationExecutionLog.Status.PENDING,
    )
    try:
        _ensure_db_connection()
    except Exception as e:
        log.mark_completed(
            AutomationExecutionLog.Status.FAILED,
            error_message=str(e)[:2000],
            summary={"ok": False, "error": str(e)[:500]},
        )
        return f"failed: {e}"
    log.mark_completed(
        AutomationExecutionLog.Status.SUCCESS,
        records_processed=1,
        summary={"ok": True, "ts": timezone.now().isoformat()},
    )
    return "ok"


@shared_task(name="platform_runtime.automation_failure_trend_signal")
def automation_failure_trend_signal() -> str:
    """
    Opt-in daily beat (ENABLE_AUTOMATION_FAILURE_TREND_BEAT=1): summarize failure trend and
    write an operator-visible signal log.
    """
    if not _env_truthy("ENABLE_AUTOMATION_FAILURE_TREND_BEAT"):
        return "skipped"
    from datetime import timedelta

    from apps.automation.models import AutomationExecutionLog

    lookback_hours = int(os.getenv("AUTOMATION_FAILURE_TREND_LOOKBACK_HOURS", "24") or "24")
    max_failures = int(os.getenv("AUTOMATION_FAILURE_TREND_MAX_FAILURES", "10") or "10")
    lookback_hours = max(1, min(168, lookback_hours))
    max_failures = max(0, min(1000, max_failures))
    since = timezone.now() - timedelta(hours=lookback_hours)
    recent = AutomationExecutionLog.objects.filter(started_at__gte=since)
    failure_count = recent.filter(status=AutomationExecutionLog.Status.FAILED).count()
    partial_count = recent.filter(status=AutomationExecutionLog.Status.PARTIAL).count()
    run_count = recent.count()
    breached = failure_count > max_failures
    status = (
        AutomationExecutionLog.Status.FAILED
        if breached
        else AutomationExecutionLog.Status.SUCCESS
    )
    log = AutomationExecutionLog.objects.create(
        task_name="platform.automation_failure_trend_signal",
        execution_type=AutomationExecutionLog.ExecutionType.SCHEDULED,
        status=AutomationExecutionLog.Status.PENDING,
    )
    log.mark_completed(
        status,
        records_processed=run_count,
        records_failed=failure_count,
        summary={
            "ok": not breached,
            "lookback_hours": lookback_hours,
            "max_failures": max_failures,
            "failure_count": failure_count,
            "partial_count": partial_count,
            "breached": breached,
            "ts": timezone.now().isoformat(),
        },
        error_message=(
            f"Failure trend breached: {failure_count} > {max_failures}"
            if breached
            else ""
        ),
    )
    return "failed" if breached else "ok"
