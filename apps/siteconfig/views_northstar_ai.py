"""North Star SLICE 11 — draft-only AI assistant API (JSON, CSRF, tenant-scoped)."""

from __future__ import annotations

import json
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import permission_required
from apps.people.models import StudentProfile
from apps.schools.security_enforcer import enforce_tenant_security
from apps.platform_runtime.ai_assistant_service import (
    draft_configuration_copilot,
    draft_policy_assistant,
    draft_report_comment_assistant,
    draft_support_knowledge_assistant,
    draft_workflow_builder_assistant,
    generate_parent_message,
    generate_report_summary,
    generate_school_insights,
    suggest_next_actions,
)


@csrf_protect
@permission_required("settings.manage", raise_exception=True)
@enforce_tenant_security(action="admin", require_school=True)
@require_http_methods(["POST"])
def northstar_ai_draft_api(request: HttpRequest) -> JsonResponse:
    """
    POST JSON { "kind": "...", "context": {}, "student_id": optional, "metrics": optional }.

    Returns draft text only — never performs send/post/schedule side effects.
    """
    school = getattr(request, "school", None)
    if not school:
        return JsonResponse(
            {"ok": False, "error": "no_school", "requires_approval": True},
            status=400,
        )
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {"ok": False, "error": "invalid_json", "requires_approval": True},
            status=400,
        )
    kind = str(body.get("kind") or "").strip().lower()
    ctx: dict[str, Any] = body.get("context") if isinstance(body.get("context"), dict) else {}
    user = getattr(request, "user", None)

    if kind == "parent_message":
        student = None
        sid = body.get("student_id")
        if sid is not None and str(sid).strip().isdigit():
            student = StudentProfile.objects.filter(
                pk=int(sid), school=school
            ).first()
        res = generate_parent_message(student, ctx, school=school, user=user)
    elif kind == "report_summary":
        student = None
        sid = body.get("student_id")
        if sid is not None and str(sid).strip().isdigit():
            student = StudentProfile.objects.filter(
                pk=int(sid), school=school
            ).first()
        res = generate_report_summary(
            student, ctx, school=school, user=user
        )
    elif kind == "school_insights":
        metrics = body.get("metrics") if isinstance(body.get("metrics"), dict) else ctx
        res = generate_school_insights(
            metrics, school=school, user=user
        )
    elif kind == "next_actions":
        res = suggest_next_actions(
            school, user=user, snapshot=ctx
        )
    elif kind == "config_copilot":
        res = draft_configuration_copilot(ctx, school=school, user=user)
    elif kind == "report_comment":
        res = draft_report_comment_assistant(ctx, school=school, user=user)
    elif kind == "policy_assistant":
        excerpt = str(ctx.get("excerpt") or "")
        res = draft_policy_assistant(
            excerpt,
            school=school,
            user=user,
            topic=str(ctx.get("topic") or ""),
        )
    elif kind == "workflow_builder":
        res = draft_workflow_builder_assistant(ctx, school=school, user=user)
    elif kind == "support_knowledge":
        res = draft_support_knowledge_assistant(ctx, school=school, user=user)
    else:
        return JsonResponse(
            {
                "ok": False,
                "error": "unknown_kind",
                "requires_approval": True,
            },
            status=400,
        )

    return JsonResponse(
        {
            "ok": True,
            "draft_text": res.get("draft_text", ""),
            "requires_approval": res.get("requires_approval", True),
            "meta": {
                "provider": (res.get("meta") or {}).get("provider"),
                "task_type": (res.get("meta") or {}).get("task_type"),
            },
        }
    )
