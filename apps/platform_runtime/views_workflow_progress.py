"""Workflow Progress Bus — HTTP surface (v4.00.96).

Endpoints mounted under ``/platform/workflow-progress/`` (see urls.py):

* ``GET  active/``            — JSON list of running + stuck runs for the
  caller's tenant + actor scope. Used by the assist-dock badge.
* ``GET  detail/<id>/``       — JSON detail incl. per-step breakdown.
* ``GET  stream/``            — Server-Sent Events stream pushing live
  updates every 2s, heartbeat every 15s, graceful close before the
  hosting worker timeout (25s default; see ``_sse_max_duration_seconds``).
* ``POST cancel/<id>/``       — Operator cancels a RUNNING / STUCK run.
* ``POST apply-fix/<id>/``    — Operator triggers the suggested
  ``auto_fix_kind`` if any (idempotent; safe no-op if nothing applies).

All views require an authenticated user. Tenant scoping is enforced
post-query via ``request.tenant.schema_name`` comparison so a user on tenant
A cannot read tenant B's runs.
"""

from __future__ import annotations

import json
import logging
import os
import time
from functools import wraps
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

logger = logging.getLogger(__name__)

_DEBUG_LOG_PATH = Path(__file__).resolve().parents[2] / "debug-0f968b.log"


def _agent_debug_log(hypothesis_id: str, location: str, message: str, data: dict | None = None) -> None:
    # #region agent log
    try:
        payload = {
            "sessionId": "0f968b",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=str) + "\n")
    except OSError:
        pass
    # #endregion


