"""Bulk JSON APIs for control-plane operator list surfaces."""

from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.compliance.models_audit import AuditLog
from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_FLEET,
    PLATFORM_SCOPE_SECURITY_WRITE,
    PLATFORM_SCOPE_TEAM_MANAGE,
    require_platform_scope,
    user_has_platform_scope,
)
from apps.schools.bulk_operator_actions import (
    ACTION_CONFIRM_PHRASES as SCHOOL_CONFIRM_PHRASES,
    bulk_apply_school_actions,
    parse_school_id_list,
)
from apps.schools.bulk_operator_team_actions import (
    ACTION_CONFIRM_PHRASES as TEAM_CONFIRM_PHRASES,
    bulk_apply_operator_team_actions,
    parse_operator_user_id_list,
)
from apps.schools.control_plane import log_control_plane_action

_SECURITY_WRITE_ACTIONS = frozenset(
    {"purge_dry_run", "dual_approve_primary", "dual_approve_second"}
)
_EXPORT_ACTIONS = frozenset({"export"})


def _parse_json_body(request) -> dict:
    if not request.body:
        return {}
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _audit_bulk_schools(request, *, action: str, school_ids, outcome: dict) -> None:
    sensitivity = AuditLog.Sensitivity.HIGH
    audit_action = AuditLog.Action.UPDATE
    if action in _EXPORT_ACTIONS:
        audit_action = AuditLog.Action.EXPORT
        sensitivity = AuditLog.Sensitivity.CRITICAL
    elif action in _SECURITY_WRITE_ACTIONS:
        sensitivity = AuditLog.Sensitivity.CRITICAL
    log_control_plane_action(
        request,
        audit_action,
        "School",
        ",".join(str(sid) for sid in school_ids[:5]),
        object_repr=f"Bulk school action: {action}",
        reason=(
            f"Bulk school action {action} "
            f"({outcome['succeeded']}/{outcome['processed']} succeeded)"
        ),
        sensitivity=sensitivity,
    )


@require_http_methods(["POST"])
@require_platform_scope(PLATFORM_SCOPE_FLEET)
def api_bulk_schools(request):
    payload = _parse_json_body(request)
    action = str(payload.get("action") or request.POST.get("action") or "").strip()
    reason = str(payload.get("reason") or request.POST.get("reason") or "").strip()
    confirm_phrase = str(
        payload.get("confirm_phrase") or request.POST.get("confirm_phrase") or ""
    ).strip()
    school_ids = parse_school_id_list(payload.get("ids") or request.POST.getlist("ids"))

    if action in _SECURITY_WRITE_ACTIONS and not user_has_platform_scope(
        request.user, PLATFORM_SCOPE_SECURITY_WRITE
    ):
        return JsonResponse(
            {"ok": False, "error": "platform.security.write scope required."},
            status=403,
        )

    try:
        outcome = bulk_apply_school_actions(
            school_ids=school_ids,
            action=action,
            reason=reason,
            actor=request.user,
            confirm_phrase=confirm_phrase,
        )
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    _audit_bulk_schools(request, action=action, school_ids=school_ids, outcome=outcome)
    status = 200 if outcome.get("ok") else 422
    return JsonResponse(
        {
            **outcome,
            "confirm_phrase_hint": SCHOOL_CONFIRM_PHRASES.get(action, ""),
        },
        status=status,
    )


@require_http_methods(["POST"])
@require_platform_scope(PLATFORM_SCOPE_TEAM_MANAGE)
def api_bulk_operators(request):
    payload = _parse_json_body(request)
    action = str(payload.get("action") or request.POST.get("action") or "").strip()
    confirm_phrase = str(
        payload.get("confirm_phrase") or request.POST.get("confirm_phrase") or ""
    ).strip()
    tier = str(payload.get("tier") or request.POST.get("tier") or "").strip()
    user_ids = parse_operator_user_id_list(
        payload.get("ids") or request.POST.getlist("ids")
    )

    try:
        outcome = bulk_apply_operator_team_actions(
            user_ids=user_ids,
            action=action,
            actor=request.user,
            confirm_phrase=confirm_phrase,
            tier=tier,
        )
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    from apps.platform_runtime.operator_identity import audit_operator_action

    audit_operator_action(
        request,
        action="UPDATE",
        model_name="PlatformOperatorProfile",
        object_id=",".join(str(uid) for uid in user_ids[:5]),
        object_repr=f"Bulk operator action: {action}",
        new_values={
            "processed": outcome["processed"],
            "succeeded": outcome["succeeded"],
            "tier": tier or None,
        },
    )
    status = 200 if outcome.get("ok") else 422
    return JsonResponse(
        {
            **outcome,
            "confirm_phrase_hint": TEAM_CONFIRM_PHRASES.get(action, ""),
        },
        status=status,
    )
