"""Public HTTP API for orchestration runs (Move 2).

Plain JSON over function-based views — matches the project convention. Auth is
session-based via @accept_session_or_jwt; tenant-scoping is enforced by filtering on
`request.school` (set by middleware) for non-staff callers.

Endpoints:
  POST /api/orchestration/runs/                   start a run
  GET  /api/orchestration/runs/                   list runs (filter ?status=, ?definition=, ?school=)
  GET  /api/orchestration/runs/<id>/              run detail + projected status
  GET  /api/orchestration/runs/<id>/events/       full event log
  POST /api/orchestration/runs/<id>/cancel/       cancel a pending/running run
  POST /api/orchestration/runs/<id>/retry/        retry a failed run
  GET  /api/orchestration/slo/                    latest SLO snapshot per definition
"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required

from apps.orchestration.auth_helpers import accept_session_or_jwt
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from apps.orchestration.models import (
    OrchestrationRun,
    OrchestrationSLOMetric,
    OrchestrationStepEvent,
    ProcessDefinition,
)
from apps.orchestration import event_log, versioning


def _serialize_run(run: OrchestrationRun) -> dict:
    return {
        "id": run.pk,
        "definition_code": run.definition.code,
        "definition_version": run.definition_version.version_number if run.definition_version_id else None,
        "school_id": str(run.school_id) if run.school_id else None,
        "status": run.status,
        "input_payload": run.input_payload,
        "output_payload": run.output_payload,
        "error_message": run.error_message,
        "retry_count": run.retry_count,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "sla_deadline": run.sla_deadline.isoformat() if run.sla_deadline else None,
        "sla_overdue": run.sla_overdue,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


def _parse_json_body(request) -> dict:
    if not request.body:
        return {}
    try:
        return json.loads(request.body)
    except json.JSONDecodeError:
        return {}


def _can_act(request) -> bool:
    return request.user.is_authenticated and (
        request.user.is_staff
        or request.user.is_superuser
        or (getattr(request, "school", None) is not None)
    )


@csrf_exempt
@accept_session_or_jwt
@require_http_methods(["GET", "POST"])
def runs_list_or_create(request):
    if request.method == "GET":
        qs = OrchestrationRun.objects.select_related("definition", "definition_version", "school")
        status_filter = request.GET.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        defn = request.GET.get("definition")
        if defn:
            qs = qs.filter(definition__code=defn)
        if not (request.user.is_staff or request.user.is_superuser):
            school = getattr(request, "school", None)
            if school is None:
                return JsonResponse({"results": [], "total": 0})
            qs = qs.filter(school=school)
        qs = qs.order_by("-created_at")[:200]
        return JsonResponse(
            {"results": [_serialize_run(r) for r in qs], "total": qs.count() if hasattr(qs, "count") else len(list(qs))}
        )

    if not _can_act(request):
        return JsonResponse({"error": "forbidden"}, status=403)
    body = _parse_json_body(request)
    code = (body.get("definition_code") or "").strip()
    if not code:
        return JsonResponse({"error": "definition_code is required"}, status=400)
    try:
        defn = ProcessDefinition.objects.get(code=code)
    except ProcessDefinition.DoesNotExist:
        return JsonResponse({"error": f"unknown definition_code: {code}"}, status=404)
    school = getattr(request, "school", None)
    run = OrchestrationRun.objects.create(
        definition=defn,
        school=school,
        status=OrchestrationRun.Status.PENDING,
        input_payload=body.get("input_payload") or {},
        triggered_by=request.user if request.user.is_authenticated else None,
    )
    versioning.bind_run_to_current_version(run)
    event_log.emit(run, event_type=OrchestrationStepEvent.EventType.RUN_CREATED, payload={"by": request.user.pk})
    return JsonResponse(_serialize_run(run), status=201)


@accept_session_or_jwt
@require_GET
def run_detail(request, run_id: int):
    run = get_object_or_404(OrchestrationRun, pk=run_id)
    if not (request.user.is_staff or request.user.is_superuser):
        school = getattr(request, "school", None)
        if school is None or run.school_id != getattr(school, "pk", None):
            return JsonResponse({"error": "forbidden"}, status=403)
    return JsonResponse(
        {
            "run": _serialize_run(run),
            "projection": event_log.project_status(run),
        }
    )


@accept_session_or_jwt
@require_GET
def run_events(request, run_id: int):
    run = get_object_or_404(OrchestrationRun, pk=run_id)
    if not (request.user.is_staff or request.user.is_superuser):
        school = getattr(request, "school", None)
        if school is None or run.school_id != getattr(school, "pk", None):
            return JsonResponse({"error": "forbidden"}, status=403)
    events = [
        {
            "sequence": e.sequence_number,
            "type": e.event_type,
            "step": e.step_name,
            "payload": e.payload,
            "error": e.error_message,
            "duration_ms": e.duration_ms,
            "at": e.created_at.isoformat(),
        }
        for e in event_log.events_for(run)
    ]
    return JsonResponse({"run_id": run.pk, "events": events, "count": len(events)})


@csrf_exempt
@accept_session_or_jwt
@require_POST
def run_cancel(request, run_id: int):
    run = get_object_or_404(OrchestrationRun, pk=run_id)
    if not (request.user.is_staff or request.user.is_superuser):
        school = getattr(request, "school", None)
        if school is None or run.school_id != getattr(school, "pk", None):
            return JsonResponse({"error": "forbidden"}, status=403)
    if run.status not in (OrchestrationRun.Status.PENDING, OrchestrationRun.Status.RUNNING):
        return JsonResponse({"error": f"cannot cancel run in status {run.status}"}, status=409)
    run.status = OrchestrationRun.Status.CANCELLED
    run.completed_at = timezone.now()
    run.save(update_fields=["status", "completed_at", "updated_at"])
    event_log.emit(run, event_type=OrchestrationStepEvent.EventType.RUN_CANCELLED, payload={"by": request.user.pk})
    return JsonResponse(_serialize_run(run))


@csrf_exempt
@accept_session_or_jwt
@require_POST
def run_retry(request, run_id: int):
    run = get_object_or_404(OrchestrationRun, pk=run_id)
    if not (request.user.is_staff or request.user.is_superuser):
        school = getattr(request, "school", None)
        if school is None or run.school_id != getattr(school, "pk", None):
            return JsonResponse({"error": "forbidden"}, status=403)
    if run.status != OrchestrationRun.Status.FAILED:
        return JsonResponse({"error": f"cannot retry run in status {run.status}"}, status=409)
    run.status = OrchestrationRun.Status.PENDING
    run.completed_at = None
    run.error_message = ""
    run.retry_count += 1
    run.save(update_fields=["status", "completed_at", "error_message", "retry_count", "updated_at"])
    event_log.emit(run, event_type=OrchestrationStepEvent.EventType.RETRY_SCHEDULED, payload={"by": request.user.pk})
    return JsonResponse(_serialize_run(run))


@accept_session_or_jwt
@require_GET
def slo_snapshot(request):
    """Latest SLO row per definition."""

    rows = []
    for defn in ProcessDefinition.objects.all():
        m = OrchestrationSLOMetric.objects.filter(definition=defn).order_by("-window_start").first()
        if m is None:
            continue
        rows.append(
            {
                "definition_code": defn.code,
                "window_start": m.window_start.isoformat(),
                "window_end": m.window_end.isoformat(),
                "runs_total": m.runs_total,
                "runs_succeeded": m.runs_succeeded,
                "runs_failed": m.runs_failed,
                "runs_sla_breached": m.runs_sla_breached,
                "p50_latency_ms": m.p50_latency_ms,
                "p95_latency_ms": m.p95_latency_ms,
                "p99_latency_ms": m.p99_latency_ms,
                "queue_depth_max": m.queue_depth_max,
                "success_rate": m.success_rate,
            }
        )
    return JsonResponse({"results": rows, "total": len(rows)})
