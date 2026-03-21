"""
Signed roster change webhook for districts (not Clever/ClassLink).
See docs/ONEROSTER_ROSTER_WEBHOOK.md
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def oneroster_roster_webhook(request):
    raw = request.body
    try:
        body = json.loads(raw.decode() or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid json"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": "object required"}, status=400)

    school_id = body.get("school_id")
    secret = getattr(settings, "ONEROSTER_WEBHOOK_SECRET", "") or ""
    if school_id:
        from apps.schools.models import School

        school = School.objects.filter(pk=school_id).first()
        if school and isinstance(getattr(school, "settings", None), dict):
            s = (school.settings or {}).get("roster_webhook_secret") or ""
            if s:
                secret = s
    if not secret:
        return JsonResponse({"error": "webhook not configured"}, status=503)

    sig_header = (request.META.get("HTTP_X_ROSTER_WEBHOOK_SIGNATURE") or "").strip()
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), raw, hashlib.sha256
    ).hexdigest()
    if not sig_header or not hmac.compare_digest(sig_header, expected):
        logger.warning("oneroster_roster_webhook: bad signature school_id=%s", school_id)
        return JsonResponse({"error": "bad signature"}, status=401)

    logger.info(
        "oneroster_roster_webhook: event=%s school_id=%s",
        body.get("event"),
        school_id,
    )
    return JsonResponse(
        {
            "ok": True,
            "received": body.get("event"),
            "doc": "docs/ONEROSTER_ROSTER_WEBHOOK.md",
        }
    )
