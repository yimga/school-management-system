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
from django.views.decorators.http import require_GET, require_POST, require_http_methods

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

    is_json = bool(
        request.content_type and request.content_type.startswith("application/json")
    )
    wants_json = is_json or "application/json" in request.META.get("HTTP_ACCEPT", "")

    if is_json:
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            return JsonResponse({"ok": False, "reason": "invalid_json"}, status=400)
    else:
        body = {k: v for k, v in request.POST.items()}

    if str(body.get("website_url") or "").strip():
        result = {"ok": True, "reason": "ignored"}
        return (
            JsonResponse(result, status=200)
            if wants_json
            else _render_subscribe_html(ok=True, reason="ignored")
        )

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
    if wants_json:
        return JsonResponse(result, status=200 if result.get("ok") else 400)
    return _render_subscribe_html(
        ok=bool(result.get("ok")),
        reason=str(result.get("reason") or ""),
        email=email,
    )


def _render_subscribe_html(*, ok: bool, reason: str = "", email: str = "") -> HttpResponse:
    """Render a small HTML page for non-JS form posts."""

    from django.utils.html import escape

    if ok:
        body = (
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            "<title>Check your email</title></head>"
            "<body style=\"font-family:system-ui,sans-serif;max-width:520px;margin:48px auto;padding:24px\">"
            "<h1 style=\"margin:0 0 .5rem\">Check your email</h1>"
            f"<p>We sent a confirmation link to <strong>{escape(email)}</strong>. "
            "Click it to finish subscribing.</p>"
            "<p style=\"color:#777;font-size:14px;margin-top:24px\">— The RunMyCampus team</p>"
            "</body></html>"
        )
        return HttpResponse(body, content_type="text/html")
    return HttpResponse(
        "<!doctype html><html><body style=\"font-family:system-ui;max-width:520px;margin:48px auto;padding:24px\">"
        f"<h1>Couldn't subscribe</h1><p>Reason: {escape(reason or 'unknown')}</p>"
        "<p>Please return to the signup form and try again.</p></body></html>",
        content_type="text/html",
        status=400,
    )


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


@csrf_exempt
@require_http_methods(["GET", "POST"])
def newsletter_unsubscribe_view(request, token: str):
    """One-click unsubscribe (RFC 8058).

    POST = the mail-client one-click action (List-Unsubscribe-Post) — returns
    a minimal 200 with no body, as the spec expects. GET = the human landing
    page. Audit H5: previously GET-only, which both failed RFC 8058 (needs
    POST) and let email link-scanners accidentally unsubscribe users.
    """

    from apps.platform_runtime.newsletter_service import unsubscribe

    result = unsubscribe(token)

    if request.method == "POST":
        # One-click: machine action, terse response, never an HTML page.
        return JsonResponse(
            {"ok": bool(result.get("ok")), "unsubscribed": bool(result.get("ok"))},
            status=200 if result.get("ok") else 400,
        )

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
