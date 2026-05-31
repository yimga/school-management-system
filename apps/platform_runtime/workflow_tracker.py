"""Workflow Progress Bus — tracker module (v4.00.96).

The opinionated, terse public surface every platform workflow uses to emit
live progress. Three primitives:

* :func:`track_workflow` — decorator wrapping a callable. Creates a WorkflowRun
  row, advances steps via the registry, and finalizes status on return /
  exception. Use it on view functions, Celery tasks, or any callable that
  represents one logical platform operation.
* :func:`workflow_step` — context manager for granular step blocks inside a
  decorated callable. Heartbeats the parent run and records the step's
  duration + payload.
* :func:`heartbeat` — explicit ping for long-running operations between steps.

Secret hygiene: every payload routed through :func:`_scrub` which drops the
platform's standard 14-key denylist before persistence. The tracker NEVER
logs or stores raw password / token / signature material.

Stuck detection: a row is "stuck" when ``now - last_heartbeat_at`` exceeds
``expected_duration_seconds * 1.5``. The SSE view + frontend chip read this
directly; the resolver below is the SOT.
"""

from __future__ import annotations

import functools
import logging
import time
import uuid
from contextlib import contextmanager
from datetime import timedelta
from typing import Any, Callable, Iterable, Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


# Mirrors the platform's standard secret-key denylist. Any payload key that
# matches (case-insensitive substring) is dropped before persistence.
_SECRET_KEY_FRAGMENTS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "hash",
        "secret",
        "token",
        "ssn",
        "dob",
        "api_key",
        "apikey",
        "private_key",
        "signature_text",
        "id_token",
        "dpop",
        "nonce",
        "code",
        "state",
        "authorization",
    }
)

# Hard cap on persisted payload values to avoid blowing up DB rows.
_MAX_VALUE_LEN = 256
# Stuck multiplier: heartbeat must be within this × expected duration.
_STUCK_MULTIPLIER = 1.5
# Default expected duration when caller omits it (seconds).
_DEFAULT_EXPECTED_DURATION = 30


def _scrub(payload: Any) -> dict:
    """Drop secret-looking keys and truncate long values. Returns a fresh
    dict; never mutates the input. Non-dict input becomes ``{"_value": ...}``
    if a primitive, otherwise ``{}``."""

    if payload is None:
        return {}
    if not isinstance(payload, dict):
        try:
            return {"_value": _truncate(payload)}
        except Exception:
            return {}
    out: dict[str, Any] = {}
    for key, value in payload.items():
        key_lower = str(key).lower()
        if any(frag in key_lower for frag in _SECRET_KEY_FRAGMENTS):
            continue
        if isinstance(value, dict):
            out[str(key)] = _scrub(value)
        elif isinstance(value, (list, tuple)):
            out[str(key)] = [_scrub_value(v) for v in list(value)[:50]]
        else:
            out[str(key)] = _truncate(value)
    return out


def _scrub_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _scrub(value)
    return _truncate(value)


def _truncate(value: Any) -> Any:
    if isinstance(value, str) and len(value) > _MAX_VALUE_LEN:
        return value[:_MAX_VALUE_LEN] + "…"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, str):
        return value
    text = str(value)
    if len(text) > _MAX_VALUE_LEN:
        return text[:_MAX_VALUE_LEN] + "…"
    return text


def _resolve_definition(workflow_key: str) -> dict:
    """Look up the workflow in the SOT registry; degrade to empty defaults
    when no match. Never raises."""

    try:
        from apps.platform_runtime.workflow_registry import WORKFLOWS

        definition = WORKFLOWS.get(workflow_key)
        if definition is None:
            return {}
        return {
            "label": getattr(definition, "label", "") or "",
            "tags": list(getattr(definition, "tags", []) or []),
            "audience": getattr(definition, "audience", "") or "",
        }
    except Exception:
        logger.warning("workflow_tracker_registry_lookup_failed", extra={"workflow_key": workflow_key})
        return {}


def _resolve_request_context(request: Any) -> dict:
    """Pull tenant_schema + actor identity from a Django HttpRequest when
    available. Tolerates missing attributes (Celery callers pass request=None)."""

    if request is None:
        return {}
    ctx: dict[str, Any] = {}
    tenant = getattr(request, "tenant", None)
    if tenant is not None:
        schema = getattr(tenant, "schema_name", "") or ""
        ctx["tenant_schema"] = str(schema)
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        ctx["actor_user_id"] = str(getattr(user, "id", "") or "")
        ctx["actor_label"] = (
            getattr(user, "get_full_name", lambda: "")() or getattr(user, "username", "") or ""
        )[:120]
    return ctx


def is_stuck(run: Any) -> bool:
    """Return True when a RUNNING row has gone past its stuck threshold."""

    if getattr(run, "status", "") != "running":
        return False
    expected = max(int(getattr(run, "expected_duration_seconds", _DEFAULT_EXPECTED_DURATION) or 0), 5)
    threshold = timedelta(seconds=expected * _STUCK_MULTIPLIER)
    last = getattr(run, "last_heartbeat_at", None)
    if last is None:
        return False
    return (timezone.now() - last) > threshold


