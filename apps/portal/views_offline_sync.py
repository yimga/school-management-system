"""
Offline sync queue and conflict resolution (server-backed; complements client Dexie/SW queue).
"""

from __future__ import annotations

import json
import logging
from typing import Any

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

from apps.accounts.permissions import tenant_operator_hub_eligible
from apps.platform_runtime.models import OfflineAction
from apps.platform_runtime.offline_queue import (
    enqueue_offline_action,
    process_offline_queue,
    resolve_conflict_choice,
    retry_failed_actions,
)

logger = logging.getLogger(__name__)
_MAX_JSON_BYTES = 512 * 1024


def _school_operator_scope(request: HttpRequest) -> bool:
    return tenant_operator_hub_eligible(request.user)


def _filter_offline_queryset(qs, request: HttpRequest):
    at = (request.GET.get("action_type") or "").strip()
    if at:
        qs = qs.filter(action_type=at)
    uid = request.GET.get("user")
    if uid and str(uid).isdigit():
        qs = qs.filter(user_id=int(uid))
    cid = request.GET.get("classroom_id")
    if cid and str(cid).isdigit():
        qs = qs.filter(payload__classroom_id=int(cid))
    sid = request.GET.get("student_id")
    if sid and str(sid).isdigit():
        qs = qs.filter(payload__student_id=int(sid))
    return qs


def _filter_submitters_for_school(school_id: int, limit: int = 80):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    ids = list(
        OfflineAction.objects.filter(school_id=school_id)
        .values_list("user_id", flat=True)
        .distinct()[:limit]
    )
    rows = []
    for u in User.objects.filter(pk__in=ids).order_by("username"):
        rows.append({"id": u.pk, "username": u.get_username()})
    return rows


