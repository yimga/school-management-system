"""Newsletter subscription HTTP surface (v4.00.98 Phase 3).

Routes:

* POST /platform-runtime/newsletter/subscribe/   — public form post
* GET  /platform-runtime/newsletter/confirm/<token>/   — double-opt-in click
* GET  /platform-runtime/newsletter/unsubscribe/<token>/ — one-click unsub

All routes are CSRF-exempt for the public form (cross-origin from
runmycampus.com marketing surface). Rate-limited at the reliability layer
via the email matrix dispatcher. NEVER raises — every failure returns a
JSON envelope.
"""

from __future__ import annotations

import json
import logging

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

logger = logging.getLogger(__name__)


def _client_ip(request) -> str:
    """Best-effort client IP without trusting forwarded headers in dev."""

    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return str(forwarded.split(",")[0].strip())
    return str(request.META.get("REMOTE_ADDR", ""))


@csrf_exempt
@require_POST
def newsletter_subscribe_view(request):
    """Public newsletter signup. Accepts JSON or form-encoded POST."""

    from apps.platform_runtime.newsletter_service import request_subscription

    if request.content_type and request.content_type.startswith("application/json"):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            return JsonResponse({"ok": False, "reason": "invalid_json"}, status=400)
    else:
        body = {k: v for k, v in request.POST.items()}

    email = str(body.get("email") or "").strip()
    source = str(body.get("source") or "marketing_signup")[:64]
    utm_source = str(body.get("utm_source") or "")[:64]
    utm_medium = str(body.get("utm_medium") or "")[:64]
    utm_campaign = str(body.get("utm_campaign") or "")[:128]

    result = request_subscription(
        email=email,
        source=source,
        ip=_client_ip(request),
        utm_source=utm_source,
        utm_medium=utm_medium,
        utm_campaign=utm_campaign,
    )
    return JsonResponse(result, status=200 if result.get("ok") else 400)


@require_GET
def newsletter_confirm_view(request, token: str):
    """Double-opt-in confirmation landing page."""

    from apps.platform_runtime.newsletter_service import confirm_subscription

    result = confirm_subscription(token)
    if result.get("ok"):
        body = (
            "<!doctype html><html><head><meta charset=\"utf-8\"><title>Subscription confirmed</title></head>"
            "<body style=\"font-family:system-ui,sans-serif;max-width:520px;margin:48px auto;padding:24px\">"
            f"<h1 style=\"margin:0 0 .5rem\">You're confirmed</h1>"
            f"<p>Thanks for confirming <strong>{result.get('email', '')}</strong>. "
            "We'll send you the occasional update — never spam.</p>"
            "<p style=\"color:#777;font-size:14px;margin-top:24px\">— The RunMyCampus team</p>"
            "</body></html>"
        )
        return HttpResponse(body, content_type="text/html")
    return HttpResponse(
        "<!doctype html><html><body style=\"font-family:system-ui;max-width:520px;margin:48px auto;padding:24px\">"
        f"<h1>Couldn't confirm subscription</h1><p>Reason: {result.get('reason', 'unknown')}</p>"
        "<p>If you'd like to subscribe again, return to the signup form.</p></body></html>",
        content_type="text/html",
        status=400,
    )


@require_GET
def newsletter_unsubscribe_view(request, token: str):
    """One-click unsubscribe landing page."""

    from apps.platform_runtime.newsletter_service import unsubscribe

    result = unsubscribe(token)
    if result.get("ok"):
        body = (
            "<!doctype html><html><head><meta charset=\"utf-8\"><title>Unsubscribed</title></head>"
            "<body style=\"font-family:system-ui,sans-serif;max-width:520px;margin:48px auto;padding:24px\">"
            "<h1 style=\"margin:0 0 .5rem\">Unsubscribed</h1>"
            f"<p><strong>{result.get('email', '')}</strong> will no longer receive RunMyCampus marketing email.</p>"
            "<p style=\"color:#777;font-size:14px;margin-top:24px\">Made a mistake? You can resubscribe any time at runmycampus.com.</p>"
            "</body></html>"
        )
        return HttpResponse(body, content_type="text/html")
    return HttpResponse(
        "<!doctype html><html><body style=\"font-family:system-ui;max-width:520px;margin:48px auto;padding:24px\">"
        f"<h1>Couldn't unsubscribe</h1><p>Reason: {result.get('reason', 'unknown')}</p></body></html>",
        content_type="text/html",
        status=400,
    )
