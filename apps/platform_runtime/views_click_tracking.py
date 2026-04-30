"""HTTP surface for click instrumentation (tenant-bound)."""

from __future__ import annotations

import json
import logging
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from apps.platform_runtime.click_tracking import (
    get_click_system_public_context,
    get_median_clicks_before_after,
    record_click_event as persist_click_event,
)
from apps.platform_runtime.models import ClickTrackEvent

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 65536


def _json_body(request) -> dict[str, Any]:
    if len(request.body) > MAX_BODY_BYTES:
        raise ValueError("payload_too_large")
    return json.loads(request.body.decode("utf-8"))


@login_required
@require_POST
def record_click_event(request):
    """
    Record click / task_start / task_complete. Host must resolve ``request.school`` (tenant).
    """
    school = getattr(request, "school", None)
    if not school:
        return JsonResponse({"ok": False, "error": "no_tenant_context"}, status=400)
    try:
        data = _json_body(request)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    kind = (data.get("kind") or data.get("event_kind") or "").strip()
    task_code = (data.get("task_code") or data.get("task") or "").strip()
    session_run_id = (data.get("session_run_id") or data.get("run_id") or "").strip()
    phase = (data.get("phase") or "").strip().lower()
    task_step = str(data.get("task_step") or data.get("step") or "")[:128]
    action_code = str(data.get("action") or data.get("action_code") or "")[:128]
    path = str(data.get("path") or "")[:512]
    screen_token = str(data.get("screen_token") or data.get("screen") or "")[:128]
    extra = data.get("extra") if isinstance(data.get("extra"), dict) else {}

    allowed_kinds = {k for k, _ in ClickTrackEvent.Kind.choices}
    if kind not in allowed_kinds:
        return JsonResponse({"ok": False, "error": "invalid_kind"}, status=400)
    if not task_code or not session_run_id:
        return JsonResponse({"ok": False, "error": "task_and_session_required"}, status=400)
    allowed_phases = {ClickTrackEvent.Phase.BASELINE, ClickTrackEvent.Phase.CURRENT}
    if phase not in allowed_phases:
        return JsonResponse({"ok": False, "error": "invalid_phase"}, status=400)

    try:
        persist_click_event(
            school_id=school.id,
            user_id=request.user.id if request.user.is_authenticated else None,
            kind=kind,
            task_code=task_code,
            session_run_id=session_run_id,
            phase=phase,
            task_step=task_step,
            action_code=action_code,
            path=path,
            screen_token=screen_token,
            extra=extra,
        )
    except Exception as e:
        logger.warning("record_click_event persist failed: %s", e)
        return JsonResponse({"ok": False, "error": "persist_failed"}, status=500)

    return JsonResponse({"ok": True})


@login_required
def click_measurement_dashboard(request):
    """Median clicks before/after — tenant scoped."""
    school = getattr(request, "school", None)
    if not school:
        return HttpResponseForbidden("Tenant context required.")

    stats = get_median_clicks_before_after(school.id)
    return render(
        request,
        "platform_runtime/click_measurement_dashboard.html",
        {
            "click_stats": stats,
            "tracked_tasks": list(stats["per_task"].keys()),
            "click_system": get_click_system_public_context(),
        },
    )