def begin_run(
    *,
    workflow_key: str,
    steps: Iterable[str] = (),
    request: Any = None,
    tenant_schema: str = "",
    school_id: str = "",
    actor_user_id: str = "",
    actor_label: str = "",
    expected_duration_seconds: int = _DEFAULT_EXPECTED_DURATION,
    idempotency_key: str = "",
    payload: Optional[dict] = None,
) -> Any:
    """Create and return a new WorkflowRun row. Pre-seeds WorkflowStep rows
    for the declared step list. Never raises — on failure returns ``None``
    and the caller's workflow proceeds without tracking."""

    try:
        from apps.platform_runtime.models import WorkflowRun, WorkflowStep
    except Exception:
        return None

    definition = _resolve_definition(workflow_key)
    label = definition.get("label", "") or workflow_key.replace("_", " ").title()

    ctx = _resolve_request_context(request)
    tenant_schema = tenant_schema or ctx.get("tenant_schema", "")
    actor_user_id = actor_user_id or ctx.get("actor_user_id", "")
    actor_label = actor_label or ctx.get("actor_label", "")

    step_list = [s for s in steps if s]

    try:
        run = WorkflowRun.objects.create(
            workflow_key=workflow_key[:80],
            workflow_label=label[:160],
            tenant_schema=str(tenant_schema)[:64],
            school_id=str(school_id)[:40],
            actor_user_id=str(actor_user_id)[:40],
            actor_label=str(actor_label)[:120],
            total_steps=len(step_list),
            expected_duration_seconds=max(int(expected_duration_seconds or _DEFAULT_EXPECTED_DURATION), 1),
            idempotency_key=str(idempotency_key)[:128],
            payload_summary=_scrub(payload or {}),
        )
        WorkflowStep.objects.bulk_create(
            [
                WorkflowStep(
                    run=run,
                    ordinal=index + 1,
                    name=str(name)[:80],
                    label=str(name).replace("_", " ").title()[:160],
                )
                for index, name in enumerate(step_list)
            ]
        )
        return run
    except Exception:
        logger.exception("workflow_tracker_begin_run_failed key=%s", workflow_key)
        return None


def heartbeat(run: Any) -> None:
    """Update ``last_heartbeat_at`` so the stuck detector sees progress.
    Cheap — single UPDATE."""

    if run is None or getattr(run, "pk", None) is None:
        return
    try:
        from apps.platform_runtime.models import WorkflowRun

        WorkflowRun.objects.filter(pk=run.pk).update(last_heartbeat_at=timezone.now())
    except Exception:
        logger.warning("workflow_tracker_heartbeat_failed run_id=%s", getattr(run, "pk", "-"))


def finalize_run(run: Any, *, status: str, error: Optional[Exception] = None) -> None:
    """Mark a run as succeeded / failed / cancelled. Computes
    ``suggested_remediation`` from the auto-fix matcher on failure."""

    if run is None or getattr(run, "pk", None) is None:
        return
    try:
        from apps.platform_runtime.models import WorkflowRun

        update_fields: dict[str, Any] = {
            "status": status,
            "ended_at": timezone.now(),
            "last_heartbeat_at": timezone.now(),
        }
        if status == "failed" and error is not None:
            from apps.platform_runtime.workflow_auto_fix import suggest_remediation

            error_text = str(error)[:512]
            update_fields["error_summary"] = {
                "type": type(error).__name__,
                "message": error_text,
            }
            try:
                update_fields["suggested_remediation"] = suggest_remediation(
                    error_type=type(error).__name__,
                    error_message=error_text,
                    workflow_key=getattr(run, "workflow_key", ""),
                )
            except Exception:
                update_fields["suggested_remediation"] = {
                    "verdict": "no_match",
                    "human_action": "Inspect the workflow run detail for raw error.",
                }
        WorkflowRun.objects.filter(pk=run.pk).update(**update_fields)
    except Exception:
        logger.exception("workflow_tracker_finalize_failed run_id=%s", getattr(run, "pk", "-"))


