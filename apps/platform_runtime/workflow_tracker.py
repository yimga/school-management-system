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

import contextvars
import functools
import logging
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import timedelta
from typing import Any, Callable, Iterable, Optional

from django.utils import timezone

# Nested workflows (batch purge → per-school purge) stack so pulses land on the
# innermost active run without losing the parent envelope.
_WORKFLOW_RUN_STACK: contextvars.ContextVar[tuple[Any, ...]] = contextvars.ContextVar(
    "rmc_workflow_run_stack",
    default=(),
)


def active_workflow_run() -> Any | None:
    """Return the innermost in-flight WorkflowRun for this execution context."""

    stack = _WORKFLOW_RUN_STACK.get()
    return stack[-1] if stack else None


def push_workflow_run(run: Any) -> None:
    if run is None or getattr(run, "pk", None) is None:
        return
    stack = list(_WORKFLOW_RUN_STACK.get())
    stack.append(run)
    _WORKFLOW_RUN_STACK.set(tuple(stack))


def pop_workflow_run(run: Any | None = None) -> None:
    stack = list(_WORKFLOW_RUN_STACK.get())
    if not stack:
        return
    if run is not None and stack[-1] is not run:
        try:
            stack.remove(run)
        except ValueError:
            return
    else:
        stack.pop()
    _WORKFLOW_RUN_STACK.set(tuple(stack))


def clear_workflow_run_stack_for_tests() -> None:
    """Reset context stack between smoke assertions."""
    _WORKFLOW_RUN_STACK.set(())

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
            out[str(key)] = _truncate(value, key_lower=key_lower)
    return out


def _scrub_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _scrub(value)
    return _truncate(value)


# URL-bearing keys legitimately exceed the generic 256-char cap (a tenant
# activation link is ~120-256 chars and MUST survive intact — a truncated link
# is a dead link). Keep them whole up to a sane ceiling.
_MAX_URL_VALUE_LEN = 2048  # magic-number-allow: url-bearing payload value ceiling


def _truncate(value: Any, key_lower: str = "") -> Any:
    cap = _MAX_URL_VALUE_LEN if key_lower.endswith("_url") else _MAX_VALUE_LEN
    if isinstance(value, str) and len(value) > cap:
        return value[:cap] + "…"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, str):
        return value
    text = str(value)
    if len(text) > cap:
        return text[:cap] + "…"
    return text


