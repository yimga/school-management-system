"""Record-level workflow telemetry on the existing WorkflowRun + Channels spine.

The pasted greenfield ``ActiveWorkflowTask`` / ``ws://localhost:8080`` samples
are not used. This module persists percent + log windows onto
``WorkflowRun.payload_summary["telemetry"]`` (tenant-scoped via
``school_id`` / ``tenant_schema``) and fans frames to a per-school Channels
group that authenticated sockets join from the request host — never a client
supplied tenant id.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)

TASK_MIGRATION_INGESTION = "MIGRATION_INGESTION"
TASK_TIMETABLE_SOLVER = "TIMETABLE_SOLVER"
TASK_EOY_ROLLOVER = "EOY_ROLLOVER"
TASK_PROCUREMENT_LOOP = "PROCUREMENT_LOOP"

LOG_HISTORY_CAP = 10

_PERCENT_QUANTUM = Decimal("0.01")
_HUNDRED = Decimal("100.00")
_ZERO = Decimal("0.00")


def workflow_telemetry_room_name(school_id: Any) -> str:
    """Per-school Channels group for live workflow progress.

    Mirrors ``substitute_market_room_name``: one room per tenant school so every
    authenticated operator on that host sees the same job. ``school_id`` comes
    from the bound socket scope / the job's school FK — never from a query string.
    """
    return f"school-{school_id}-workflow-telemetry"


def compute_percent_complete(processed: int, expected: int) -> Decimal:
    """Return a quantized 0.00–100.00 completion ratio. Never uses float()."""
    expected_n = int(expected) if expected and int(expected) > 0 else 1
    processed_n = max(int(processed or 0), 0)
    percentage = (Decimal(processed_n) / Decimal(expected_n)) * _HUNDRED
    if percentage > _HUNDRED:
        percentage = _HUNDRED
    if percentage < _ZERO:
        percentage = _ZERO
    return percentage.quantize(_PERCENT_QUANTUM)


def append_log_history(history: Any, message: str, *, now=None) -> list[str]:
    """Keep the last ``LOG_HISTORY_CAP`` trace lines. Strips PII-looking payloads."""
    stamp = (now or timezone.now()).strftime("%H:%M:%S")
    line = f"[{stamp}] {str(message or '').strip()}"[:240]  # magic-number-allow: telemetry-log-line-cap
    prior = [str(item) for item in (history or []) if str(item).strip()]
    prior.append(line)
    return prior[-LOG_HISTORY_CAP:]


def telemetry_from_payload(payload: Any) -> dict[str, Any]:
    """Read the canonical telemetry block from a WorkflowRun payload_summary."""
    if not isinstance(payload, dict):
        return {}
    block = payload.get("telemetry")
    return block if isinstance(block, dict) else {}


def _connection_schema() -> str:
    try:
        from django.db import connection

        return str(getattr(connection, "schema_name", "") or "")[:64]
    except Exception:  # noqa: BLE001 — schema is best-effort
        return ""


def _school_id_of(school: Any, *, explicit: str = "") -> str:
    if explicit:
        return str(explicit)[:40]
    if school is None:
        return ""
    return str(getattr(school, "pk", "") or "")[:40]


def _persist_telemetry(run: Any, block: dict[str, Any]) -> None:
    if run is None or getattr(run, "pk", None) is None:
        return
    try:
        from django.db import transaction

        from apps.platform_runtime.models import WorkflowRun

        with transaction.atomic():
            held = (
                # tenant-isolation-allow: workflow-telemetry-single-row-pk-update-on-held-run
                WorkflowRun.objects.select_for_update()
                .filter(pk=run.pk)
                .first()
            )
            if held is None:
                return
            payload = dict(held.payload_summary or {})
            payload["telemetry"] = block
            WorkflowRun.objects.filter(pk=held.pk).update(
                payload_summary=payload,
                last_heartbeat_at=timezone.now(),
            )
            run.payload_summary = payload
    except Exception:  # noqa: BLE001 — telemetry must never break the job
        logger.debug(
            "workflow_telemetry_persist_failed run_id=%s",
            getattr(run, "pk", "-"),
            exc_info=True,
        )


def _broadcast(school_id: str, frame: dict[str, Any]) -> int:
    if not school_id:
        return 0
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return 0
        async_to_sync(layer.group_send)(
            workflow_telemetry_room_name(school_id),
            {
                "type": "workflow.progress.update",
                **frame,
            },
        )
        return 1
    except Exception as exc:  # noqa: BLE001 — real-time layer is best-effort
        logger.debug("workflow_telemetry_broadcast_skipped: %s", exc)
        return 0


def update_and_broadcast_progress(
    *,
    processed: int,
    expected: int,
    log_message: str,
    run: Any = None,
    school: Any = None,
    school_id: str = "",
    tenant_schema: str = "",
    workflow_key: str = "",
    task_type: str = "",
    status: str = "",
) -> dict[str, Any]:
    """Persist record-level metrics and fan a live frame to the school's sockets.

    Never raises. Returns the frame payload (empty dict when skipped).
    """
    def _no_active_run() -> Any:
        return None

    try:
        from apps.platform_runtime.workflow_tracker import active_workflow_run
    except Exception:  # noqa: BLE001
        active_workflow_run = _no_active_run

    held = run if run is not None else active_workflow_run()
    sid = _school_id_of(school, explicit=school_id) or str(
        getattr(held, "school_id", "") or ""
    )
    percentage = compute_percent_complete(processed, expected)
    processed_n = max(int(processed or 0), 0)
    expected_n = max(int(expected or 0), 0)
    prior = telemetry_from_payload(getattr(held, "payload_summary", None))
    history = append_log_history(prior.get("log_history"), log_message)
    if processed_n >= expected_n and expected_n > 0:
        current_status = status or "succeeded"
    else:
        current_status = status or "running"
    block = {
        "task_type": str(task_type or prior.get("task_type") or "")[:50],
        "records_processed": processed_n,
        "records_expected": expected_n,
        "percent_complete": str(percentage),
        "log_history": history,
        "current_status": current_status,
        "updated_at": timezone.now().isoformat(),
    }
    _persist_telemetry(held, block)
    frame = {
        "event_type": "WORKFLOW_PROGRESS_UPDATE",
        "emitted_at": timezone.now().isoformat(),
        "payload": {
            "task_id": str(getattr(held, "pk", "") or ""),
            "workflow_key": str(
                workflow_key or getattr(held, "workflow_key", "") or ""
            ),
            "task_type": block["task_type"],
            "percent_complete": str(percentage),
            "processed_count": processed_n,
            "expected_count": expected_n,
            "current_status": current_status,
            "latest_trace_log": str(log_message or "")[:240],
            "log_history": history,
            "tenant_schema": str(
                tenant_schema or getattr(held, "tenant_schema", "") or _connection_schema()
            ),
            "school_id": sid,
        },
    }
    _broadcast(sid, frame)
    return frame


def enqueue_background_job(task, *args, **kwargs):
    """Prefer Celery ``apply_async``; fall back to in-process ``apply``.

    Long jobs must leave the HTTP worker so the same-tab canvas (and the
    Channels consumer) can paint. Tests with ``CELERY_TASK_ALWAYS_EAGER``
    still finish before the view returns.
    """
    try:
        return task.apply_async(args=args, kwargs=kwargs)
    except Exception:  # noqa: BLE001
        logger.debug("workflow_telemetry_enqueue_async_failed", exc_info=True)
        return task.apply(args=args, kwargs=kwargs)


def background_job_payload(async_result) -> Any:
    """Return the task result when it already finished (eager / fallback)."""
    ready = getattr(async_result, "ready", None)
    if not callable(ready) or not ready():
        return None
    getter = getattr(async_result, "get", None)
    if not callable(getter):
        return None
    try:
        return getter(propagate=False)
    except Exception:  # noqa: BLE001
        logger.debug("workflow_telemetry_enqueue_result_failed", exc_info=True)
        return None