@contextmanager
def workflow_step(run: Any, name: str, *, payload: Optional[dict] = None):
    """Context manager for one step inside a tracked workflow.

    Usage::

        run = begin_run(workflow_key="create_user", steps=("validate", "save", "email"))
        with workflow_step(run, "validate"):
            ...
        with workflow_step(run, "save", payload={"row_count": 1}):
            ...

    On enter: marks the step RUNNING, advances the parent run's
    ``current_step_ordinal`` + ``current_step_name``, heartbeats the parent.
    On clean exit: marks the step DONE with duration_ms.
    On exception: marks the step FAILED with the exception's string form.
    """

    if run is None or getattr(run, "pk", None) is None:
        # Tracking is best-effort; if begin_run failed, run the inner block transparently.
        yield None
        return

    from apps.platform_runtime.models import WorkflowRun, WorkflowStep

    step = None
    try:
        step = WorkflowStep.objects.filter(run=run, name=name).first()
        if step is None:
            # Caller skipped the steps= declaration on begin_run; create on demand.
            next_ordinal = (
                WorkflowStep.objects.filter(run=run).count() + 1
            )
            step = WorkflowStep.objects.create(
                run=run,
                ordinal=next_ordinal,
                name=name[:80],
                label=name.replace("_", " ").title()[:160],
            )
        WorkflowStep.objects.filter(pk=step.pk).update(
            status="running",
            started_at=timezone.now(),
            payload_summary=_scrub(payload or {}),
        )
        WorkflowRun.objects.filter(pk=run.pk).update(
            current_step_ordinal=step.ordinal,
            current_step_name=step.name,
            last_heartbeat_at=timezone.now(),
        )
    except Exception:
        logger.exception("workflow_step_enter_failed run_id=%s name=%s", run.pk, name)

    start = time.monotonic()
    try:
        yield step
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        try:
            if step is not None:
                WorkflowStep.objects.filter(pk=step.pk).update(
                    status="failed",
                    ended_at=timezone.now(),
                    duration_ms=duration_ms,
                    error_text=str(exc)[:512],
                )
        except Exception:
            logger.exception("workflow_step_fail_record_failed run_id=%s", run.pk)
        raise
    duration_ms = int((time.monotonic() - start) * 1000)
    try:
        if step is not None:
            WorkflowStep.objects.filter(pk=step.pk).update(
                status="done",
                ended_at=timezone.now(),
                duration_ms=duration_ms,
            )
        WorkflowRun.objects.filter(pk=run.pk).update(last_heartbeat_at=timezone.now())
    except Exception:
        logger.exception("workflow_step_done_record_failed run_id=%s", run.pk)


def track_workflow(
    workflow_key: str,
    *,
    steps: Iterable[str] = (),
    expected_duration_seconds: int = _DEFAULT_EXPECTED_DURATION,
    request_kwarg: str = "request",
    payload_resolver: Optional[Callable[..., dict]] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator wrapping a callable. Creates a WorkflowRun, finalizes on
    return / exception.

    ``request_kwarg`` names the kwarg whose value is a Django HttpRequest
    when present (defaults to ``"request"``); used to auto-pull
    tenant_schema + actor identity.

    ``payload_resolver`` (optional) receives the wrapped callable's args/kwargs
    and returns a dict to persist as ``payload_summary``. Errors in the
    resolver are swallowed.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            request = kwargs.get(request_kwarg)
            if request is None and args:
                # Common pattern: view(self, request, ...) — second positional.
                for arg in args[:2]:
                    if hasattr(arg, "META") and hasattr(arg, "user"):
                        request = arg
                        break
            payload: dict = {}
            if payload_resolver is not None:
                try:
                    payload = payload_resolver(*args, **kwargs) or {}
                except Exception:
                    logger.warning("workflow_tracker_payload_resolver_failed key=%s", workflow_key)

            run = begin_run(
                workflow_key=workflow_key,
                steps=steps,
                request=request,
                expected_duration_seconds=expected_duration_seconds,
                payload=payload,
                idempotency_key=str(uuid.uuid4())[:128],
            )
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                finalize_run(run, status="failed", error=exc)
                raise
            finalize_run(run, status="succeeded")
            return result

        return wrapper

    return decorator


def list_active_runs(
    *,
    tenant_schema: str = "",
    actor_user_id: str = "",
    limit: int = 25,
) -> list[dict]:
    """Return a JSON-serializable list of currently RUNNING / STUCK runs
    visible to the requesting context. Used by the SSE endpoint + the
    badge_source URL for the assist dock chip."""

    try:
        from apps.platform_runtime.models import WorkflowRun
    except Exception:
        return []

    qs = WorkflowRun.objects.filter(status__in=("running", "stuck"))
    if tenant_schema:
        qs = qs.filter(tenant_schema=tenant_schema)
    if actor_user_id:
        qs = qs.filter(actor_user_id=str(actor_user_id))
    qs = qs.order_by("-started_at")[:limit]

    out: list[dict] = []
    for run in qs:
        out.append(
            {
                "id": run.pk,
                "workflow_key": run.workflow_key,
                "workflow_label": run.workflow_label,
                "status": "stuck" if is_stuck(run) else run.status,
                "current_step_ordinal": run.current_step_ordinal,
                "current_step_name": run.current_step_name,
                "total_steps": run.total_steps,
                "started_at": run.started_at.isoformat() if run.started_at else "",
                "expected_duration_seconds": run.expected_duration_seconds,
                "tenant_schema": run.tenant_schema,
                "suggested_remediation": run.suggested_remediation or {},
            }
        )
    return out