def _resolve_definition(workflow_key: str) -> dict:
    """Look up the workflow in the SOT registry; degrade to empty defaults
    when no match. Never raises."""

    try:
        from apps.platform_runtime.workflow_registry import WORKFLOWS

        definition = WORKFLOWS.get(workflow_key)
        if definition is None:
            return {}
        title = getattr(definition, "title", "") or getattr(definition, "label", "") or ""
        return {
            "label": title,
            "tags": list(getattr(definition, "default_tags", []) or getattr(definition, "tags", []) or []),
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


def compute_progress_percent(
    *,
    current_step_ordinal: int = 0,
    total_steps: int = 0,
    age_seconds: int = 0,
    expected_duration_seconds: int = _DEFAULT_EXPECTED_DURATION,
) -> int:
    """Return 0–100 completion estimate for the workflow progress UI."""

    ordinal = max(int(current_step_ordinal or 0), 0)
    total = max(int(total_steps or 0), 0)
    if total > 0 and ordinal > 0:
        # In-progress step counts as partial credit (never 100 until finalize).
        pct = int(round(((ordinal - 0.35) / total) * 100))
        return max(1, min(99, pct))
    expected = max(int(expected_duration_seconds or _DEFAULT_EXPECTED_DURATION), 5)
    age = max(int(age_seconds or 0), 0)
    if age <= 0:
        return 0
    return max(1, min(95, int(round((age / expected) * 100))))


def _run_age_seconds(run: Any) -> int:
    started = getattr(run, "started_at", None)
    if started is None:
        return 0
    try:
        return max(0, int((timezone.now() - started).total_seconds()))
    except Exception:
        return 0


def serialize_workflow_run(run: Any, *, status_override: str = "") -> dict:
    """JSON shape for one active WorkflowRun row."""

    from apps.platform_runtime.workflow_degrading import resolve_display_status
    from apps.platform_runtime.workflow_sla import sla_meta_for_run
    from apps.platform_runtime.workflow_status_taxonomy import status_meta

    status = status_override or resolve_display_status(run)
    meta = status_meta(status)
    ordinal = int(getattr(run, "current_step_ordinal", 0) or 0)
    total = int(getattr(run, "total_steps", 0) or 0)
    age_seconds = _run_age_seconds(run)
    expected = int(getattr(run, "expected_duration_seconds", _DEFAULT_EXPECTED_DURATION) or _DEFAULT_EXPECTED_DURATION)
    route = ""
    try:
        from apps.platform_runtime.workflow_registry import WORKFLOWS

        definition = WORKFLOWS.get(run.workflow_key or "")
        if definition is not None:
            route = getattr(definition, "route", "") or ""
    except Exception:
        pass
    p95 = 0
    try:
        from apps.platform_runtime.workflow_duration_stats import get_p95_seconds

        p95 = get_p95_seconds(run.workflow_key or "")
    except Exception:
        p95 = 0
    return {
        "id": run.pk,
        "workflow_key": run.workflow_key,
        "workflow_label": run.workflow_label,
        "status": status,
        "display_status": meta["label"],
        "status_meta": meta,
        "registry_route": route,
        "p95_seconds": p95,
        "sla": sla_meta_for_run(run),
        "current_step_ordinal": ordinal,
        "current_step_name": run.current_step_name,
        "total_steps": total,
        "progress_percent": compute_progress_percent(
            current_step_ordinal=ordinal,
            total_steps=total,
            age_seconds=age_seconds,
            expected_duration_seconds=expected,
        ),
        "started_at": run.started_at.isoformat() if run.started_at else "",
        "expected_duration_seconds": expected,
        "tenant_schema": run.tenant_schema,
        "school_id": getattr(run, "school_id", "") or "",
        "suggested_remediation": run.suggested_remediation or {},
    }


def pulse_workflow_step(run: Any, name: str, *, payload: Optional[dict] = None) -> None:
    """Advance the visible step on a long-running workflow (no ``with`` block)."""

    if run is None:
        run = active_workflow_run()
    if run is None or getattr(run, "pk", None) is None:
        return
    try:
        from apps.platform_runtime.models import WorkflowRun, WorkflowStep

        running = WorkflowStep.objects.filter(run=run, status="running").order_by("-ordinal").first()
        if running is not None and running.name != name:
            WorkflowStep.objects.filter(pk=running.pk).update(
                status="done",
                ended_at=timezone.now(),
            )
        step = WorkflowStep.objects.filter(run=run, name=name).first()
        if step is None:
            next_ordinal = WorkflowStep.objects.filter(run=run).count() + 1
            step = WorkflowStep.objects.create(
                run=run,
                ordinal=next_ordinal,
                name=name[:80],
                label=name.replace("_", " ").title()[:160],  # magic-number-allow: string-truncation-cap
            )
        WorkflowStep.objects.filter(pk=step.pk).update(
            status="running",
            started_at=timezone.now(),
            payload_summary=_scrub(payload or {}),
        )
        # tenant-isolation-allow: workflow-pulse-single-row-pk-update-on-held-run
        WorkflowRun.objects.filter(pk=run.pk).update(
            current_step_ordinal=step.ordinal,
            current_step_name=step.name,
            last_heartbeat_at=timezone.now(),
        )
    except Exception:
        logger.exception("workflow_pulse_step_failed run_id=%s name=%s", getattr(run, "pk", "-"), name)


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


# v4.01 — stuck vs ABANDONED. is_stuck() renders a RUNNING row as "stuck" in the
# operator chip but never moves it to a terminal state, so a run whose process
# died (no more heartbeats) shows as "stuck" FOREVER and zombie rows accumulate.
# A run idle far past its stuck threshold is treated as abandoned and reaped to
# terminal FAILED.
_ABANDON_MULTIPLIER = 20  # magic-number-allow: stuck->abandoned hard cap, multiple of expected duration
_ABANDON_FLOOR_SECONDS = 3600  # magic-number-allow: never abandon a run idle < 1h regardless of expected duration


def _is_abandoned(run: Any) -> bool:
    """Return True when a RUNNING row is idle past the hard abandonment cap."""
    if getattr(run, "status", "") != "running":
        return False
    last = getattr(run, "last_heartbeat_at", None)
    if last is None:
        return False
    expected = max(int(getattr(run, "expected_duration_seconds", _DEFAULT_EXPECTED_DURATION) or 0), 5)
    cap = max(expected * _ABANDON_MULTIPLIER, _ABANDON_FLOOR_SECONDS)
    return (timezone.now() - last) > timedelta(seconds=cap)


def reap_abandoned_runs(*, tenant_schema: str = "", limit: int = 50) -> int:
    """Transition long-abandoned RUNNING rows to terminal FAILED.

    Bounds the zombie accumulation described above. Called lazily from
    ``active_runs`` so the operator chip self-cleans without a dedicated Celery
    beat. Only WRITES when a run is genuinely abandoned (rare); the scan is a
    bounded, indexed ``status='running'`` query. Returns the number reaped.
    """
    try:
        from apps.platform_runtime.models import WorkflowRun
    except Exception:  # noqa: BLE001
        return 0
    # tenant-isolation-allow: workflow-reaper-optional-tenant-schema-filter-operator-scope
    qs = WorkflowRun.objects.filter(status="running")
    if tenant_schema:
        qs = qs.filter(tenant_schema=tenant_schema)
    reaped = 0
    for run in qs.order_by("started_at")[:limit]:
        if not _is_abandoned(run):
            continue
        try:
            finalize_run(
                run,
                status="failed",
                error=TimeoutError(
                    "workflow run abandoned: no heartbeat past the stuck threshold"
                ),
                email_on_failure=False,
            )
            reaped += 1
        except Exception:  # noqa: BLE001 — reaping must never break the chip fetch
            logger.debug(
                "reap_abandoned_runs: finalize failed run_id=%s",
                getattr(run, "pk", "-"), exc_info=True,
            )
    return reaped


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
            workflow_label=label[:160],  # magic-number-allow: string-truncation-cap
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
                    label=str(name).replace("_", " ").title()[:160],  # magic-number-allow: string-truncation-cap
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

        # tenant-isolation-allow: workflow-heartbeat-single-row-pk-update-on-held-run
        WorkflowRun.objects.filter(pk=run.pk).update(last_heartbeat_at=timezone.now())
    except Exception:
        logger.warning("workflow_tracker_heartbeat_failed run_id=%s", getattr(run, "pk", "-"))


@contextmanager
def heartbeat_during(run: Any, *, interval_seconds: float = 30.0):
    """Keep ``run``'s heartbeat fresh while a single long blocking step runs.

    The stuck detector flags a run when ``now - last_heartbeat_at`` exceeds
    ``expected_duration_seconds * 1.5``. One long step with no intra-step ping — a
    fresh tenant-schema ``migrate`` of the full app set on a loaded DB, say — can
    blow past that window while genuinely progressing, false-flagging a healthy run
    as "abandoned: no heartbeat past the stuck threshold". This spawns a daemon
    thread that pings :func:`heartbeat` every ``interval_seconds`` until the block
    exits (normally or by exception), then stops and releases its DB connection.
    Best-effort: a heartbeat failure never affects the wrapped operation. A genuine
    hang is still caught — the wrapped call's own DB/statement timeout surfaces it,
    and the thread stops the moment the call returns or raises.
    """
    if run is None or getattr(run, "pk", None) is None:
        yield
        return

    stop = threading.Event()

    def _beat() -> None:
        # ``Event.wait`` returns True only once ``stop`` is set, so the first ping
        # lands one interval in — a fast op never spawns a heartbeat write at all.
        while not stop.wait(interval_seconds):
            heartbeat(run)
        try:
            from django.db import connection

            connection.close()  # release this worker thread's own DB connection
        except Exception:
            logger.debug("heartbeat_during: thread connection close failed", exc_info=True)

    thread = threading.Thread(target=_beat, name="rmc-wf-heartbeat", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=2.0)


def finalize_run(
    run: Any,
    *,
    status: str,
    error: Optional[Exception] = None,
    email_on_failure: bool = False,
) -> None:
    """Mark a run as succeeded / failed / cancelled. Computes
    ``suggested_remediation`` from the auto-fix matcher on failure.

    When ``email_on_failure=True`` and ``status='failed'``, publishes
    ``workflow.run.failed`` through the event bus so the platform email
    matrix routes an operator alert. Best-effort — never raises out of
    the finalize path.
    """

    if run is None or getattr(run, "pk", None) is None:
        return
    try:
        from apps.platform_runtime.models import WorkflowRun

        update_fields: dict[str, Any] = {
            "status": status,
            "ended_at": timezone.now(),
            "last_heartbeat_at": timezone.now(),
        }
        suggested = {}
        if status == "failed" and error is not None:
            from apps.platform_runtime.workflow_auto_fix import suggest_remediation

            error_text = str(error)[:512]
            update_fields["error_summary"] = {
                "type": type(error).__name__,
                "message": error_text,
            }
            try:
                suggested = suggest_remediation(
                    error_type=type(error).__name__,
                    error_message=error_text,
                    workflow_key=getattr(run, "workflow_key", ""),
                )
            except Exception:
                suggested = {
                    "verdict": "no_match",
                    "human_action": "Inspect the workflow run detail for raw error.",
                }
            update_fields["suggested_remediation"] = suggested
        # tenant-isolation-allow: workflow-finalize-single-row-pk-update-on-held-run
        WorkflowRun.objects.filter(pk=run.pk).update(**update_fields)

        if status in ("succeeded", "failed", "cancelled"):
            try:
                from apps.platform_runtime.workflow_duration_stats import (
                    duration_from_run,
                    record_completed_duration,
                )

                record_completed_duration(
                    workflow_key=getattr(run, "workflow_key", ""),
                    duration_seconds=duration_from_run(run),
                )
            except Exception:
                logger.debug("workflow_duration_stat_finalize_skip", exc_info=True)

        if status == "failed" and suggested.get("auto_fix_available"):
            try:
                from apps.platform_runtime.workflow_autopilot import try_auto_apply_on_failure

                try_auto_apply_on_failure(run_pk=int(run.pk))
            except Exception:
                logger.debug("workflow_autopilot_finalize_skip", exc_info=True)

        if status in ("succeeded", "failed"):
            try:
                from apps.platform_runtime.workflow_duration_stats import duration_from_run
                from apps.platform_runtime.workflow_sla import maybe_record_sla_breach

                maybe_record_sla_breach(run=run, actual_seconds=duration_from_run(run))
            except Exception:
                logger.debug("workflow_sla_finalize_skip", exc_info=True)

        # v4.00.98 Phase 6 — opt-in operator email when a workflow fails.
        if status == "failed" and email_on_failure:
            try:
                from apps.platform_runtime.event_bus import publish_event

                publish_event(
                    "workflow.run.failed",
                    {
                        "run_id": run.pk,
                        "workflow_key": getattr(run, "workflow_key", ""),
                        "workflow_label": getattr(run, "workflow_label", ""),
                        "tenant_schema": getattr(run, "tenant_schema", ""),
                        "error_type": type(error).__name__ if error else "",
                        "error_message": str(error)[:400] if error else "",
                        "suggested_remediation_text": (suggested or {}).get("human_action", ""),
                    },
                    strict_catalog=True,
                    source="workflow_tracker.finalize_run",
                )
            except Exception:
                logger.warning("workflow_tracker_email_on_failure_publish_failed", exc_info=True)
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

    if run is None:
        run = active_workflow_run()
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
                label=name.replace("_", " ").title()[:160],  # magic-number-allow: string-truncation-cap
            )
        WorkflowStep.objects.filter(pk=step.pk).update(
            status="running",
            started_at=timezone.now(),
            payload_summary=_scrub(payload or {}),
        )
        # tenant-isolation-allow: workflow-step-enter-single-row-pk-update-on-held-run
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
        # tenant-isolation-allow: workflow-step-done-single-row-pk-update-on-held-run
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
    email_on_failure: bool = False,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator wrapping a callable. Creates a WorkflowRun, finalizes on
    return / exception.

    ``request_kwarg`` names the kwarg whose value is a Django HttpRequest
    when present (defaults to ``"request"``); used to auto-pull
    tenant_schema + actor identity.

    ``payload_resolver`` (optional) receives the wrapped callable's args/kwargs
    and returns a dict to persist as ``payload_summary``. Errors in the
    resolver are swallowed.

    ``email_on_failure`` (default False) — when True, a failed run also
    publishes ``workflow.run.failed`` through the platform event bus so
    the email matrix routes an operator alert. Opt-in per workflow so noisy
    workflows don't flood the operator inbox.
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
            push_workflow_run(run)
            if request is not None:
                try:
                    setattr(request, "_rmc_workflow_run", run)
                except Exception:
                    pass
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                finalize_run(run, status="failed", error=exc, email_on_failure=email_on_failure)
                raise
            else:
                finalize_run(run, status="succeeded")
                return result
            finally:
                pop_workflow_run(run)

        # Expose the flag for testing / introspection.
        wrapper.email_on_failure = email_on_failure  # type: ignore[attr-defined]
        return wrapper

    return decorator


