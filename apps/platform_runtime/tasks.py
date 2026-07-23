"""
Celery tasks for platform_runtime (beat-discovered via autodiscover_tasks).
"""

from __future__ import annotations

import logging
import os
from io import StringIO

from celery import shared_task
from django.core.management import call_command
from django.utils import timezone

from apps.platform_runtime.backlog_unlock_engine import normalize_profile

logger = logging.getLogger(__name__)


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


def _env_enabled_default_on(name: str) -> bool:
    """Platform-health beats default ON; opt out with 0/false/no/off."""
    raw = os.getenv(name, "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("", "1", "true", "yes", "on"):
        return True
    # Unknown values: stay on (fail-open for monitoring, not payments).
    return True


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
    Default-on daily beat: write AutomationExecutionLog so operators can confirm
    Celery + DB path from platform admin. Opt out with ENABLE_*=0/false/no.
    """
    if not _env_enabled_default_on("ENABLE_OPERATOR_VISIBILITY_HEARTBEAT_BEAT"):
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
    Default-on daily beat: ensure_connection + log outcome.
    Opt out with ENABLE_DATABASE_CONNECTIVITY_HEARTBEAT_BEAT=0/false/no.
    """
    if not _env_enabled_default_on("ENABLE_DATABASE_CONNECTIVITY_HEARTBEAT_BEAT"):
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
    Default-on daily beat: summarize failure trend and write an operator-visible
    signal log. Opt out with ENABLE_AUTOMATION_FAILURE_TREND_BEAT=0/false/no.
    """
    if not _env_enabled_default_on("ENABLE_AUTOMATION_FAILURE_TREND_BEAT"):
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
        from django.db.models import F, Q
        from django.utils import timezone as _tz

        from apps.platform_runtime.models import WorkflowRun
        from apps.platform_runtime.event_bus import publish_event
        from apps.platform_runtime.workflow_fix_handlers import resolve_stuck_remediation
        from apps.platform_runtime.workflow_autopilot import try_auto_apply_on_stuck

        now = _tz.now()
        # Include missing heartbeats — a SIGKILL mid-tenant_schema never writes one.
        candidates = list(
            # tenant-isolation-allow: platform-workflow-stuck-no-tenant-scope
            WorkflowRun.objects.filter(status="running")
            .filter(
                Q(last_heartbeat_at__lt=now - _td(seconds=30))
                | Q(last_heartbeat_at__isnull=True)
            )
            .order_by(F("last_heartbeat_at").asc(nulls_first=True))[:500]
        )
        published = 0
        auto_applied = 0
        for run in candidates:
            try:
                expected = max(int(run.expected_duration_seconds or 30), 5)
                # Provisioning tenant_schema uses the watchdog staleness window
                # (~120s), not 1.5× expected (900s for a 600s migrate). Waiting
                # 15 minutes before flipping to stuck leaves operators on
                # "Running / Diagnostic only" while the schema step is already dead.
                if run.workflow_key == "tenant_school_provision":
                    try:
                        from apps.schools.provision_watchdog import (
                            provision_resume_stale_seconds,
                        )

                        threshold = _td(seconds=provision_resume_stale_seconds())
                    except Exception:
                        threshold = _td(seconds=expected * 1.5)
                else:
                    threshold = _td(seconds=expected * 1.5)
                if run.last_heartbeat_at and (now - run.last_heartbeat_at) <= threshold:
                    continue
                # No heartbeat at all on a provision run past the stale window
                # from started_at — also stuck.
                if run.last_heartbeat_at is None:
                    started = run.started_at or now
                    if (now - started) <= threshold:
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
                # Flip the row so the SSE chip reflects stuck visually AND stamp a
                # remediation card so the operator gets a one-click Retry + the
                # autopilot has a concrete target. Never clobber a richer (failure)
                # remediation that already carries an auto-fix.
                update_fields = {"status": "stuck"}
                if not (run.suggested_remediation or {}).get("auto_fix_available"):
                    update_fields["suggested_remediation"] = resolve_stuck_remediation(run=run)
                # tenant-isolation-allow: workflow-stuck-sweep-single-row-pk-update-system-beat
                WorkflowRun.objects.filter(pk=run.pk).update(**update_fields)
                published += 1
                # Safe-by-default unattended remediation: a no-op (shadow) unless a
                # WorkflowAutopilotPolicy explicitly enables the fix kind.
                try:
                    if try_auto_apply_on_stuck(run_pk=run.pk).get("applied"):
                        auto_applied += 1
                except Exception:
                    logger.debug("stuck_auto_apply_failed run_id=%s", run.pk, exc_info=True)
            except Exception:
                continue
        return {
            "ok": True,
            "scanned": len(candidates),
            "published": published,
            "auto_applied": auto_applied,
        }
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


@shared_task(name="platform_runtime.scheduled_job_health_monitor")
def scheduled_job_health_monitor_task() -> dict:
    """Beat entry point for the periodic-job dead-man's-switch.

    The in-process scheduler (``apps.platform_runtime.periodic``) runs this same
    monitor off ``/health/`` while there is no Celery broker, then stands down the
    moment a real worker + beat are provisioned. Without this beat entry, that
    hand-off would SILENCE the watchdog — so it is registered here too, keeping it
    alive in every execution mode.
    """
    try:
        from apps.platform_runtime.scheduled_job_health import run_health_monitor

        findings = run_health_monitor()
        stale = [f for f in findings if f.is_stale]
        return {"ok": True, "checked": len(findings), "stale": len(stale)}
    except Exception as exc:
        return {"ok": False, "reason": f"exception:{type(exc).__name__}"}


@shared_task(name="platform_runtime.drain_heavy_work_outbox")
def drain_heavy_work_outbox_task(limit: int = 3) -> dict:
    """Drain durable heavy-work outbox (provision / schema heal / MC advance)."""
    try:
        from apps.platform_runtime.heavy_work_outbox import drain_heavy_work_outbox

        return {"ok": True, **drain_heavy_work_outbox(limit=limit)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"exception:{type(exc).__name__}"}


def _run_school_is_settled(run) -> bool:
    """True when this run's school is already fully provisioned.

    Reuses the provisioning watchdog's single definition of "settled" (portal
    ready AND Phase B complete) rather than re-deriving it here, so the sweep and
    the watchdog can never disagree about whether a school still needs work.
    Fails OPEN (False) — an unknown school is treated as still needing the
    remediation it would have got before this guard existed.
    """
    try:
        from apps.schools.models import School
        from apps.schools.provision_watchdog import _school_is_settled

        school = School.objects.filter(pk=getattr(run, "school_id", "") or "").first()
        if school is None:
            return False
        return bool(_school_is_settled(school))
    except Exception:  # noqa: BLE001 — the guard must never break the sweep
        logger.debug(
            "settled-check failed for run=%s; treating as not settled",
            getattr(run, "pk", None),
            exc_info=True,
        )
        return False


def _run_school_needs_attention(run) -> bool:
    """True when the watchdog has declared this run's school terminally stuck.

    A ``needs_attention`` school must be excluded from auto-requeue: the watchdog
    already gave up after repeated no-progress resumes, so re-driving it here would
    resurrect the exact ~forever loop the terminal state exists to end. A human
    retry clears the flag (``_do_provision`` → ``clear_provision_needs_attention``).
    Fails OPEN (False) so an unknown school still gets its normal remediation.
    """
    try:
        from apps.schools.models import School
        from apps.schools.provision_watchdog import provision_needs_attention

        school = School.objects.filter(pk=getattr(run, "school_id", "") or "").first()
        if school is None:
            return False
        return bool(provision_needs_attention(school))
    except Exception:  # noqa: BLE001 — the guard must never break the sweep
        logger.debug(
            "needs-attention check failed for run=%s; treating as not terminal",
            getattr(run, "pk", None),
            exc_info=True,
        )
        return False


def provision_failure_clearable_after_success(run) -> bool:
    """True when an operator may clear this provision failure from the Flight Deck.

    Clear is allowed only after proof of success:
    - the school is settled (portal ready + Phase B), or
    - a ``succeeded`` provision run exists **and** a newer attempt superseded
      this row (this card is historical, not the live failure).

    The latest unfinished failure for an unsettled school cannot be cleared.
    """
    if getattr(run, "workflow_key", "") != "tenant_school_provision":
        return False
    status = (getattr(run, "status", "") or "").lower()
    if status not in ("failed", "cancelled", "stuck"):
        return False
    if _run_school_is_settled(run):
        return True
    school_id = str(getattr(run, "school_id", "") or "")
    if not school_id:
        return False
    if not _provision_has_later_attempt(run):
        return False
    try:
        from apps.platform_runtime.models import WorkflowRun

        return (
            # tenant-isolation-allow: platform-workflow-success-proof-per-school-id
            WorkflowRun.objects.filter(
                workflow_key="tenant_school_provision",
                school_id=school_id,
                status="succeeded",
            ).exists()
        )
    except Exception:  # noqa: BLE001
        return False


def _provision_has_later_attempt(run) -> bool:
    """True when another tenant_school_provision row for this school is newer."""
    school_id = str(getattr(run, "school_id", "") or "")
    if not school_id:
        return False
    try:
        from apps.platform_runtime.models import WorkflowRun

        latest = (
            # tenant-isolation-allow: platform-workflow-latest-provision-per-school-id
            WorkflowRun.objects.filter(
                workflow_key="tenant_school_provision",
                school_id=school_id,
            )
            .order_by("-started_at", "-pk")
            .first()
        )
    except Exception:  # noqa: BLE001 — never break deck/sweep on lookup failure
        return False
    return latest is not None and latest.pk != getattr(run, "pk", None)


def suppress_stale_provision_failure_for_deck(run) -> bool:
    """Hide (and stamp) provision failures that are settled or superseded.

    Flight Deck used to list every non-remediated failed/cancelled row forever.
    Celery's 10-minute settled sweep eventually stamps them — but without beat,
    or between ticks, operators see "Needs operator: 9" for schools that already
    provisioned. Call this on the deck read path so the UI matches reality now.

    Returns True when the row must leave Active / Recent failures.
    """
    from apps.platform_runtime.workflow_fix_handlers import workflow_run_is_remediated

    if workflow_run_is_remediated(run):
        return True
    if getattr(run, "workflow_key", "") != "tenant_school_provision":
        return False
    if _run_school_is_settled(run):
        _resolve_stale_provisioned_run(run)
        return True
    if _provision_has_later_attempt(run):
        _resolve_stale_provisioned_run(
            run,
            kind="superseded_by_later_attempt",
            human_action=(
                "No action needed — a newer provisioning attempt exists for this "
                "school. This row is historical, not the live failure."
            ),
            error_message=(
                "superseded: newer tenant_school_provision attempt exists for "
                "this school"
            ),
        )
        return True
    return False


def supersede_prior_provision_failures(succeeded_run) -> int:
    """On successful provision finalize, stamp older failed/cancelled/stuck rows.

    Each attempt is a new ``WorkflowRun``. Success does not rewrite prior FAILED
    rows unless we stamp them — otherwise the deck keeps them until Celery beat.
    """
    if getattr(succeeded_run, "workflow_key", "") != "tenant_school_provision":
        return 0
    school_id = str(getattr(succeeded_run, "school_id", "") or "")
    if not school_id:
        return 0
    try:
        from apps.platform_runtime.models import WorkflowRun
        from apps.platform_runtime.workflow_fix_handlers import workflow_run_is_remediated

        priors = list(
            # tenant-isolation-allow: platform-workflow-supersede-prior-failures-by-school-id
            WorkflowRun.objects.filter(
                workflow_key="tenant_school_provision",
                school_id=school_id,
                status__in=("failed", "cancelled", "stuck"),
            ).exclude(pk=succeeded_run.pk)[:50]
        )
    except Exception:  # noqa: BLE001
        logger.debug("supersede_prior_provision_failures_lookup_failed", exc_info=True)
        return 0
    cleared = 0
    for prior in priors:
        try:
            if workflow_run_is_remediated(prior):
                continue
            if _resolve_stale_provisioned_run(
                prior,
                kind="superseded_by_success",
                human_action=(
                    "No action needed — a later provisioning run succeeded for "
                    "this school. This row is historical."
                ),
                error_message=(
                    "superseded: later tenant_school_provision run succeeded"
                ),
            ):
                cleared += 1
        except Exception:  # noqa: BLE001
            logger.debug(
                "supersede_prior_provision_failures_row_failed pk=%s",
                getattr(prior, "pk", None),
                exc_info=True,
            )
    return cleared


def _resolve_stale_provisioned_run(
    run,
    *,
    kind: str = "stale_run_superseded",
    human_action: str | None = None,
    error_message: str | None = None,
) -> bool:
    """Retire a red row whose school is actually fine, and CLEAR IT OFF THE DECK.

    Setting ``status="cancelled"`` alone is not enough: the Flight Deck lists
    ``status__in=("failed", "cancelled")``, so a cancelled row keeps rendering as
    a red item — and because the school is settled, ``_can_requeue_provision``
    returns False, so that row shows with NO fix button. An operator is then
    staring at a permanent red row they cannot action, for a school that is
    healthy. The deck only hides a row that carries the remediation stamp
    (``workflow_fix_handlers.workflow_run_is_remediated``), so write that too.

    Returns True when this call retired the row (False if already retired), so
    the sweep does not re-report the same row every tick.
    """
    from apps.platform_runtime.models import WorkflowRun
    from apps.platform_runtime.workflow_fix_handlers import (
        _REMEDIATED_PAYLOAD_KEY,
        workflow_run_is_remediated,
    )

    if workflow_run_is_remediated(run):
        return False

    now = timezone.now()
    stamp = {
        "kind": kind,
        "applied_at": now.isoformat(),
        "school_id": str(getattr(run, "school_id", "") or ""),
        "result": {"ok": True, "applied": kind},
    }
    payload = dict(getattr(run, "payload_summary", None) or {})
    remediation = dict(getattr(run, "suggested_remediation", None) or {})
    payload[_REMEDIATED_PAYLOAD_KEY] = stamp
    remediation[_REMEDIATED_PAYLOAD_KEY] = stamp
    remediation["auto_fix_available"] = False
    remediation["human_action"] = human_action or (
        "No action needed — this school is fully provisioned. The drive was "
        "killed after the work landed but before it could record success, so "
        "this row was stale, not a failure."
    )
    # tenant-isolation-allow: platform-workflow-stale-row-resolve-by-pk
    WorkflowRun.objects.filter(pk=run.pk).update(
        status="cancelled",
        ended_at=getattr(run, "ended_at", None) or now,
        payload_summary=payload,
        suggested_remediation=remediation,
        error_summary={
            "type": "StaleRun",
            "message": error_message
            or (
                "superseded: school is fully provisioned (drive died after the "
                "work landed, before finalize could record success)"
            ),
        },
    )
    logger.info(
        "retired stale provisioning run=%s school=%s kind=%s",
        getattr(run, "pk", None),
        getattr(run, "school_id", ""),
        kind,
    )
    return True


@shared_task(name="platform_runtime.workflow_failed_provision_auto_requeue_sweep")
def workflow_failed_provision_auto_requeue_sweep_task() -> dict:
    """Batch 1737 — zero-fail: auto-requeue failed/stuck tenant_school_provision runs."""
    try:
        from apps.platform_runtime.models import WorkflowRun
        from apps.platform_runtime.workflow_autopilot import try_auto_apply_on_failure
        from apps.platform_runtime.workflow_flight_deck_actions import (
            resolve_effective_remediation,
        )
        from apps.platform_runtime.workflow_fix_handlers import apply_auto_fix_kind

        candidates = list(
            # tenant-isolation-allow: platform-workflow-provision-sweep-no-tenant-scope
            WorkflowRun.objects.filter(
                workflow_key="tenant_school_provision",
                status__in=("failed", "stuck", "cancelled"),
            ).order_by("-started_at")[:100]  # WorkflowRun has no `updated_at`; -updated_at raised FieldError (swallowed) → sweep was a no-op
        )
        remediated = 0
        requeued = 0
        settled_skipped = 0
        settled_resolved = 0
        needs_attention_skipped = 0
        for run in candidates:
            try:
                # A run can be FAILED while its school is fully provisioned: the
                # drive is killed AFTER the work lands but BEFORE finalize_run
                # writes "succeeded", so the row stays failed forever while the
                # tenant is live (observed in prod — schools with 322 tables /
                # 1196 applied migrations / phase A+B complete still carrying a
                # FAILED tenant_schema run). Requeuing those re-drives a finished
                # tenant, and because the requeue never clears the old row it
                # would be re-picked on EVERY tick — an unbounded migrate storm.
                # Mark the stale row cancelled so it leaves the candidate set,
                # and never re-drive a settled school.
                if _run_school_is_settled(run):
                    settled_skipped += 1
                    if _resolve_stale_provisioned_run(run):
                        settled_resolved += 1
                    continue
                # Terminal 'needs attention': the watchdog gave up after repeated
                # no-progress resumes. Re-driving here would resurrect the ~forever
                # loop; skip until a human retry clears the flag.
                if _run_school_needs_attention(run):
                    needs_attention_skipped += 1
                    continue
                rem = resolve_effective_remediation(run)
                if rem.get("auto_fix_kind") != "requeue_provision":
                    continue
                if not rem.get("auto_fix_available"):
                    # tenant-isolation-allow: workflow-remediation-stamp-by-pk
                    WorkflowRun.objects.filter(pk=run.pk).update(
                        suggested_remediation=rem
                    )
                    remediated += 1
                result = try_auto_apply_on_failure(run_pk=run.pk)
                if result:
                    requeued += 1
                    continue
                apply_result = apply_auto_fix_kind(run=run, kind="requeue_provision")
                if apply_result.get("ok"):
                    requeued += 1
            except Exception:
                logger.debug(
                    "workflow_failed_provision_auto_requeue skipped run=%s",
                    getattr(run, "pk", None),
                    exc_info=True,
                )
                continue
        return {
            "ok": True,
            "scanned": len(candidates),
            "remediated": remediated,
            "requeued": requeued,
            "settled_skipped": settled_skipped,
            "settled_resolved": settled_resolved,
            "needs_attention_skipped": needs_attention_skipped,
        }
    except Exception as exc:
        return {"ok": False, "reason": f"exception:{type(exc).__name__}"}
