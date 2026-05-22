"""Workflow playbook ask APIs — onboarding + offboarding (batch 1394)."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from apps.accounts.permissions import tenant_operator_hub_eligible
from apps.portal.workflow_playbook_ai import (
    build_offboarding_playbook_context,
    build_onboarding_playbook_context,
)
from apps.portal.views_ai_gateway import _api_guided_domain_assistant
from services.ai_gateway import TaskType


def _decode_body(request) -> dict:
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return {}


@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_onboarding_playbook_ask(request):
    """POST { query } — conversational onboarding playbook (tenant operators)."""
    school = getattr(request, "school", None)
    if school is None or not tenant_operator_hub_eligible(request.user):
        return JsonResponse({"success": False, "error": "forbidden"}, status=403)
    body = _decode_body(request)
    query = (body.get("query") or "").strip()[:500]
    if not query:
        return JsonResponse({"success": False, "error": "query required"}, status=400)

    from apps.platform_runtime.onboarding import get_school_onboarding_progress

    progress = get_school_onboarding_progress(school, user=request.user)
    blockers: list[str] = []
    if int(progress.get("percent") or 0) < 50:
        blockers.append("Activation below 50%")
    ctx = build_onboarding_playbook_context(progress=progress, blockers=blockers)
    return _api_guided_domain_assistant(
        request,
        task_type=TaskType.WORKFLOW_DRAFT,
        audit_feature="onboarding_playbook",
        prompt_key="workflow_playbook",
        context_block=ctx,
    )


@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_offboarding_playbook_ask(request):
    """POST { query } — conversational offboarding playbook (school admins)."""
    school = getattr(request, "school", None)
    if school is None or not tenant_operator_hub_eligible(request.user):
        return JsonResponse({"success": False, "error": "forbidden"}, status=403)
    body = _decode_body(request)
    query = (body.get("query") or "").strip()[:500]
    if not query:
        return JsonResponse({"success": False, "error": "query required"}, status=400)

    self_service: dict = {"status": "active"}
    try:
        from apps.schools.tenant_offboarding import get_self_service_snapshot

        self_service = get_self_service_snapshot(school) or self_service
    except Exception:
        pass
    ctx = build_offboarding_playbook_context(self_service=self_service)
    return _api_guided_domain_assistant(
        request,
        task_type=TaskType.WORKFLOW_DRAFT,
        audit_feature="offboarding_playbook",
        prompt_key="workflow_playbook",
        context_block=ctx,
    )