def _conflict_compare(card_row: OfflineAction) -> tuple[dict[str, Any], dict[str, Any]]:
    """Human-readable server vs offline snapshots for conflict UI."""
    det = card_row.conflict_details or {}
    pay = card_row.payload or {}
    server_vals: dict[str, Any] = {}
    local_vals: dict[str, Any] = {}
    at = card_row.action_type
    if at == OfflineAction.ActionType.ATTENDANCE:
        server_vals["status"] = det.get("server_status")
        local_vals["status"] = det.get("client_status") or pay.get("status")
        server_vals["remarks"] = det.get("server_remarks")
        local_vals["remarks"] = pay.get("remarks")
        server_vals["date"] = pay.get("date")
        local_vals["date"] = pay.get("date")
        server_vals["student_id"] = pay.get("student_id")
        local_vals["student_id"] = pay.get("student_id")
        server_vals["classroom_id"] = pay.get("classroom_id")
        local_vals["classroom_id"] = pay.get("classroom_id")
    elif at == OfflineAction.ActionType.GRADING:
        for k in (
            "subject_assignment_id",
            "student_id",
            "seq1_score",
            "seq2_score",
            "exam_score",
        ):
            local_vals[k] = pay.get(k)
        local_vals["remarks"] = pay.get("remarks")
        if det:
            server_vals.update({str(k): v for k, v in det.items()})
    elif at == OfflineAction.ActionType.PAYMENT_RECEIPT:
        local_vals["amount"] = pay.get("amount")
        local_vals["invoice_id"] = pay.get("invoice_id")
        local_vals["payment_method"] = pay.get("payment_method")
        if det:
            server_vals.update({str(k): v for k, v in det.items()})
    elif at == OfflineAction.ActionType.NOTES_REPORT:
        local_vals["title"] = pay.get("title")
        local_vals["body_preview"] = (pay.get("body") or "")[:240]
        local_vals["student_id"] = pay.get("student_id")
        if det:
            server_vals.update({str(k): v for k, v in det.items()})
    else:
        server_vals.update({str(k): v for k, v in det.items()})
        local_vals.update({str(k): v for k, v in pay.items()})
    return server_vals, local_vals


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

    operator_scope = _school_operator_scope(request)
    uid_filter = None if operator_scope else request.user.pk

    if request.method == "POST":
        if request.POST.get("action") == "process_queue":
            summary = process_offline_queue(
                school_id=school.pk,
                user_id=uid_filter,
                limit=75,
            )
            messages.info(
                request,
                f"Processed {summary['processed']}: {summary['synced']} synced, "
                f"{summary['failed']} failed, {summary['conflicts']} conflicts.",
            )
        elif request.POST.get("action") == "retry_failed":
            n = retry_failed_actions(
                school_id=school.pk,
                user_id=uid_filter,
                max_retries=5,
                limit=200,
            )
            messages.info(request, f"Re-queued {n} failed item(s).")

    base_qs = OfflineAction.objects.filter(school_id=school.pk).select_related(
        "user"
    )
    if not operator_scope:
        base_qs = base_qs.filter(user_id=request.user.pk)
    base_qs = _filter_offline_queryset(base_qs, request)

    rows = list(base_qs.order_by("-created_at")[:200])
    queued_only = list(
        base_qs.filter(status=OfflineAction.Status.QUEUED).order_by("-created_at")[
            :120
        ]
    )
    syncing_actions = list(
        base_qs.filter(status=OfflineAction.Status.SYNCING).order_by("-updated_at")[
            :120
        ]
    )
    failed_actions = list(
        base_qs.filter(status=OfflineAction.Status.FAILED).order_by("-created_at")[
            :120
        ]
    )
    conflict_actions = list(
        base_qs.filter(status=OfflineAction.Status.CONFLICT).order_by("-updated_at")[
            :120
        ]
    )
    synced_actions = list(
        base_qs.filter(status=OfflineAction.Status.SYNCED).order_by("-updated_at")[:60]
    )

    count_qs = OfflineAction.objects.filter(school_id=school.pk)
    if not operator_scope:
        count_qs = count_qs.filter(user_id=request.user.pk)
    count_qs = _filter_offline_queryset(count_qs, request)

    pending = count_qs.filter(status=OfflineAction.Status.QUEUED).count()
    syncing_n = count_qs.filter(status=OfflineAction.Status.SYNCING).count()
    failed = count_qs.filter(status=OfflineAction.Status.FAILED).count()
    conflict_n = count_qs.filter(status=OfflineAction.Status.CONFLICT).count()

    submitters = (
        _filter_submitters_for_school(school.pk) if operator_scope else []
    )

    return render(
        request,
        "portal/offline_sync_queue.html",
        {
            "offline_actions": rows,
            "queued_actions": queued_only,
            "syncing_actions": syncing_actions,
            "failed_actions": failed_actions,
            "conflict_actions": conflict_actions,
            "synced_actions": synced_actions,
            "pending_count": pending,
            "syncing_count": syncing_n,
            "failed_count": failed,
            "conflict_count": conflict_n,
            "operator_offline_scope": operator_scope,
            "submitters": submitters,
            "action_type_choices": OfflineAction.ActionType.choices,
            "filter_action_type": request.GET.get("action_type") or "",
            "filter_user": request.GET.get("user") or "",
            "filter_classroom_id": request.GET.get("classroom_id") or "",
            "filter_student_id": request.GET.get("student_id") or "",
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def offline_sync_conflicts(request: HttpRequest) -> HttpResponse:
    school, err = _require_school(request)
    if err:
        return err

    operator_scope = _school_operator_scope(request)

    if request.method == "POST":
        action_id = request.POST.get("action_id")
        choice = request.POST.get("resolution")
        if action_id and choice:
            result = resolve_conflict_choice(
                action_id=int(action_id),
                school_id=school.pk,
                user_id=request.user.pk,
                choice=str(choice),
                school_operator=operator_scope,
            )
            if result.get("ok"):
                messages.success(request, "Resolution recorded.")
            else:
                messages.error(
                    request,
                    result.get("error") or "Could not resolve.",
                )
            return redirect("portal:offline_sync_conflicts")

    conflict_qs = OfflineAction.objects.filter(
        school_id=school.pk,
        status=OfflineAction.Status.CONFLICT,
    ).select_related("user")
    if not operator_scope:
        conflict_qs = conflict_qs.filter(user_id=request.user.pk)
    conflicts = list(conflict_qs.order_by("-updated_at")[:100])

    conflict_cards = []
    for c in conflicts:
        srv, loc = _conflict_compare(c)
        conflict_cards.append(
            {
                "row": c,
                "server_vals": srv,
                "local_vals": loc,
                "audit_trail": list((c.sync_metadata or {}).get("resolution_audits") or [])[
                    -10:
                ],
            }
        )

    return render(
        request,
        "portal/offline_sync_conflicts.html",
        {
            "conflict_cards": conflict_cards,
            "operator_offline_scope": operator_scope,
        },
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

    if data.get("tenant_id") is not None or data.get("school_id") is not None:
        return JsonResponse({"ok": False, "error": "tenant_from_session_only"}, status=400)

    from apps.platform_runtime.offline_action_types import (
        OfflineActionType,
        SODP_TO_LEGACY,
        normalize_action_type,
        validate_offline_payload,
    )

    action_type = normalize_action_type(str(data.get("action_type") or ""))
    legacy = {c for c, _ in OfflineAction.ActionType.choices}
    if action_type not in OfflineActionType.values and action_type not in legacy:
        return JsonResponse({"ok": False, "error": "invalid_action_type"}, status=400)

    stored_type = SODP_TO_LEGACY.get(action_type, action_type)
    if stored_type not in legacy:
        return JsonResponse({"ok": False, "error": "invalid_action_type"}, status=400)

    payload = data.get("payload")
    if payload is not None and not isinstance(payload, dict):
        return JsonResponse({"ok": False, "error": "payload_must_be_object"}, status=400)

    validation_errors = validate_offline_payload(action_type, payload if isinstance(payload, dict) else {})
    if validation_errors:
        return JsonResponse(
            {"ok": False, "error": "invalid_payload", "details": validation_errors},
            status=400,
        )

    idem = str(data.get("idempotency_key") or "")[:128]
    try:
        row = enqueue_offline_action(
            user_id=request.user.pk,
            school_id=school.pk,
            action_type=stored_type,
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


@login_required
@require_http_methods(["POST"])
def api_offline_apply_batch(request: HttpRequest) -> JsonResponse:
    """Preflight client delta batches through ``apply_remote`` + conflict_resolver policies."""
    school, err = _require_school(request)
    if err:
        return JsonResponse({"ok": False, "error": "no_school"}, status=403)

    data = _parse_json(request)
    if not data:
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    changes = data.get("changes")
    if not isinstance(changes, list):
        return JsonResponse({"ok": False, "error": "changes_must_be_list"}, status=400)

    device_id = str(data.get("device_id") or "")[:128] or None
    from apps.platform_runtime.offline_queue import apply_client_batch

    result = apply_client_batch(
        school.pk,
        request.user.pk,
        changes,
        device_id=device_id,
    )
    conflicts = result.get("conflicts") or []
    manual_review = sum(1 for row in conflicts if row.get("policy") == "manual_review")
    return JsonResponse(
        {
            "ok": True,
            **result,
            "conflict_count": len(conflicts),
            "manual_review_count": manual_review,
        }
    )