# Generic Celery bridge keys flash on sub-second beats; hide until this age (seconds).
_CHIP_MIN_VISIBLE_SECONDS = 4


def _visible_in_progress_chip(run: Any) -> bool:
    """Suppress ephemeral auto-tracked Celery envelopes from the assist-dock chip."""

    key = str(getattr(run, "workflow_key", "") or "")
    if not key.startswith("celery."):
        return True
    age = _run_age_seconds(run)
    if age >= _CHIP_MIN_VISIBLE_SECONDS:
        return True
    ordinal = int(getattr(run, "current_step_ordinal", 0) or 0)
    return ordinal > 1


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

    # v4.01 — self-clean abandoned zombie runs before listing so they don't
    # linger as permanent "stuck" rows in the operator chip.
    try:
        reap_abandoned_runs(tenant_schema=tenant_schema)
    except Exception:  # noqa: BLE001 — reaping must never break the chip fetch
        logger.debug("active_runs: reap_abandoned_runs failed", exc_info=True)

    # tenant-isolation-allow: workflow-active-runs-operator-scope-conditional-tenant-schema-filter
    qs = WorkflowRun.objects.filter(status__in=("running", "stuck"))
    if tenant_schema:
        qs = qs.filter(tenant_schema=tenant_schema)
    if actor_user_id:
        qs = qs.filter(actor_user_id=str(actor_user_id))
    qs = qs.order_by("-started_at")[: max(limit * 3, limit)]

    out: list[dict] = []
    for run in qs:
        if not _visible_in_progress_chip(run):
            continue
        out.append(serialize_workflow_run(run))
        if len(out) >= limit:
            break
    return out
