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
    # Engine room: smoke-test active model pointer after pull (no second pull).
    if os.getenv("AI_ENGINE_ROOM_SUPPORT", "1").strip().lower() in ("1", "true", "yes"):
        try:
            call_command("engine_room_sync_ollama", "--no-pull", stdout=out, stderr=err)
        except Exception:
            pass
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


def _parse_bounded_int_env(
    name: str, default: int, *, min_v: int, max_v: int
) -> int:
    """Parse integer platform env; non-numeric or empty falls back to default (release readiness bucket C)."""
    raw = (os.getenv(name) or "").strip()
    if not raw:
        v = default
    else:
        try:
            v = int(raw)
        except (TypeError, ValueError):
            v = default
    return max(min_v, min(max_v, v))


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

    lookback_hours = _parse_bounded_int_env(
        "AUTOMATION_FAILURE_TREND_LOOKBACK_HOURS",
        24,
        min_v=1,
        max_v=168,
    )
    max_failures = _parse_bounded_int_env(
        "AUTOMATION_FAILURE_TREND_MAX_FAILURES",
        10,
        min_v=0,
        max_v=1000,
    )
    since = timezone.now() - timedelta(hours=lookback_hours)
    # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
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


@shared_task(name="platform_runtime.deliver_event_webhook")
def deliver_event_webhook_task(delivery_id: int) -> dict:
    """
    HTTP POST for :class:`~apps.platform_runtime.models.EventWebhookDelivery` (retries + DLQ in event_bus).
    """
    from apps.platform_runtime.event_bus import deliver_webhook_attempt

    return deliver_webhook_attempt(int(delivery_id))


@shared_task(name="platform_runtime.sweep_event_webhook_deliveries")
def sweep_event_webhook_deliveries_task(limit: int = 50) -> int:
    """Beat-discoverable safety sweep for stale webhook deliveries."""
    from apps.platform_runtime.event_bus import sweep_stale_webhook_deliveries

    return sweep_stale_webhook_deliveries(limit=limit)


@shared_task(name="platform_runtime.process_offline_queues_due")
def process_offline_queues_due(
    *,
    limit_per_school: int = 25,
    school_limit: int = 50,
) -> dict:
    """
    Drain QUEUED OfflineAction rows per tenant (rural / background_retry LCA pack).

    Complements browser SW replay; does not replace manual sync center UX.
    """
    from apps.platform_runtime.models import OfflineAction
    from apps.platform_runtime.offline_queue import process_offline_queue

    school_ids = list(
        OfflineAction.objects.filter(status=OfflineAction.Status.QUEUED)  # tenant-isolation-allow: offline-queue-celery-distinct-school-ids
        .values_list("school_id", flat=True)
        .distinct()[:school_limit]
    )
    totals = {"schools": 0, "synced": 0, "failed": 0, "conflicts": 0, "processed": 0}
    for school_id in school_ids:
        if school_id is None:
            continue
        summary = process_offline_queue(
            school_id=school_id,
            limit=limit_per_school,
        )
        totals["schools"] += 1
        totals["synced"] += int(summary.get("synced") or 0)
        totals["failed"] += int(summary.get("failed") or 0)
        totals["conflicts"] += int(summary.get("conflicts") or 0)
        totals["processed"] += int(summary.get("processed") or 0)
    return totals



@shared_task(name="platform_runtime.tenant_reactivation_sweep")
def tenant_reactivation_sweep_task() -> dict:
    """v4.00.98 Phase 4 — daily reactivation sweep entrypoint for Celery beat.

    Mirrors `manage.py run_tenant_reactivation_sweep --apply`. Never raises;
    captures the engine summary so beat can record the outcome.
    """
    try:
        from apps.platform_runtime.reactivation_engine import run_reactivation_sweep

        return run_reactivation_sweep(dry_run=False, limit_per_cadence=200)
    except Exception as exc:
        return {"ok": False, "reason": f"exception:{type(exc).__name__}"}


