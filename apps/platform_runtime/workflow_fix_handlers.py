"""Idempotent auto-fix handlers for Workflow Progress Bus."""

from __future__ import annotations

import logging
from typing import Any

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

_REMEDIATED_PAYLOAD_KEY = "workflow_fix_remediation"
_DEFER_REMEDIATION_STAMP = False

AUTO_FIX_HANDLER_CATALOG: dict[str, dict[str, Any]] = {
    "requeue_provision": {
        "label": "Requeue provisioning",
        "mode": "execute",
        "confidence": "high",
        "requires_network": True,
        "description": "Launches the idempotent school provisioning task again.",
    },
    "resend_welcome": {
        "label": "Resend welcome email",
        "mode": "execute",
        "confidence": "high",
        "requires_network": True,
        "description": "Sends the tenant welcome email again.",
    },
    "retry_dns_sync": {
        "label": "Retry DNS sync",
        "mode": "execute",
        "confidence": "medium",
        "requires_network": True,
        "description": "Re-syncs runtime domains and retries DNS provisioning.",
    },
    "repair_tenant_schema_drift": {
        "label": "Repair schema drift",
        "mode": "execute",
        "confidence": "medium",
        "requires_network": False,
        "description": "Runs tenant schema drift healing in apply mode.",
    },
    "run_tenant_migrations": {
        "label": "Run tenant migrations",
        "mode": "execute",
        "confidence": "medium",
        "requires_network": False,
        "description": "Runs tenant migrations through the existing management command.",
    },
    "mark_superseded": {
        "label": "Mark superseded",
        "mode": "execute",
        "confidence": "high",
        "requires_network": False,
        "description": "Moves the old row out of the unresolved deck after replacement work exists.",
    },
    "clear_after_success": {
        "label": "Clear from deck",
        "mode": "execute",
        "confidence": "high",
        "requires_network": False,
        "description": (
            "Removes this provision failure from the Flight Deck only after the "
            "school provisioned successfully (settled or a succeeded run exists)."
        ),
    },
    "retry_once_with_backoff": {
        "label": "Retry with backoff",
        "mode": "execute",
        "confidence": "medium",
        "requires_network": True,
        "description": "Marks the run for retry and records retry metadata.",
    },
    "retry_after_rate_limit": {
        "label": "Retry after rate limit",
        "mode": "execute",
        "confidence": "medium",
        "requires_network": True,
        "description": "Marks the run for a rate-limit-safe retry.",
    },
    "refresh_oauth_token_and_retry": {
        "label": "Refresh token and retry",
        "mode": "execute",
        "confidence": "medium",
        "requires_network": True,
        "description": "Marks the run for retry after credential refresh.",
    },
    "suggest_alternate_slug": {
        "label": "Suggest alternate slug",
        "mode": "diagnostic",
        "confidence": "medium",
        "requires_network": False,
        "description": "Computes slug alternatives; no automatic database mutation.",
    },
    "resume_from_checkpoint": {
        "label": "Resume from checkpoint",
        "mode": "execute",
        "confidence": "conditional",
        "requires_network": False,
        "description": "Routes to a workflow-specific checkpoint handler when metadata is present.",
    },
    "retry_failed_step": {
        "label": "Retry failed step",
        "mode": "execute",
        "confidence": "conditional",
        "requires_network": False,
        "description": (
            "Re-drives the failed step: Migration Cloud via durable outbox, "
            "named Celery tasks from the run payload, else marks the run for retry."
        ),
    },
    "replay_webhook": {
        "label": "Replay webhook",
        "mode": "execute",
        "confidence": "high",
        "requires_network": True,
        "description": "Replays a domain webhook delivery, platform webhook delivery, or platform event.",
    },
    "clear_stale_lock": {
        "label": "Clear stale lock",
        "mode": "execute",
        "confidence": "conditional",
        "requires_network": False,
        "description": "Deletes an explicit cache lock key from the run payload.",
    },
    "cancel_duplicate_run": {
        "label": "Cancel duplicate run",
        "mode": "execute",
        "confidence": "high",
        "requires_network": False,
        "description": "Cancels active duplicate workflow rows for the same idempotency or tenant target.",
    },
    "open_diagnostic_detail": {
        "label": "Open AI diagnosis",
        "mode": "navigation",
        "confidence": "high",
        "requires_network": False,
        "description": "Opens the run detail with AI-ready context.",
    },
}


def auto_fix_capability(kind: str) -> dict[str, Any]:
    """Return public capability metadata for an auto-fix kind."""

    key = str(kind or "").strip()
    meta = dict(AUTO_FIX_HANDLER_CATALOG.get(key) or {})
    if not meta:
        return {
            "label": "Unsupported fix",
            "mode": "unsupported",
            "confidence": "unknown",
            "requires_network": False,
            "description": "No handler is registered for this auto_fix_kind.",
        }
    meta["kind"] = key
    return meta


def auto_fix_kind_is_executable(kind: str) -> bool:
    return auto_fix_capability(kind).get("mode") == "execute"


