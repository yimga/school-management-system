"""Authenticated browser Web Push subscription API."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from apps.communication.web_push_service import (
    deactivate_web_push_subscription,
    upsert_web_push_subscription,
    vapid_configured,
    vapid_public_key,
)


@login_required
@require_GET
def web_push_vapid_public_key(request):
    if not vapid_configured():
        return JsonResponse({"configured": False, "public_key": ""})
    return JsonResponse({"configured": True, "public_key": vapid_public_key()})


@login_required
@require_POST
def web_push_subscribe(request):
    if not vapid_configured():
        return JsonResponse(
            {"ok": False, "error": "web_push_not_configured"}, status=503
        )
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)
    row = upsert_web_push_subscription(request.user, payload)
    if not row:
        return JsonResponse({"ok": False, "error": "invalid_subscription"}, status=400)
    return JsonResponse({"ok": True, "subscription_id": row.pk})


@login_required
@require_POST
def web_push_unsubscribe(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {}
    endpoint = (payload.get("endpoint") or "").strip()
    deactivate_web_push_subscription(request.user, endpoint)
    return JsonResponse({"ok": True})
