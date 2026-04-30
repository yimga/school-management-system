"""
Offline sync queue and conflict resolution (server-backed; complements client Dexie/SW queue).
"""

from __future__ import annotations

import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.platform_runtime.models import OfflineAction
from apps.platform_runtime.offline_queue import (
    enqueue_offline_action,
    process_offline_queue,
    resolve_conflict_choice,
    retry_failed_actions,
)

logger = logging.getLogger(__name__)
_MAX_JSON_BYTES = 512 * 1024


def _require_school(request: HttpRequest):
    school = getattr(request, "school", None)
    if school is None:
        return None, HttpResponseForbidden("School context required.")
    return school, None


@login_required
@require_http_methods(["GET", "POST"])
def offline_sync_queue(request: HttpRequest) -> HttpResponse:
    school, err = _require_school(request)
    if err:
        return err

    if request.method == "POST":
        if request.POST.get("action") == "process_queue":
            summary = process_offline_queue(
                school_id=school.pk,
                user_id=request.user.pk,
                limit=50,
            )
            messages.info(
                request,
                f"Processed {summary['processed']}: {summary['synced']} synced, "
                f"{summary['failed']} failed, {summary['conflicts']} conflicts.",
            )
        elif request.POST.get("action") == "retry_failed":
            n = retry_failed_actions(
                school_id=school.pk,
                user_id=request.user.pk,
                max_retries=5,
                limit=100,
            )
            messages.info(request, f"Re-queued {n} failed item(s).")

    rows = (
        OfflineAction.objects.filter(
            school_id=school.pk,
            user_id=request.user.pk,
        )
        .order_by("-created_at")[:200]
    )
    pending = OfflineAction.objects.filter(
        school_id=school.pk,
        user_id=request.user.pk,
        status=OfflineAction.Status.QUEUED,
    ).count()
    failed = OfflineAction.objects.filter(
        school_id=school.pk,
        user_id=request.user.pk,
        status=OfflineAction.Status.FAILED,
    ).count()
    conflict_n = OfflineAction.objects.filter(
        school_id=school.pk,
        user_id=request.user.pk,
        status=OfflineAction.Status.CONFLICT,
    ).count()

    return render(
        request,
        "portal/offline_sync_queue.html",
        {
            "offline_actions": rows,
            "pending_count": pending,
            "failed_count": failed,
            "conflict_count": conflict_n,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def offline_sync_conflicts(request: HttpRequest) -> HttpResponse:
    school, err = _require_school(request)
    if err:
        return err

    if request.method == "POST":
        action_id = request.POST.get("action_id")
        choice = request.POST.get("resolution")
        if action_id and choice:
            result = resolve_conflict_choice(
                action_id=int(action_id),
                school_id=school.pk,
                user_id=request.user.pk,
                choice=str(choice),
            )
            if result.get("ok"):
                messages.success(request, "Resolution recorded.")
            else:
                messages.error(
                    request,
                    result.get("error") or "Could not resolve.",
                )
            return redirect("portal:offline_sync_conflicts")

    conflicts = list(
        OfflineAction.objects.filter(
            school_id=school.pk,
            user_id=request.user.pk,
            status=OfflineAction.Status.CONFLICT,
        ).order_by("-updated_at")[:100]
    )

    return render(
        request,
        "portal/offline_sync_conflicts.html",
        {"conflicts": conflicts},
    )


def _parse_json(request: HttpRequest) -> dict | None:
    if len(request.body) > _MAX_JSON_BYTES:
        return None
    try:
        data = json.loads(request.body.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return None


@login_required
@require_http_methods(["POST"])
def api_offline_enqueue(request: HttpRequest) -> JsonResponse:
    """
    Accept one offline action from the browser outbox (CSRF-protected POST).
    Tenant id comes from ``request.school`` only.
    """
    school, err = _require_school(request)
    if err:
        return JsonResponse({"ok": False, "error": "no_school"}, status=403)

    data = _parse_json(request)
    if not data:
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    action_type = str(data.get("action_type") or "").strip()
    allowed = {c for c, _ in OfflineAction.ActionType.choices}
    if action_type not in allowed:
        return JsonResponse({"ok": False, "error": "invalid_action_type"}, status=400)

    payload = data.get("payload")
    if payload is not None and not isinstance(payload, dict):
        return JsonResponse({"ok": False, "error": "payload_must_be_object"}, status=400)

    idem = str(data.get("idempotency_key") or "")[:128]
    try:
        row = enqueue_offline_action(
            user_id=request.user.pk,
            school_id=school.pk,
            action_type=action_type,
            payload=payload if isinstance(payload, dict) else {},
            idempotency_key=idem,
        )
    except Exception as exc:
        logger.warning("api_offline_enqueue failed: %s", exc)
        return JsonResponse({"ok": False, "error": "enqueue_failed"}, status=500)

    return JsonResponse({"ok": True, "id": row.pk, "status": row.status})


@login_required
@require_http_methods(["POST"])
def api_offline_process(request: HttpRequest) -> JsonResponse:
    """Process queued ``OfflineAction`` rows for this user + school (server replay)."""
    school, err = _require_school(request)
    if err:
        return JsonResponse({"ok": False, "error": "no_school"}, status=403)

    summary = process_offline_queue(
        school_id=school.pk,
        user_id=request.user.pk,
        limit=50,
    )
    return JsonResponse({"ok": True, **summary})