def _payload_first(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _as_int(value: Any) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _chain_to_kind(*, run: Any, kind: str, source_kind: str) -> dict[str, Any]:
    if not kind or kind == source_kind:
        return {"ok": False, "reason": "missing_recovery_handler", "kind": source_kind}
    result = apply_auto_fix_kind(run=run, kind=kind)
    if result.get("ok"):
        result["delegated_from"] = source_kind
    return result


def workflow_run_remediation_stamp(run: Any) -> dict[str, Any]:
    """Return the latest fix stamp for a run, if a fix already superseded it."""

    for source in (
        getattr(run, "payload_summary", None),
        getattr(run, "suggested_remediation", None),
    ):
        if not isinstance(source, dict):
            continue
        stamp = source.get(_REMEDIATED_PAYLOAD_KEY) or source.get("applied_fix")
        if isinstance(stamp, dict) and stamp.get("applied_at"):
            return stamp
    return {}


def workflow_run_is_remediated(run: Any) -> bool:
    """True when a terminal/stuck row has already launched a repair action."""

    return bool(workflow_run_remediation_stamp(run))


def _mark_run_remediated(
    *,
    run: Any,
    kind: str,
    result: dict[str, Any],
    status: str = "",
) -> dict[str, Any]:
    """Stamp the original run after a real fix is launched.

    The old row remains auditable, but the Flight Deck can stop presenting it as
    an unresolved red item while the newly queued workflow takes over.
    """

    if _DEFER_REMEDIATION_STAMP:
        return {}

    if run is None or getattr(run, "pk", None) is None:
        return {}

    from apps.platform_runtime.models import WorkflowRun

    now = timezone.now()
    payload = dict(getattr(run, "payload_summary", None) or {})
    remediation = dict(getattr(run, "suggested_remediation", None) or {})
    stamp = {
        "kind": kind,
        "applied_at": now.isoformat(),
        "school_id": str(result.get("school_id") or getattr(run, "school_id", "") or ""),
        "result": {
            "ok": bool(result.get("ok")),
            "applied": str(result.get("applied") or kind),
        },
    }
    payload[_REMEDIATED_PAYLOAD_KEY] = stamp
    remediation[_REMEDIATED_PAYLOAD_KEY] = stamp
    remediation["auto_fix_available"] = False
    remediation["human_action"] = (
        "Fix launched. The original run is now superseded; watch the active run "
        "for live delivery."
    )
    update_fields: dict[str, Any] = {
        "payload_summary": payload,
        "suggested_remediation": remediation,
        "last_heartbeat_at": now,
    }
    if status:
        update_fields["status"] = status
        update_fields["ended_at"] = now
    WorkflowRun.objects.filter(pk=run.pk).update(**update_fields)  # tenant-isolation-allow: workflow-run-remediation-stamp-by-pk
    return stamp


def preview_auto_fix_kind(*, run: Any, kind: str) -> dict[str, Any]:
    """Shadow/dry-run: describe what apply would do without mutating the run."""

    capability = auto_fix_capability(kind)
    workflow_key = getattr(run, "workflow_key", "")
    payload = dict(getattr(run, "payload_summary", None) or {})

    if capability.get("mode") not in ("execute", "diagnostic", "navigation"):
        return {
            "ok": False,
            "dry_run": True,
            "reason": "unsupported_fix_kind",
            "kind": kind,
            "capability": capability,
        }

    if capability.get("mode") in ("diagnostic", "navigation"):
        return {
            "ok": True,
            "dry_run": True,
            "would_apply": "",
            "kind": kind,
            "capability": capability,
            "note": capability.get("description", "Open run detail for diagnosis."),
        }

    if kind == "suggest_alternate_slug":
        base = payload.get("slug") or workflow_key
        alternates = [f"{base}-2026", f"{base}-academy", f"{base}-school"]
        return {
            "ok": True,
            "dry_run": True,
            "would_apply": kind,
            "capability": capability,
            "alternates": alternates,
            "note": "No database changes in preview mode.",
        }

    if kind in ("retry_once_with_backoff", "retry_after_rate_limit", "refresh_oauth_token_and_retry"):
        return {
            "ok": True,
            "dry_run": True,
            "would_apply": kind,
            "would_set_status": "running",
            "current_status": getattr(run, "status", ""),
            "capability": capability,
            "note": "Would mark run running and stamp retry metadata in payload_summary.",
        }

    if kind in (
        "requeue_provision",
        "resend_welcome",
        "retry_dns_sync",
        "repair_tenant_schema_drift",
        "run_tenant_migrations",
        "mark_superseded",
        "clear_after_success",
        "resume_from_checkpoint",
        "retry_failed_step",
        "replay_webhook",
        "clear_stale_lock",
        "cancel_duplicate_run",
    ):
        return {
            "ok": True,
            "dry_run": True,
            "would_apply": kind,
            "workflow_key": workflow_key,
            "capability": capability,
            "note": capability.get("description", "Owner-safe remediation."),
        }

    return {
        "ok": False,
        "dry_run": True,
        "reason": "unsupported_fix_kind",
        "kind": kind,
        "capability": capability,
    }


def _payload_first(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def _as_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _chain_to_kind(run: Any, kind: str, source_kind: str) -> dict[str, Any]:
    if not kind or kind == source_kind:
        return {
            "ok": False,
            "reason": "missing_recovery_route",
            "kind": source_kind,
        }
    result = apply_auto_fix_kind(run=run, kind=kind)
    result.setdefault("source_kind", source_kind)
    result.setdefault("delegated_from", source_kind)
    return result


def _retry_failed_step_by_workflow(
    *,
    run: Any,
    workflow_key: str,
    payload: dict[str, Any],
    source_kind: str,
) -> dict[str, Any]:
    """Concrete re-drive when payload has no delegated auto_fix_kind.

    Migration Cloud → durable outbox. Named Celery task (payload or registry)
    → ``send_task``. Otherwise stamp the run for retry.
    """
    from apps.platform_runtime.models import WorkflowRun

    # Known stuck-default workflows → Celery task name when payload omits one.
    # Keep in sync with STUCK_DEFAULT_FIX_BY_WORKFLOW retry_failed_step rows.
    _RETRY_CELERY_TASK_BY_WORKFLOW: dict[str, str] = {
        "evals_bulk_grades": "evals.process_bulk_grades",
        "finance_auto_generate_fee_invoices": "finance.auto_generate_fee_invoices",
        "finance_auto_copy_fee_plans": "finance.auto_copy_fee_plans",
        "orchestration_process_due": "orchestration.process_due_runs",
        "tenant_school_offboard_purge": "schools.run_scheduled_tenant_purges",
    }

    bid = _as_int(_payload_first(payload, "bundle_id", "migration_bundle_id"))

    if workflow_key == "migration_bundle_advance":
        if not bid:
            return {"ok": False, "reason": "missing_bundle_id", "kind": source_kind}
        from apps.migration_cloud.celery_tasks import enqueue_advance

        queued = enqueue_advance(int(bid), use_accelerator=True)
        result = {
            "ok": True,
            "applied": source_kind,
            "workflow_key": workflow_key,
            "bundle_id": int(bid),
            "durable_outbox": True,
            "outbox_id": getattr(queued, "outbox_id", None) or getattr(queued, "id", None),
            "queued_async": True,
            "refresh_deck": True,
            "healing_poll_ms": 2500,
        }
        result["remediation"] = _mark_run_remediated(run=run, kind=source_kind, result=result)
        return result

    if workflow_key == "migration_bundle_apply":
        if not bid:
            return {"ok": False, "reason": "missing_bundle_id", "kind": source_kind}
        from apps.migration_cloud.celery_tasks import enqueue_apply

        dry_run = bool(payload.get("dry_run", False))
        queued = enqueue_apply(int(bid), dry_run=dry_run)
        result = {
            "ok": True,
            "applied": source_kind,
            "workflow_key": workflow_key,
            "bundle_id": int(bid),
            "dry_run": dry_run,
            "durable_outbox": True,
            "outbox_id": getattr(queued, "outbox_id", None) or getattr(queued, "id", None),
            "queued_async": True,
            "refresh_deck": True,
            "healing_poll_ms": 2500,
        }
        result["remediation"] = _mark_run_remediated(run=run, kind=source_kind, result=result)
        return result

    if workflow_key == "migration_bundle_fetch_assets":
        if not bid:
            return {"ok": False, "reason": "missing_bundle_id", "kind": source_kind}
        from apps.migration_cloud.celery_tasks import enqueue_fetch_assets

        queued = enqueue_fetch_assets(int(bid))
        result = {
            "ok": True,
            "applied": source_kind,
            "workflow_key": workflow_key,
            "bundle_id": int(bid),
            "queued_async": queued is not None,
            "refresh_deck": True,
            "healing_poll_ms": 2500,
        }
        result["remediation"] = _mark_run_remediated(run=run, kind=source_kind, result=result)
        return result

    task_name = str(
        _payload_first(payload, "celery_task_name", "task_name", "retry_task_name")
        or _RETRY_CELERY_TASK_BY_WORKFLOW.get(workflow_key, "")
        or ""
    ).strip()
    if task_name:
        try:
            from celery import current_app

            args = payload.get("celery_task_args") or payload.get("task_args") or []
            kwargs = dict(
                payload.get("celery_task_kwargs") or payload.get("task_kwargs") or {}
            )
            if not isinstance(args, (list, tuple)):
                args = []
            # Prefer explicit payload kwargs; else seed from the stuck run's tenant.
            if not kwargs:
                sid = str(getattr(run, "school_id", "") or "").strip()
                schema = str(getattr(run, "tenant_schema", "") or "").strip()
                if sid:
                    kwargs["school_id"] = sid
                if schema and "schema_name" not in kwargs:
                    kwargs["schema_name"] = schema
            current_app.send_task(task_name, args=list(args), kwargs=dict(kwargs))
            WorkflowRun.objects.filter(pk=run.pk).update(  # tenant-isolation-allow: workflow-run-update-by-primary-key-row
                status="running",
                last_heartbeat_at=timezone.now(),
                payload_summary={
                    **payload,
                    "retry_requested_at": timezone.now().isoformat(),
                    "retry_kind": source_kind,
                    "retry_task_name": task_name,
                },
            )
            result = {
                "ok": True,
                "applied": source_kind,
                "workflow_key": workflow_key,
                "celery_task_name": task_name,
                "queued_async": True,
                "refresh_deck": True,
                "healing_poll_ms": 2500,
            }
            result["remediation"] = _mark_run_remediated(
                run=run, kind=source_kind, result=result
            )
            return result
        except Exception as exc:  # noqa: BLE001 — fall through to stamp-only retry
            logger.warning(
                "retry_failed_step celery requeue failed workflow=%s task=%s: %s",
                workflow_key,
                task_name,
                type(exc).__name__,
            )

    WorkflowRun.objects.filter(pk=run.pk).update(  # tenant-isolation-allow: workflow-run-update-by-primary-key-row
        status="running",
        last_heartbeat_at=timezone.now(),
        payload_summary={
            **payload,
            "retry_requested_at": timezone.now().isoformat(),
            "retry_kind": source_kind,
        },
    )
    result = {
        "ok": True,
        "applied": source_kind,
        "workflow_key": workflow_key,
        "note": (
            "Run marked for retry. Re-invoke the originating action or wait for "
            "the next scheduled sweep."
        ),
        "refresh_deck": True,
        "healing_poll_ms": 2500,
    }
    result["remediation"] = _mark_run_remediated(run=run, kind=source_kind, result=result)
    return result


def apply_auto_fix_kind(*, run: Any, kind: str, defer_remediation_stamp: bool = False) -> dict[str, Any]:
    """Execute a supported ``auto_fix_kind``. Returns JSON-serializable result."""

    global _DEFER_REMEDIATION_STAMP
    prior_defer = _DEFER_REMEDIATION_STAMP
    _DEFER_REMEDIATION_STAMP = defer_remediation_stamp
    try:
        return _apply_auto_fix_kind_impl(run=run, kind=kind)
    finally:
        _DEFER_REMEDIATION_STAMP = prior_defer


def _apply_auto_fix_kind_impl(*, run: Any, kind: str) -> dict[str, Any]:

    from apps.platform_runtime.models import WorkflowRun

    workflow_key = getattr(run, "workflow_key", "")
    payload = dict(getattr(run, "payload_summary", None) or {})
    capability = auto_fix_capability(kind)

    if capability.get("mode") != "execute":
        return {
            "ok": False,
            "reason": "diagnostic_only"
            if capability.get("mode") in ("diagnostic", "navigation")
            else "unsupported_fix_kind",
            "kind": kind,
            "capability": capability,
        }

    if kind == "replay_webhook":
        platform_event_id = _as_int(_payload_first(payload, "platform_event_id", "event_id"))
        if platform_event_id:
            from apps.platform_runtime.event_bus import replay_event

            result = dict(replay_event(platform_event_id, dispatch_webhooks=True))
            if result.get("ok"):
                result.update(
                    {
                        "applied": kind,
                        "refresh_deck": True,
                        "healing_poll_ms": 2500,
                    }
                )
                result["remediation"] = _mark_run_remediated(
                    run=run,
                    kind=kind,
                    result=result,
                )
            else:
                result.setdefault("kind", kind)
            return result

        platform_delivery_id = _as_int(
            _payload_first(
                payload,
                "platform_webhook_delivery_id",
                "event_webhook_delivery_id",
            )
        )
        if platform_delivery_id:
            from apps.platform_runtime.models import EventWebhookDelivery

            updated = EventWebhookDelivery.objects.filter(pk=platform_delivery_id).update(  # tenant-isolation-allow: platform-webhook-delivery-operator-replay-by-pk
                status=EventWebhookDelivery.Status.PENDING,
                next_retry_at=timezone.now(),
                last_error="",
                operator_resolution=None,
                operator_resolution_reason="",
                operator_resolution_by_id=None,
                operator_resolution_at=None,
            )
            if not updated:
                return {"ok": False, "reason": "webhook_delivery_not_found", "kind": kind}
            result = {
                "ok": True,
                "applied": kind,
                "platform_webhook_delivery_id": platform_delivery_id,
                "refresh_deck": True,
                "healing_poll_ms": 2500,
            }
            result["remediation"] = _mark_run_remediated(run=run, kind=kind, result=result)
            return result

        domain_delivery_id = _as_int(
            _payload_first(payload, "webhook_delivery_id", "domain_webhook_delivery_id")
        )
        if domain_delivery_id:
            from apps.events.models import WebhookDelivery
            from apps.events.webhooks import replay_webhook_delivery

            run_school_id = getattr(run, "school_id", None) or payload.get("school_id")
            delivery = (
                WebhookDelivery.objects.filter(pk=domain_delivery_id)  # tenant-isolation-allow: workflow-webhook-replay-by-pk-with-run-school-validation
                .select_related("subscription", "domain_event")
                .first()
            )
            if delivery is None:
                return {"ok": False, "reason": "webhook_delivery_not_found", "kind": kind}
            if run_school_id:
                sub_school = getattr(delivery.subscription, "school_id", None)
                evt_school = getattr(delivery.domain_event, "school_id", None)
                if str(sub_school or evt_school or "") != str(run_school_id):
                    return {"ok": False, "reason": "webhook_delivery_tenant_mismatch", "kind": kind}
            replayed = replay_webhook_delivery(delivery)
            result = {
                "ok": True,
                "applied": kind,
                "webhook_delivery_id": domain_delivery_id,
                "replayed_delivery_id": getattr(replayed, "pk", None),
                "refresh_deck": True,
                "healing_poll_ms": 2500,
            }
            result["remediation"] = _mark_run_remediated(run=run, kind=kind, result=result)
            return result

        return {"ok": False, "reason": "missing_webhook_replay_target", "kind": kind}

    if kind == "clear_stale_lock":
        lock_key = str(
            _payload_first(payload, "lock_key", "cache_lock_key", "stale_lock_key") or ""
        ).strip()
        if not lock_key:
            return {"ok": False, "reason": "missing_lock_key", "kind": kind}
        if len(lock_key) > 250 or any(ch.isspace() for ch in lock_key):
            return {"ok": False, "reason": "unsafe_lock_key", "kind": kind}
        deleted = cache.delete(lock_key)
        result = {
            "ok": True,
            "applied": kind,
            "lock_key": lock_key,
            "deleted": bool(deleted),
            "refresh_deck": True,
            "healing_poll_ms": 2500,
        }
        result["remediation"] = _mark_run_remediated(run=run, kind=kind, result=result)
        return result

    if kind == "cancel_duplicate_run":
        duplicate_id = _as_int(_payload_first(payload, "duplicate_run_id", "duplicate_id"))
        candidates = WorkflowRun.objects.filter(status__in=("running", "stuck"))  # tenant-isolation-allow: workflow-duplicate-cancel-operator-scoped
        if duplicate_id:
            candidates = candidates.filter(pk=duplicate_id)
        elif getattr(run, "idempotency_key", ""):
            candidates = candidates.filter(idempotency_key=run.idempotency_key).exclude(pk=run.pk)
        else:
            candidates = candidates.filter(
                Q(workflow_key=workflow_key),
                Q(tenant_schema=getattr(run, "tenant_schema", "")),
                Q(school_id=getattr(run, "school_id", "")),
            ).exclude(pk=run.pk)
        cancelled_ids = list(candidates.values_list("pk", flat=True))
        cancelled = candidates.update(
            status="cancelled",
            ended_at=timezone.now(),
            payload_summary={
                **payload,
                "cancelled_as_duplicate_of": str(getattr(run, "pk", "") or ""),
                "cancelled_at": timezone.now().isoformat(),
            },
        )
        if not cancelled:
            # No duplicates is success for a healing chain step — continue to repair.
            result = {
                "ok": True,
                "applied": kind,
                "cancelled": 0,
                "cancelled_run_ids": [],
                "skipped": True,
                "reason": "duplicate_run_not_found",
                "refresh_deck": True,
                "healing_poll_ms": 2500,
            }
            result["remediation"] = _mark_run_remediated(run=run, kind=kind, result=result)
            return result
        result = {
            "ok": True,
            "applied": kind,
            "cancelled": cancelled,
            "cancelled_run_ids": cancelled_ids,
            "refresh_deck": True,
            "healing_poll_ms": 2500,
        }
        result["remediation"] = _mark_run_remediated(run=run, kind=kind, result=result)
        return result

    if kind == "suggest_alternate_slug":
        base = payload.get("slug") or workflow_key
        alternates = [f"{base}-2026", f"{base}-academy", f"{base}-school"]
        return {"ok": False, "reason": "diagnostic_only", "applied": kind, "alternates": alternates}

    if kind in ("retry_once_with_backoff", "retry_after_rate_limit", "refresh_oauth_token_and_retry"):
        WorkflowRun.objects.filter(pk=run.pk).update(  # tenant-isolation-allow: workflow-run-update-by-primary-key-row
            status="running",
            last_heartbeat_at=timezone.now(),
            payload_summary={
                **payload,
                "retry_requested_at": timezone.now().isoformat(),
                "retry_kind": kind,
            },
        )
        return {
            "ok": True,
            "applied": kind,
            "note": "Run marked for retry. Re-invoke the original action.",
            "refresh_deck": True,
            "healing_poll_ms": 2500,
        }

    if kind == "repair_tenant_schema_drift":
        tenant_schema = str(
            getattr(run, "tenant_schema", "") or payload.get("tenant_schema") or ""
        ).strip()
        if not tenant_schema:
            return {"ok": False, "reason": "missing_tenant_schema", "kind": kind}
        from apps.platform_runtime.heavy_work_outbox import enqueue_heavy_work
        from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox

        row = enqueue_heavy_work(
            HeavyWorkOutbox.Kind.HEAL_TENANT_SCHEMA,
            school_id=str(getattr(run, "school_id", "") or ""),
            tenant_schema=tenant_schema,
            payload={
                "tenant_schema": tenant_schema,
                "workflow_run_id": str(getattr(run, "pk", "") or ""),
            },
            idempotency_key=f"heal-schema:{tenant_schema}:{getattr(run, 'pk', '')}",
            kick=True,
        )
        result = {
            "ok": True,
            "applied": kind,
            "tenant_schema": tenant_schema,
            "queued_async": True,
            "durable_outbox": True,
            "job_id": str(row.pk),
            "outbox_id": str(row.pk),
            "note": (
                "Schema heal queued on durable heavy-work outbox "
                "(never on the Flight Deck HTTP request)."
            ),
            "refresh_deck": True,
            "healing_poll_ms": 2500,
        }
        result["remediation"] = _mark_run_remediated(run=run, kind=kind, result=result)
        return result

    if kind == "run_tenant_migrations":
        tenant_schema = str(
            getattr(run, "tenant_schema", "") or payload.get("tenant_schema") or ""
        ).strip()
        from apps.platform_runtime.heavy_work_outbox import enqueue_heavy_work
        from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox

        row = enqueue_heavy_work(
            HeavyWorkOutbox.Kind.RUN_TENANT_MIGRATIONS,
            school_id=str(getattr(run, "school_id", "") or ""),
            tenant_schema=tenant_schema,
            payload={
                "tenant_schema": tenant_schema,
                "workflow_run_id": str(getattr(run, "pk", "") or ""),
            },
            idempotency_key=(
                f"migrate-schema:{tenant_schema or 'all'}:{getattr(run, 'pk', '')}"
            ),
            kick=True,
        )
        result = {
            "ok": True,
            "applied": kind,
            "tenant_schema": tenant_schema,
            "queued_async": True,
            "durable_outbox": True,
            "job_id": str(row.pk),
            "outbox_id": str(row.pk),
            "note": (
                "Tenant migrations queued on durable heavy-work outbox "
                "(never on the Flight Deck HTTP request)."
            ),
            "refresh_deck": True,
            "healing_poll_ms": 2500,
        }
        result["remediation"] = _mark_run_remediated(run=run, kind=kind, result=result)
        return result

    if kind == "clear_after_success":
        # Explicit operator clear — same gate as mark_superseded for provision.
        return apply_auto_fix_kind(run=run, kind="mark_superseded")

    if kind == "mark_superseded":
        workflow_key = getattr(run, "workflow_key", "") or ""
        if workflow_key == "tenant_school_provision":
            from apps.platform_runtime.tasks import (
                provision_failure_clearable_after_success,
            )

            if not provision_failure_clearable_after_success(run):
                return {
                    "ok": False,
                    "reason": "clear_requires_successful_provision",
                    "kind": kind,
                    "message": (
                        "Cannot clear this row until provisioning has succeeded "
                        "(school settled or a succeeded provision run exists)."
                    ),
                }
            from apps.platform_runtime.tasks import _resolve_stale_provisioned_run

            if _resolve_stale_provisioned_run(
                run,
                kind="operator_clear_after_success",
                human_action=(
                    "Cleared by operator after successful provisioning. "
                    "This historical failure no longer needs attention."
                ),
                error_message=(
                    "superseded: operator cleared after successful provision"
                ),
            ):
                return {
                    "ok": True,
                    "applied": "clear_after_success",
                    "refresh_deck": True,
                    "healing_poll_ms": 1500,
                    "operator_message": (
                        "Cleared from Flight Deck — provisioning already succeeded."
                    ),
                }
            return {
                "ok": True,
                "applied": "clear_after_success",
                "refresh_deck": True,
                "reason": "already_remediated",
                "operator_message": "Already cleared from the Flight Deck.",
            }
        result = {
            "ok": True,
            "applied": kind,
            "refresh_deck": True,
            "healing_poll_ms": 2500,
        }
        status = "cancelled" if getattr(run, "status", "") in ("running", "stuck") else ""
        result["remediation"] = _mark_run_remediated(
            run=run,
            kind=kind,
            result=result,
            status=status,
        )
        return result

    if kind == "resume_from_checkpoint":
        from apps.platform_runtime.workflow_attention_gateway import (
            SIMULATION_WORKFLOW_KEY,
        )

        if workflow_key == SIMULATION_WORKFLOW_KEY:
            from apps.platform_runtime.workflow_simulation import (
                resume_simulation_from_failure,
            )

            return resume_simulation_from_failure(run, delay_seconds=0.0)
        if workflow_key == "tenant_school_provision":
            return _chain_to_kind(
                run=run,
                kind="requeue_provision",
                source_kind=kind,
            )
        delegated = _payload_first(
            payload,
            "resume_auto_fix_kind",
            "checkpoint_auto_fix_kind",
            "recovery_auto_fix_kind",
        )
        return _chain_to_kind(run=run, kind=delegated, source_kind=kind)

    if kind == "retry_failed_step":
        if workflow_key == "tenant_school_provision":
            return _chain_to_kind(
                run=run,
                kind="requeue_provision",
                source_kind=kind,
            )
        delegated = _payload_first(
            payload,
            "retry_step_auto_fix_kind",
            "failed_step_auto_fix_kind",
            "recovery_auto_fix_kind",
        )
        return _chain_to_kind(run=run, kind=delegated, source_kind=kind)

    if kind == "replay_webhook":
        domain_delivery_id = _as_int(
            _payload_first(payload, "webhook_delivery_id", "domain_webhook_delivery_id")
        )
        platform_delivery_id = _as_int(
            _payload_first(payload, "platform_webhook_delivery_id", "event_webhook_delivery_id")
        )
        platform_event_id = _as_int(
            _payload_first(payload, "platform_event_id", "event_id")
        )
        if domain_delivery_id:
            from apps.events.models import WebhookDelivery
            from apps.events.webhooks import replay_webhook_delivery

            delivery = WebhookDelivery.objects.select_related(
                "domain_event", "subscription"
            ).filter(pk=domain_delivery_id).first()
            if delivery is None:
                return {"ok": False, "reason": "webhook_delivery_not_found", "kind": kind}
            new_delivery = replay_webhook_delivery(delivery)
            result = {
                "ok": True,
                "applied": kind,
                "webhook_delivery_id": domain_delivery_id,
                "new_webhook_delivery_id": new_delivery.pk,
                "refresh_deck": True,
                "healing_poll_ms": 2500,
            }
            result["remediation"] = _mark_run_remediated(run=run, kind=kind, result=result)
            return result
        if platform_delivery_id:
            from apps.platform_runtime.models import EventWebhookDelivery

            delivery = EventWebhookDelivery.objects.filter(pk=platform_delivery_id).first()
            if delivery is None:
                return {
                    "ok": False,
                    "reason": "platform_webhook_delivery_not_found",
                    "kind": kind,
                }
            now = timezone.now()
            EventWebhookDelivery.objects.filter(pk=delivery.pk).update(  # tenant-isolation-allow: workflow-platform-webhook-delivery-retry-by-pk
                status=EventWebhookDelivery.Status.PENDING,
                attempt_count=0,
                last_error="",
                next_retry_at=now,
                operator_resolution=None,
                operator_resolution_reason="",
                operator_resolution_by=None,
                operator_resolution_at=None,
                updated_at=now,
            )
            result = {
                "ok": True,
                "applied": kind,
                "platform_webhook_delivery_id": platform_delivery_id,
                "refresh_deck": True,
                "healing_poll_ms": 2500,
            }
            result["remediation"] = _mark_run_remediated(run=run, kind=kind, result=result)
            return result
        if platform_event_id:
            from apps.platform_runtime.event_bus import replay_event

            replay = replay_event(platform_event_id, dispatch_webhooks=True)
            if not replay.get("ok"):
                return {
                    "ok": False,
                    "reason": replay.get("error") or "platform_event_replay_failed",
                    "kind": kind,
                }
            result = {
                "ok": True,
                "applied": kind,
                "platform_event_id": platform_event_id,
                "replay": replay,
                "refresh_deck": True,
                "healing_poll_ms": 2500,
            }
            result["remediation"] = _mark_run_remediated(run=run, kind=kind, result=result)
            return result
        return {"ok": False, "reason": "missing_webhook_replay_target", "kind": kind}

    if kind == "clear_stale_lock":
        lock_key = _payload_first(payload, "lock_key", "cache_lock_key", "stale_lock_key")
        if not lock_key:
            return {"ok": False, "reason": "missing_lock_key", "kind": kind}
        if len(lock_key) > 220 or any(part in lock_key for part in ("\n", "\r", "\x00")):
            return {"ok": False, "reason": "unsafe_lock_key", "kind": kind}
        deleted = cache.delete(lock_key)
        result = {
            "ok": True,
            "applied": kind,
            "lock_key": lock_key,
            "deleted": bool(deleted),
            "refresh_deck": True,
            "healing_poll_ms": 2500,
        }
        result["remediation"] = _mark_run_remediated(run=run, kind=kind, result=result)
        return result

    if kind == "cancel_duplicate_run":
        duplicate_run_id = _as_int(
            _payload_first(payload, "duplicate_run_id", "duplicate_workflow_run_id")
        )
        now = timezone.now()
        qs = WorkflowRun.objects.filter(status__in=("running", "stuck"))  # tenant-isolation-allow: workflow-duplicate-cancel-operator-scope
        if duplicate_run_id:
            qs = qs.filter(pk=duplicate_run_id).exclude(pk=run.pk)
        else:
            idem = str(getattr(run, "idempotency_key", "") or "").strip()
            if idem:
                qs = qs.filter(idempotency_key=idem).exclude(pk=run.pk)
            else:
                qs = qs.filter(
                    workflow_key=workflow_key,
                    tenant_schema=getattr(run, "tenant_schema", "") or "",
                    school_id=getattr(run, "school_id", "") or "",
                ).exclude(pk=run.pk)
        cancelled_ids = list(qs.values_list("pk", flat=True)[:25])
        if not cancelled_ids:
            return {"ok": False, "reason": "no_duplicate_runs_found", "kind": kind}
        WorkflowRun.objects.filter(pk__in=cancelled_ids).update(  # tenant-isolation-allow: workflow-duplicate-cancel-by-pk-list
            status="cancelled",
            ended_at=now,
            last_heartbeat_at=now,
        )
        result = {
            "ok": True,
            "applied": kind,
            "cancelled_run_ids": cancelled_ids,
            "refresh_deck": True,
            "healing_poll_ms": 2500,
        }
        result["remediation"] = _mark_run_remediated(run=run, kind=kind, result=result)
        return result

    if kind == "requeue_provision" and workflow_key == "tenant_school_provision":
        school_id = str(getattr(run, "school_id", "") or payload.get("school_id") or "")
        if not school_id:
            return {"ok": False, "reason": "missing_school_id", "kind": kind}
        from apps.schools.models import School
        from apps.schools.operator_school_lens import can_operator_requeue_provisioning
        from apps.schools.tasks import dispatch_provision_school

        school = School.objects.filter(pk=school_id).first()
        if school is None:
            return {"ok": False, "reason": "school_not_found", "kind": kind}
        if not can_operator_requeue_provisioning(school):
            return {"ok": False, "reason": "requeue_not_allowed", "kind": kind}
        contact = str(payload.get("contact_email") or "").strip()
        dispatch_provision_school(school_id, contact_email=contact)
        result = {"ok": True, "applied": kind, "school_id": school_id}
        status = "cancelled" if getattr(run, "status", "") in ("running", "stuck") else ""
        result["remediation"] = _mark_run_remediated(
            run=run,
            kind=kind,
            result=result,
            status=status,
        )
        result["refresh_deck"] = True
        return result

    if kind == "resend_welcome" and workflow_key == "tenant_school_provision":
        school_id = str(getattr(run, "school_id", "") or payload.get("school_id") or "")
        if not school_id:
            return {"ok": False, "reason": "missing_school_id", "kind": kind}
        from apps.schools.models import School
        from apps.schools.welcome_email import send_welcome_email

        school = School.objects.filter(pk=school_id).first()
        if school is None:
            return {"ok": False, "reason": "school_not_found", "kind": kind}
        contact = str(payload.get("contact_email") or "").strip()
        send_welcome_email(school, contact)
        result = {"ok": True, "applied": kind, "school_id": school_id}
        result["remediation"] = _mark_run_remediated(run=run, kind=kind, result=result)
        result["refresh_deck"] = True
        return result

    if kind == "retry_dns_sync" and workflow_key == "tenant_school_provision":
        school_id = str(getattr(run, "school_id", "") or payload.get("school_id") or "")
        if not school_id:
            return {"ok": False, "reason": "missing_school_id", "kind": kind}
        from apps.schools.models import School
        from apps.schools.tasks import _provision_dns_record, sync_school_domains_to_runtime

        school = School.objects.filter(pk=school_id).first()
        if school is None:
            return {"ok": False, "reason": "school_not_found", "kind": kind}
        try:
            sync_school_domains_to_runtime(school)
            _provision_dns_record(school)
        except (OSError, ConnectionError, AttributeError, TypeError, ValueError) as exc:
            return {"ok": False, "reason": str(exc)[:200], "kind": kind}
        result = {"ok": True, "applied": kind, "school_id": school_id}
        result["remediation"] = _mark_run_remediated(run=run, kind=kind, result=result)
        result["refresh_deck"] = True
        return result

    return {
        "ok": False,
        "reason": "unsupported_fix_kind",
        "kind": kind,
        "capability": capability,
    }


# --- Stuck-run remediation (v4.04) ------------------------------------------
# A run the stuck-sweep just flagged is still "running" semantically (it never
# raised), so the failure-path remediation never fired and the card carries no
# action. Resolve a remediation here so the operator gets a one-click Retry and
# the unattended autopilot has a concrete target.

# Default auto-fix kind per workflow for a STUCK (not-yet-failed) run. Only
# workflows with a genuinely idempotent, owner-safe re-drive are listed; any
# other workflow gets an explain-only card (Cancel + visibility, no false
# "Apply" button).
STUCK_DEFAULT_FIX_BY_WORKFLOW = {
    "tenant_school_provision": "requeue_provision",
    "tenant_school_create": "requeue_provision",
    "migration_bundle_apply": "retry_failed_step",
    "migration_bundle_advance": "retry_failed_step",
    "migration_bundle_fetch_assets": "retry_failed_step",
    "marketplace_webhook_deliver_due": "replay_webhook",
    "orchestration_process_due": "retry_failed_step",
    "evals_bulk_grades": "retry_failed_step",
    "finance_auto_generate_fee_invoices": "retry_failed_step",
    "finance_auto_copy_fee_plans": "retry_failed_step",
    "tenant_school_purge": "retry_failed_step",
    "tenant_school_offboard_purge": "retry_failed_step",
}


def resolve_stuck_remediation(*, run: Any) -> dict[str, Any]:
    """Build a ``suggested_remediation`` payload for a run the sweep marked stuck.

    For workflows with a known idempotent re-drive this enables the one-click
    Retry (Apply) button AND the unattended autopilot; otherwise it returns an
    explain-only card (``human_action`` set, ``auto_fix_available`` false) so the
    operator still gets context + a Cancel action without a misleading Apply.
    """

    workflow_key = getattr(run, "workflow_key", "") or ""
    kind = STUCK_DEFAULT_FIX_BY_WORKFLOW.get(workflow_key, "")
    if kind == "requeue_provision":
        return {
            "auto_fix_available": True,
            "auto_fix_kind": kind,
            "human_action": (
                "Provisioning has stalled past its expected time. Re-queue the "
                "job — it is idempotent and resumes safely."
            ),
            "reason": "stuck",
            "source": "stuck_sweep",
            "healing_chain": (
                [
                    "cancel_duplicate_run",
                    "repair_tenant_schema_drift",
                    "requeue_provision",
                ]
                if str(getattr(run, "current_step_name", "") or "").strip()
                == "tenant_schema"
                else ["requeue_provision"]
            ),
        }
    if kind and auto_fix_kind_is_executable(kind):
        from apps.platform_runtime.workflow_recovery_playbook import (
            recovery_strategy_for_workflow,
        )

        strategy = recovery_strategy_for_workflow(workflow_key)
        return {
            "auto_fix_available": True,
            "auto_fix_kind": kind,
            "human_action": (
                f"This workflow has stalled past its expected time. "
                f"{strategy.get('summary') or 'Retry the failed step.'}"
            ),
            "reason": "stuck",
            "source": "stuck_sweep",
        }
    return {
        "auto_fix_available": False,
        "human_action": (
            "This workflow has stalled past its expected time. Review the run "
            "and cancel it or retry the originating action."
        ),
        "reason": "stuck",
        "source": "stuck_sweep",
    }
