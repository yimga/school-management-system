"""Tenant API: unified school readiness meter (batch 1731)."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from apps.schools.school_readiness import build_school_readiness


@login_required
@require_GET
def api_school_readiness(request: HttpRequest) -> JsonResponse:
    school = getattr(request, "school", None)
    if school is None:
        return JsonResponse({"ok": False, "error": "tenant_required"}, status=403)
    payload = build_school_readiness(school, user=request.user)
    return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})
