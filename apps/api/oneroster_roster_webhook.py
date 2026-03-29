"""
Signed roster change webhook for districts (not Clever/ClassLink).
See docs/ONEROSTER_ROSTER_WEBHOOK.md

Also hosts ``platform_marketplace_integration_webhook``: inbound HMAC callbacks using
``RuntimeDefaults.webhook_signing_secret`` (aligned with outbound ``X-RunMyCampus-Signature``).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.db import DatabaseError, IntegrityError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

_SIGNATURE_HEADER = "HTTP_X_RUNMYCAMPUS_INTEGRATION_SIGNATURE"


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


def _integration_webhook_client_ip(request) -> str:
    xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if xff:
        return xff.split(",")[0].strip()[:45]
    return (request.META.get("REMOTE_ADDR") or "").strip()[:45]


@csrf_exempt
@require_POST
def platform_marketplace_integration_webhook(request):
    """
    POST JSON body; HMAC-SHA256 over raw bytes, header ``X-RunMyCampus-Integration-Signature: sha256=<hex>``.
    Secret: ``get_effective_site_settings(...).webhook_signing_secret`` (platform RuntimeDefaults).
    """
    raw = request.body or b""
    body_sha256 = hashlib.sha256(raw).hexdigest()

    from apps.platform_runtime.helpers import get_effective_site_settings
    from apps.platform_runtime.models import PlatformIntegrationWebhookEvent

    eff = get_effective_site_settings(request=None, school=None)
    secret = str(getattr(eff, "webhook_signing_secret", None) or "").strip()

    event_type = ""
    try:
        parsed = json.loads(raw.decode("utf-8") or "{}")
        if isinstance(parsed, dict):
            ev = parsed.get("event") or parsed.get("type")
            if ev is not None:
                event_type = str(ev)[:64]
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
        pass

    sig_header = (request.META.get(_SIGNATURE_HEADER) or "").strip()
    verified = False
    if secret:
        expected_sig = "sha256=" + hmac.new(
            secret.encode("utf-8"), raw, hashlib.sha256
        ).hexdigest()
        verified = bool(sig_header and hmac.compare_digest(sig_header, expected_sig))

    try:
        PlatformIntegrationWebhookEvent.objects.create(
            verified=verified,
            event_type=event_type,
            body_sha256=body_sha256,
            client_ip=_integration_webhook_client_ip(request),
        )
    except (DatabaseError, IntegrityError, OSError, RuntimeError, TypeError, ValueError):
        logger.exception("platform_marketplace_integration_webhook: audit row failed")

    if not secret:
        return JsonResponse(
            {"error": "webhook not configured", "hint": "set webhook_signing_secret"},
            status=503,
        )
    if not verified:
        logger.warning(
            "platform_marketplace_integration_webhook: bad or missing signature ip=%s",
            _integration_webhook_client_ip(request),
        )
        return JsonResponse({"error": "bad signature"}, status=401)

    return JsonResponse({"ok": True, "received": event_type or True})
