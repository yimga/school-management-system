"""Autopilot policy HTTP API (wave 2 completion)."""

from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from services.http_auth_guards import login_required_api

from apps.platform_runtime.views_workflow_progress import _resolve_scope


@login_required_api
@require_GET
def autopilot_policy_view(request):
    """Return effective autopilot policy for a workflow key."""

    workflow_key = (request.GET.get("workflow_key") or "").strip()[:80]
    if not workflow_key:
        return JsonResponse({"error": "workflow_key_required"}, status=400)
    if not getattr(request.user, "is_staff", False):
        return JsonResponse({"error": "forbidden"}, status=403)

    from apps.platform_runtime.models import WorkflowAutopilotPolicy

    schema, _actor = _resolve_scope(request)
    pol = (
        WorkflowAutopilotPolicy.objects.filter(
            workflow_key=workflow_key,
            tenant_schema=schema,
            enabled=True,
        ).first()
        or WorkflowAutopilotPolicy.objects.filter(
            workflow_key=workflow_key,
            tenant_schema="",
            enabled=True,
        ).first()
    )
    return JsonResponse(
        {
            "workflow_key": workflow_key,
            "tenant_schema": schema,
            "enabled": bool(pol and pol.enabled),
            "allowed_auto_fix_kinds": list((pol.allowed_auto_fix_kinds if pol else []) or []),
        }
    )


@login_required_api
@require_POST
def enable_autopilot_view(request):
    """Enable autopilot for a workflow + auto_fix_kind (staff-only)."""

    if not getattr(request.user, "is_staff", False):
        return JsonResponse({"error": "forbidden"}, status=403)

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    workflow_key = str(body.get("workflow_key") or "").strip()[:80]
    auto_fix_kind = str(body.get("auto_fix_kind") or "").strip()[:64]
    if not workflow_key or not auto_fix_kind:
        return JsonResponse({"error": "workflow_key_and_auto_fix_kind_required"}, status=400)

    from apps.platform_runtime.models import WorkflowAutopilotPolicy

    schema, _actor = _resolve_scope(request)
    pol, _created = WorkflowAutopilotPolicy.objects.update_or_create(
        workflow_key=workflow_key,
        tenant_schema=schema,
        defaults={
            "enabled": True,
            "promoted_from_successes": bool(body.get("promoted_from_successes", True)),
        },
    )
    kinds = list(pol.allowed_auto_fix_kinds or [])
    if auto_fix_kind not in kinds:
        kinds.append(auto_fix_kind)
    pol.allowed_auto_fix_kinds = kinds
    pol.enabled = True
    pol.save(update_fields=["allowed_auto_fix_kinds", "enabled", "updated_at"])

    return JsonResponse(
        {
            "ok": True,
            "workflow_key": workflow_key,
            "tenant_schema": schema,
            "allowed_auto_fix_kinds": kinds,
        }
    )
