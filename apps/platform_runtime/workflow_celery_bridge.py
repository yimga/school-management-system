"""
Automatic WorkflowRun rows for Celery tasks (operators + tenants).

Hooks task_prerun / task_postrun / task_failure so every @shared_task
surfaces in the Workflow Progress Bus without per-task boilerplate.

Tasks with fine-grained ``@track_workflow`` / internal ``begin_run`` should
set ``rmc_workflow_explicit = True`` on the task object (or appear in
``_EXPLICIT_CELERY_TASKS``) to avoid duplicate envelopes.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Celery internals + platform heartbeats / sub-second flushes (no UI noise).
_WORKFLOW_CELERY_DENYLIST = frozenset(
    {
        "celery.chord_unlock",
        "celery.chord",
        "celery.accumulate",
        "celery.backend_cleanup",
        "celery.group",
        "config.debug_task",
        "wal_stream.drain_fanout",
        "apps.billing.tasks_ai_token_flush.flush_ai_metrics_buckets",
        "billing-flush-ai-metrics",
        "billing-flush-realtime-meter",
        "platform_runtime.operator_visibility_heartbeat",
        "platform_runtime.database_connectivity_heartbeat",
        "platform_runtime.automation_failure_trend_signal",
        "platform_runtime.workflow_stuck_alert_sweep",
        "platform_runtime.workflow_sla_breach_alert_sweep",
        "platform_runtime.process_offline_queues_due",
        "siteconfig.snapshot_platform_pulse_daily",
        "siteconfig.check_regional_ollama_health",
        "migration_cloud.tasks_smoke.run_smoke_against_synthetic_tenant",
        # Periodic finance sweeps — sub-minute; no operator chip noise.
        "finance.send_payment_reminders",
        "finance.retry_failed_payment_reminders",
        "finance.apply_split_late_fees",
        "finance.update_invoice_statuses",
        "finance.retry_bank_verification",
        "finance.process_payment_receipt_upload",
        "marketplace.marketplace_health_check",
        "marketplace.deliver_install_hooks",
    }
)

# Substrings — deny periodic sweeps under 30s that would flood the chip.
_WORKFLOW_CELERY_DENY_SUBSTRINGS = (
    "_heartbeat",
    "_beat",
    "_flush",
    "drain_fanout",
    "sweep_event_webhook",
    "purge_help_telemetry",
    "archive_stale",
    "reindex_kb",
    "build_code_support_index",
    "help_north_star",
    "prune_stale",
)

# Detailed step tracking already owned elsewhere.
_EXPLICIT_CELERY_TASKS = frozenset(
    {
        "apps.schools.tasks.provision_school_task",
        "schools.provision_school_task",
        "apps.schools.tasks.run_scheduled_tenant_purges_task",
        "schools.run_scheduled_tenant_purges",
        "schools.purge_tenant_media_task",
        "migration_cloud.apply_bundle",
        "migration_cloud.advance_bundle",
        "migration_cloud.fetch_assets",
        "evals.process_bulk_grades",
        "orchestration.process_due_runs",
        "finance.auto_generate_fee_invoices",
        "finance.auto_copy_fee_plans",
        "marketplace.webhook_deliver_due",
    }
)

# Prefer registry-backed keys + labels for high-value Celery entrypoints.
_CELERY_WORKFLOW_KEY_OVERRIDES: dict[str, str] = {
    "migration_cloud.apply_bundle": "migration_bundle_apply",
    "migration_cloud.advance_bundle": "migration_bundle_advance",
    "migration_cloud.fetch_assets": "migration_bundle_fetch_assets",
    "evals.process_bulk_grades": "evals_bulk_grades",
    "orchestration.process_due_runs": "orchestration_process_due",
    "finance.auto_generate_fee_invoices": "finance_auto_generate_fee_invoices",
    "finance.auto_copy_fee_plans": "finance_auto_copy_fee_plans",
    "marketplace.webhook_deliver_due": "marketplace_webhook_deliver_due",
    "schools.provision_school_task": "tenant_school_provision",
    "apps.schools.tasks.provision_school_task": "tenant_school_provision",
    "schools.run_scheduled_tenant_purges": "tenant_school_offboard_purge",
    "apps.schools.tasks.run_scheduled_tenant_purges_task": "tenant_school_offboard_purge",
}

_active_by_task_id: dict[str, Any] = {}


def _task_display_name(task: Any) -> str:
    if task is None:
        return "unknown"
    return getattr(task, "name", None) or getattr(task, "__name__", str(task))


def _workflow_key_for_task(name: str) -> str:
    if name in _CELERY_WORKFLOW_KEY_OVERRIDES:
        return _CELERY_WORKFLOW_KEY_OVERRIDES[name][:80]
    short = name.rsplit(".", 1)[-1][:72]
    return f"celery.{short}"[:80]


def _workflow_label_for_task(name: str) -> str:
    short = name.rsplit(".", 1)[-1]
    return short.replace("_", " ").replace("-", " ").strip().title()[:160]  # magic-number-allow: string-truncation-cap


def _should_track_celery_task(task: Any, *, name: str) -> bool:
    if not name or name in _WORKFLOW_CELERY_DENYLIST:
        return False
    if name.startswith("celery."):
        return False
    if name in _EXPLICIT_CELERY_TASKS:
        return False
    if getattr(task, "rmc_workflow_explicit", False):
        return False
    lowered = name.lower()
    if any(fragment in lowered for fragment in _WORKFLOW_CELERY_DENY_SUBSTRINGS):
        return False
    return True


def _expected_duration_seconds(task: Any) -> int:
    for attr in ("time_limit", "soft_time_limit"):
        val = getattr(task, attr, None)
        if val and int(val) > 0:
            return min(int(val), 3600)  # magic-number-allow: max-clamp-seconds
    return 120


def _school_id_from_kwargs(kwargs: Optional[dict]) -> str:
    if not isinstance(kwargs, dict):
        return ""
    for key in ("school_id", "school_pk", "tenant_id"):
        val = kwargs.get(key)
        if val is not None and str(val).strip():
            return str(val)[:40]
    return ""


def _tenant_schema_from_kwargs(kwargs: Optional[dict]) -> str:
    if not isinstance(kwargs, dict):
        return ""
    for key in ("tenant_schema", "schema_name"):
        val = kwargs.get(key)
        if val is not None and str(val).strip():
            return str(val)[:64]
    return ""


def celery_task_prerun(
    *,
    task_id: Optional[str],
    task: Any,
    kwargs: Optional[dict],
) -> None:
    name = _task_display_name(task)
    if not _should_track_celery_task(task, name=name):
        return
    if not task_id:
        return
    try:
        from apps.platform_runtime.workflow_tracker import begin_run

        run = begin_run(
            workflow_key=_workflow_key_for_task(name),
            steps=("execute",),
            school_id=_school_id_from_kwargs(kwargs),
            tenant_schema=_tenant_schema_from_kwargs(kwargs),
            expected_duration_seconds=_expected_duration_seconds(task),
            idempotency_key=f"celery:{task_id}"[:128],
            payload={"celery_task": name[:120]},
        )
        if run is not None:
            _active_by_task_id[str(task_id)] = run
            from apps.platform_runtime.workflow_tracker import push_workflow_run

            push_workflow_run(run)
    except Exception:
        logger.debug("workflow_celery_prerun_failed name=%s", name, exc_info=True)


def celery_task_postrun(
    *,
    task_id: Optional[str],
    task: Any,
    state: Optional[str] = None,
) -> None:
    if not task_id:
        return
    run = _active_by_task_id.pop(str(task_id), None)
    if run is None:
        return
    try:
        from apps.platform_runtime.workflow_tracker import finalize_run

        status = "failed" if state == "FAILURE" else "succeeded"
        finalize_run(run, status=status)
        from apps.platform_runtime.workflow_tracker import pop_workflow_run

        pop_workflow_run(run)
    except Exception:
        logger.debug("workflow_celery_postrun_failed", exc_info=True)


def celery_task_failure(
    *,
    task_id: Optional[str],
    exception: Optional[BaseException] = None,
) -> None:
    if not task_id:
        return
    run = _active_by_task_id.pop(str(task_id), None)
    if run is None:
        return
    try:
        from apps.platform_runtime.workflow_tracker import finalize_run

        finalize_run(run, status="failed", error=exception)
        from apps.platform_runtime.workflow_tracker import pop_workflow_run

        pop_workflow_run(run)
    except Exception:
        logger.debug("workflow_celery_failure_finalize_failed", exc_info=True)


def clear_active_runs_for_tests() -> None:
    """Test helper — reset in-memory task_id → run map."""
    _active_by_task_id.clear()