def login_required_sse(view_func):
    """Like ``login_required`` but SSE clients get 401 instead of a 302 login redirect."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            return view_func(request, *args, **kwargs)
        _agent_debug_log(
            "H1",
            "views_workflow_progress.stream_view",
            "unauthenticated_sse_rejected",
            {"path": request.path, "referer": (request.META.get("HTTP_REFERER") or "")[:120]},
        )
        return HttpResponse(status=401)

    return wrapper


# SSE tuning — must finish before the WSGI worker request timeout.
# Render often runs bare ``gunicorn`` (30s default); ``config/gunicorn.conf.py``
# uses 120s when ``-c`` is wired via ``scripts/release/render_start_web.sh``.
_SSE_TICK_SECONDS = 2.0
_SSE_HEARTBEAT_SECONDS = 15.0
_SSE_RETRY_MILLISECONDS = 2000


def _sse_max_duration_seconds() -> float:
    """Seconds to hold one SSE connection before a graceful ``bye`` frame."""

    raw = (os.environ.get("WORKFLOW_PROGRESS_SSE_MAX_SECONDS") or "").strip()
    if raw:
        try:
            return max(5.0, min(float(raw), 600.0))
        except ValueError:
            pass
    gunicorn_raw = (os.environ.get("GUNICORN_TIMEOUT") or "").strip()
    if gunicorn_raw:
        try:
            worker_timeout = float(gunicorn_raw)
            return max(5.0, min(worker_timeout - 5.0, 60.0))
        except ValueError:
            pass
    return 25.0


def _resolve_scope(request) -> tuple[str, str]:
    """Return (tenant_schema, actor_user_id) for the current request.

    Staff users on the manager host see ALL tenants (operator scope);
    tenant-host users see only their tenant's runs.
    """

    tenant = getattr(request, "tenant", None)
    schema = ""
    if tenant is not None:
        schema = str(getattr(tenant, "schema_name", "") or "")
    user = getattr(request, "user", None)
    actor_id = str(getattr(user, "id", "") or "") if user else ""

    # Manager-host staff = operator scope (no tenant filter).
    if user is not None and getattr(user, "is_staff", False) and schema in ("", "public"):
        schema = ""
    return schema, actor_id


@login_required
@require_GET
def active_runs_view(request):
    """JSON list of currently active runs visible to the caller."""

    from apps.platform_runtime.workflow_tracker import list_active_runs

    schema, actor_id = _resolve_scope(request)
    # Tenant-host users see only their own runs by default; staff see the tenant-wide set.
    is_staff = bool(getattr(request.user, "is_staff", False))
    actor_filter = "" if is_staff else actor_id
    runs = list_active_runs(tenant_schema=schema, actor_user_id=actor_filter, limit=25)

    counts = {"running": 0, "stuck": 0}
    for row in runs:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    return JsonResponse(
        {
            "generated_at": timezone.now().isoformat(),
            "scope": {
                "tenant_schema": schema or "operator",
                "actor_user_id": actor_id,
                "is_staff": is_staff,
            },
            "counts": counts,
            "runs": runs,
        }
    )


@login_required
@require_GET
def badge_view(request):
    """Lightweight badge endpoint for the assist-dock chip. Returns the
    shape ``{count, level, dot}`` the assist_dock registry contract expects."""

    from apps.platform_runtime.workflow_tracker import list_active_runs

    schema, actor_id = _resolve_scope(request)
    is_staff = bool(getattr(request.user, "is_staff", False))
    actor_filter = "" if is_staff else actor_id
    runs = list_active_runs(tenant_schema=schema, actor_user_id=actor_filter, limit=25)

    stuck = sum(1 for r in runs if r["status"] == "stuck")
    running = sum(1 for r in runs if r["status"] == "running")
    count = stuck + running

    if stuck > 0:
        level = "warning"
    elif running > 0:
        level = "info"
    else:
        level = "success"

    return JsonResponse({"count": count, "level": level, "dot": running > 0 or stuck > 0})


@login_required
@require_GET
def run_detail_view(request, run_id: int):
    """JSON detail of one run, including per-step breakdown."""

    from apps.platform_runtime.models import WorkflowRun, WorkflowStep
    from apps.platform_runtime.workflow_tracker import is_stuck

    try:
        run = WorkflowRun.objects.get(pk=run_id)
    except WorkflowRun.DoesNotExist:
        return JsonResponse({"error": "not_found"}, status=404)

    # Tenant + actor scoping.
    schema, actor_id = _resolve_scope(request)
    is_staff = bool(getattr(request.user, "is_staff", False))
    if not is_staff:
        if schema and run.tenant_schema and run.tenant_schema != schema:
            return JsonResponse({"error": "forbidden", "reason": "tenant_mismatch"}, status=403)
        if actor_id and run.actor_user_id and run.actor_user_id != actor_id:
            return JsonResponse({"error": "forbidden", "reason": "actor_mismatch"}, status=403)

    steps = []
    for s in WorkflowStep.objects.filter(run=run).order_by("ordinal"):
        steps.append(
            {
                "ordinal": s.ordinal,
                "name": s.name,
                "label": s.label,
                "status": s.status,
                "duration_ms": s.duration_ms,
                "started_at": s.started_at.isoformat() if s.started_at else "",
                "ended_at": s.ended_at.isoformat() if s.ended_at else "",
                "error_text": s.error_text,
                "payload_summary": s.payload_summary or {},
            }
        )

    return JsonResponse(
        {
            "id": run.pk,
            "workflow_key": run.workflow_key,
            "workflow_label": run.workflow_label,
            "status": "stuck" if is_stuck(run) else run.status,
            "current_step_ordinal": run.current_step_ordinal,
            "current_step_name": run.current_step_name,
            "total_steps": run.total_steps,
            "expected_duration_seconds": run.expected_duration_seconds,
            "started_at": run.started_at.isoformat() if run.started_at else "",
            "last_heartbeat_at": run.last_heartbeat_at.isoformat() if run.last_heartbeat_at else "",
            "ended_at": run.ended_at.isoformat() if run.ended_at else "",
            "tenant_schema": run.tenant_schema,
            "actor_user_id": run.actor_user_id,
            "actor_label": run.actor_label,
            "payload_summary": run.payload_summary or {},
            "error_summary": run.error_summary or {},
            "suggested_remediation": run.suggested_remediation or {},
            "steps": steps,
        }
    )


@login_required
@require_POST
def cancel_view(request, run_id: int):
    """Operator cancels a RUNNING / STUCK run."""

    from apps.platform_runtime.models import WorkflowRun

    try:
        run = WorkflowRun.objects.get(pk=run_id)
    except WorkflowRun.DoesNotExist:
        return JsonResponse({"error": "not_found"}, status=404)

    schema, actor_id = _resolve_scope(request)
    is_staff = bool(getattr(request.user, "is_staff", False))
    if not is_staff:
        if schema and run.tenant_schema and run.tenant_schema != schema:
            return JsonResponse({"error": "forbidden"}, status=403)
        if actor_id and run.actor_user_id and run.actor_user_id != actor_id:
            return JsonResponse({"error": "forbidden"}, status=403)

    if run.status not in ("running", "stuck"):
        return JsonResponse({"ok": False, "reason": "not_in_cancellable_state", "status": run.status})

    WorkflowRun.objects.filter(pk=run.pk).update(
        status="cancelled",
        ended_at=timezone.now(),
        last_heartbeat_at=timezone.now(),
    )
    return JsonResponse({"ok": True, "status": "cancelled"})


@login_required
@require_POST
def apply_fix_view(request, run_id: int):
    """Apply the run's suggested ``auto_fix_kind`` if any. The actual fix
    handlers are intentionally narrow + idempotent. Unknown kinds return
    ``{"ok": False, "reason": "unsupported_fix_kind"}``.
    """

    from apps.platform_runtime.models import WorkflowRun

    try:
        run = WorkflowRun.objects.get(pk=run_id)
    except WorkflowRun.DoesNotExist:
        return JsonResponse({"error": "not_found"}, status=404)

    schema, actor_id = _resolve_scope(request)
    is_staff = bool(getattr(request.user, "is_staff", False))
    if not is_staff:
        if schema and run.tenant_schema and run.tenant_schema != schema:
            return JsonResponse({"error": "forbidden"}, status=403)

    remediation = run.suggested_remediation or {}
    if not remediation.get("auto_fix_available"):
        return JsonResponse({"ok": False, "reason": "no_auto_fix_available"})

    kind = str(remediation.get("auto_fix_kind", ""))
    workflow_key = run.workflow_key

    if kind == "suggest_alternate_slug":
        # Generate three alternate slugs from the original.
        base = (run.payload_summary or {}).get("slug") or workflow_key
        alternates = [f"{base}-2026", f"{base}-academy", f"{base}-school"]
        return JsonResponse({"ok": True, "applied": "suggest_alternate_slug", "alternates": alternates})

    if kind in ("retry_once_with_backoff", "retry_after_rate_limit", "refresh_oauth_token_and_retry"):
        # Mark the run for retry; the caller's workflow re-invokes on the next request.
        WorkflowRun.objects.filter(pk=run.pk).update(
            status="running",
            last_heartbeat_at=timezone.now(),
            payload_summary={**(run.payload_summary or {}), "retry_requested_at": timezone.now().isoformat(), "retry_kind": kind},
        )
        return JsonResponse({"ok": True, "applied": kind, "note": "Run marked for retry. Re-invoke the original action."})

    return JsonResponse({"ok": False, "reason": "unsupported_fix_kind", "kind": kind})


def _format_sse_frame(event_id, kind: str, payload: dict) -> bytes:
    parts: list[str] = []
    if event_id is not None:
        parts.append(f"id: {event_id}")
    if kind:
        parts.append(f"event: {kind}")
    parts.append("data: " + json.dumps(payload, default=str))
    parts.append("")
    return ("\n".join(parts) + "\n").encode("utf-8")


@login_required_sse
@require_GET
def stream_view(request):
    """SSE stream of the caller's active workflow runs.

    Tick every 2s with the current snapshot; heartbeat comment every 15s;
    graceful close before the worker timeout so sync Gunicorn workers are not
    SIGKILL'd. Client reconnects on ``bye`` or transport error.
    """

    from apps.platform_runtime.workflow_tracker import list_active_runs

    schema, actor_id = _resolve_scope(request)
    is_staff = bool(getattr(request.user, "is_staff", False))
    actor_filter = "" if is_staff else actor_id
    max_duration = _sse_max_duration_seconds()
    _agent_debug_log(
        "H4",
        "views_workflow_progress.stream_view",
        "sse_stream_open",
        {
            "max_duration_s": max_duration,
            "is_staff": is_staff,
            "path": request.path,
        },
    )

    def _stream():
        yield f"retry: {_SSE_RETRY_MILLISECONDS}\n\n".encode("utf-8")
        deadline = time.monotonic() + max_duration
        last_heartbeat = time.monotonic()
        last_snapshot_hash = None
        event_seq = 0
        # Initial snapshot frame.
        try:
            runs = list_active_runs(tenant_schema=schema, actor_user_id=actor_filter, limit=25)
        except Exception:
            runs = []
        event_seq += 1
        last_snapshot_hash = _stable_hash(runs)
        yield _format_sse_frame(event_seq, "snapshot", {"runs": runs, "ts": timezone.now().isoformat()})
        while time.monotonic() < deadline:
            time.sleep(_SSE_TICK_SECONDS)
            try:
                runs = list_active_runs(tenant_schema=schema, actor_user_id=actor_filter, limit=25)
                current_hash = _stable_hash(runs)
                if current_hash != last_snapshot_hash:
                    event_seq += 1
                    last_snapshot_hash = current_hash
                    yield _format_sse_frame(event_seq, "snapshot", {"runs": runs, "ts": timezone.now().isoformat()})
                if time.monotonic() - last_heartbeat >= _SSE_HEARTBEAT_SECONDS:
                    last_heartbeat = time.monotonic()
                    yield b": ping\n\n"
            except Exception:
                logger.exception("workflow_progress_stream_tick_failed")
                yield b": error\n\n"
                break
        # Final close frame so clients with strict parsers don't hang.
        yield _format_sse_frame(event_seq + 1, "bye", {"reason": "graceful_close"})

    response = StreamingHttpResponse(_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def _stable_hash(runs: list) -> str:
    """Cheap content hash to detect snapshot changes between SSE ticks."""

    try:
        return json.dumps(
            [
                (r["id"], r["status"], r["current_step_ordinal"], r["current_step_name"])
                for r in runs
            ],
            sort_keys=True,
        )
    except Exception:
        return str(time.monotonic())