@shared_task(name="platform_runtime.signup_verification_stale_sweep")
def signup_verification_stale_sweep_task() -> dict:
    """v4.00.98 Phase 5 — fire operator alert + tenant reminder when a
    signup verification email has been unclicked for >24h. Best-effort."""
    try:
        from datetime import timedelta as _td
        from django.utils import timezone as _tz

        from apps.schools.models import SignupVerification
        from apps.platform_runtime.event_bus import publish_event

        cutoff_old = _tz.now() - _td(hours=24)
        cutoff_max = _tz.now() - _td(days=7)
        # tenant-isolation-allow: platform-signup-stale-sweep-no-tenant-scope
        rows = list(
            SignupVerification.objects.filter(
                verified_at__isnull=True,
                created_at__lt=cutoff_old,
                created_at__gte=cutoff_max,
            ).select_related("school")[:500]
        )
        fired = 0
        for v in rows:
            try:
                school = getattr(v, "school", None)
                age_hours = int((_tz.now() - v.created_at).total_seconds() / 3600)  # magic-number-allow: seconds-per-hour-divisor
                payload = {
                    "school_id": str(getattr(school, "pk", "")),
                    "school_name": getattr(school, "name", ""),
                    "admin_email": v.email,
                    "age_hours": age_hours,
                    "created_at": v.created_at.isoformat(),
                }
                publish_event(
                    "tenant.signup.verification_stale",
                    payload,
                    school_id=str(getattr(school, "pk", "")),
                    strict_catalog=True,
                    source="platform_runtime.signup_verification_stale_sweep",
                )
                fired += 1
            except Exception:
                continue
        return {"ok": True, "fired": fired, "scanned": len(rows)}
    except Exception as exc:
        return {"ok": False, "reason": f"exception:{type(exc).__name__}"}


@shared_task(name="platform_runtime.workflow_stuck_alert_sweep")
def workflow_stuck_alert_sweep_task() -> dict:
    """v4.00.98 Phase 6 — find RUNNING WorkflowRun rows past their expected
    heartbeat window and publish workflow.run.stuck. Cool-down handled by
    the email matrix (60 min per (event_type, recipient))."""
    try:
        from datetime import timedelta as _td
        from django.utils import timezone as _tz

        from apps.platform_runtime.models import WorkflowRun
        from apps.platform_runtime.event_bus import publish_event

        now = _tz.now()
        # Scan only rows where status=running AND last_heartbeat is at least
        # 1.5 × the smallest reasonable expected duration ago.
        candidates = list(
            # tenant-isolation-allow: platform-workflow-stuck-no-tenant-scope
            WorkflowRun.objects.filter(
                status="running",
                last_heartbeat_at__lt=now - _td(seconds=30),
            ).order_by("-last_heartbeat_at")[:500]
        )
        published = 0
        for run in candidates:
            try:
                expected = max(int(run.expected_duration_seconds or 30), 5)
                threshold = _td(seconds=expected * 1.5)
                if (now - run.last_heartbeat_at) <= threshold:
                    continue
                publish_event(
                    "workflow.run.stuck",
                    {
                        "run_id": run.pk,
                        "workflow_key": run.workflow_key,
                        "workflow_label": run.workflow_label,
                        "tenant_schema": run.tenant_schema,
                        "current_step_name": run.current_step_name,
                        "current_step_ordinal": run.current_step_ordinal,
                        "total_steps": run.total_steps,
                        "started_at": run.started_at.isoformat() if run.started_at else "",
                        "last_heartbeat_at": run.last_heartbeat_at.isoformat() if run.last_heartbeat_at else "",
                        "expected_duration_seconds": expected,
                    },
                    strict_catalog=True,
                    source="platform_runtime.workflow_stuck_alert_sweep",
                )
                # Flip the row so the SSE chip reflects stuck visually.
                # tenant-isolation-allow: workflow-stuck-sweep-single-row-pk-update-system-beat
                WorkflowRun.objects.filter(pk=run.pk).update(status="stuck")
                published += 1
            except Exception:
                continue
        return {"ok": True, "scanned": len(candidates), "published": published}
    except Exception as exc:
        return {"ok": False, "reason": f"exception:{type(exc).__name__}"}


@shared_task(name="platform_runtime.workflow_sla_breach_alert_sweep")
def workflow_sla_breach_alert_sweep_task() -> dict:
    """Scan RUNNING workflows past registry ``slo_seconds``; record breach + notify once."""

    try:
        from apps.platform_runtime.models import WorkflowRun
        from apps.platform_runtime.workflow_sla import record_running_sla_breach_if_needed

        candidates = list(
            # tenant-isolation-allow: platform-workflow-sla-sweep-no-tenant-scope
            WorkflowRun.objects.filter(status="running").order_by("-started_at")[:500]
        )
        recorded = 0
        for run in candidates:
            try:
                if record_running_sla_breach_if_needed(run=run):
                    recorded += 1
            except Exception:
                continue
        return {"ok": True, "scanned": len(candidates), "recorded": recorded}
    except Exception as exc:
        return {"ok": False, "reason": f"exception:{type(exc).__name__}"}
