"""Inbound SMS webhooks (audit residual closeout).

Two endpoints, both POST-only, anonymous, CSRF-exempt:

1. :func:`sms_inbound_webhook` — STOP / HELP / START keyword handling.
   Carriers and providers (Twilio, Africa's Talking) POST inbound SMS here.
   A STOP-family keyword records a ``withdrawn`` consent event (so the SMS
   send path stops messaging that number); START re-grants; HELP replies with
   the operator-configured help text. This is the receive side the platform
   previously lacked — STOP could be honoured nowhere.

2. :func:`sms_status_webhook` — Twilio delivery status callbacks. Twilio POSTs
   ``MessageStatus`` transitions (queued → sent → delivered / failed); we upsert
   a :class:`apps.communication.models_delivery_receipt.MessageDeliveryReceipt`.

Signature
---------
Twilio signs each request with ``X-Twilio-Signature`` (HMAC-SHA1 over the full
URL + sorted POST params, base64). We verify it when the auth token is
available; ``RMC_SMS_WEBHOOK_REQUIRE_TWILIO_SIGNATURE`` makes verification
mandatory (else unsigned posts — dev, or Africa's Talking which has no standard
signature — are accepted). NEVER 5xx; bad signature → 403, otherwise 200.

PII contract
------------
Phone numbers are hashed before any log or audit row; raw numbers never land in
logs.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

_EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'

# Keyword families (case-insensitive, first token of the body).
_STOP_KEYWORDS = frozenset(
    {"stop", "stopall", "unsubscribe", "cancel", "end", "quit", "optout", "revoke"}
)
_START_KEYWORDS = frozenset({"start", "yes", "unstop", "optin"})
_HELP_KEYWORDS = frozenset({"help", "info"})


def _hash_phone(phone: str) -> str:
    norm = (phone or "").strip().lower()
    if not norm:
        return ""
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:12]


def _twilio_auth_token(request: HttpRequest) -> str:
    """Resolve the Twilio auth token (platform env → tenant site settings)."""
    token = getattr(settings, "TWILIO_AUTH_TOKEN", None)
    if token:
        return str(token)
    site = getattr(request, "site_settings", None) or getattr(
        settings, "SITE_SETTINGS", None
    )
    return str(getattr(site, "twilio_auth_token", "") or "")


def _verify_twilio_signature(request: HttpRequest, token: str) -> bool:
    """Verify Twilio's X-Twilio-Signature over (url + sorted POST params)."""
    provided = (request.META.get("HTTP_X_TWILIO_SIGNATURE") or "").strip()
    if not (provided and token):
        return False
    try:
        url = request.build_absolute_uri()
        params = request.POST
        payload = url + "".join(
            f"{k}{params[k]}" for k in sorted(params.keys())
        )
        digest = hmac.new(
            token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1
        ).digest()
        computed = base64.b64encode(digest).decode("utf-8")
        return hmac.compare_digest(computed, provided)
    except Exception:  # noqa: BLE001 — any verify error → unverified
        return False


def _shared_secret_ok(request: HttpRequest) -> bool:
    """Verify the optional shared secret (Africa's Talking has no signature).

    AT — and any provider without a request-signing scheme — can be
    authenticated by configuring ``RMC_SMS_WEBHOOK_SHARED_SECRET`` and putting
    it in the webhook URL (``?key=…``) or an ``X-RMC-SMS-Secret`` header. We
    constant-time compare. Returns False when no secret is configured or it
    doesn't match.
    """
    secret = str(getattr(settings, "RMC_SMS_WEBHOOK_SHARED_SECRET", "") or "")
    if not secret:
        return False
    provided = (
        request.GET.get("key")
        or request.META.get("HTTP_X_RMC_SMS_SECRET")
        or ""
    ).strip()
    return bool(provided) and hmac.compare_digest(provided, secret)


def _signature_ok(request: HttpRequest) -> bool:
    """Apply the auth policy. True = proceed, False = reject (403).

    Order: a valid Twilio signature wins; else a valid shared secret (AT);
    else — if EITHER auth mechanism is configured — reject. With no auth
    configured at all (dev) we accept so local testing isn't blocked.
    """
    token = _twilio_auth_token(request)
    if token and _verify_twilio_signature(request, token):
        return True
    if _shared_secret_ok(request):
        return True
    require_twilio = bool(
        getattr(settings, "RMC_SMS_WEBHOOK_REQUIRE_TWILIO_SIGNATURE", False)
    )
    secret_configured = bool(
        str(getattr(settings, "RMC_SMS_WEBHOOK_SHARED_SECRET", "") or "")
    )
    if require_twilio or secret_configured:
        logger.info("communication.sms_webhook.auth_rejected")
        return False
    # No auth mechanism configured (dev) — accept.
    return True


def _inbound_fields(request: HttpRequest) -> tuple[str, str, str]:
    """Return (from_phone, body, provider) across Twilio + Africa's Talking."""
    p = request.POST
    # Twilio: From / Body. Africa's Talking: from / text.
    from_phone = (p.get("From") or p.get("from") or "").strip()
    body = (p.get("Body") or p.get("text") or "").strip()
    provider = "twilio" if (p.get("From") or p.get("MessageSid")) else (
        "africastalking" if (p.get("from") or p.get("text")) else "unknown"
    )
    return from_phone, body, provider


@csrf_exempt
@require_POST
def sms_inbound_webhook(request: HttpRequest) -> HttpResponse:
    """Inbound SMS keyword handler (STOP / START / HELP).

    Wired at ``/communication/sms/inbound/``.
    """
    if not _signature_ok(request):
        return HttpResponse("forbidden", status=403)

    from_phone, body, provider = _inbound_fields(request)
    if not from_phone:
        # Nothing to act on; ack so the provider doesn't retry.
        return HttpResponse(_EMPTY_TWIML, content_type="application/xml")

    keyword = (body.split() or [""])[0].strip().lower()
    school = getattr(request, "school", None)
    phone_hash = _hash_phone(from_phone)

    from apps.communication.consent import record_consent_event

    reply_message = ""
    if keyword in _STOP_KEYWORDS:
        record_consent_event(
            channel="sms", identifier=from_phone, action="withdrawn",
            reason=keyword, source="sms_webhook", school=school,
        )
        logger.info("communication.sms_webhook.opt_out phone=%s", phone_hash)
    elif keyword in _START_KEYWORDS:
        record_consent_event(
            channel="sms", identifier=from_phone, action="granted",
            reason=keyword, source="sms_webhook", school=school,
        )
        logger.info("communication.sms_webhook.opt_in phone=%s", phone_hash)
    elif keyword in _HELP_KEYWORDS:
        record_consent_event(
            channel="sms", identifier=from_phone, action="help_requested",
            reason=keyword, source="sms_webhook", school=school,
        )
        reply_message = str(
            getattr(settings, "RMC_SMS_HELP_REPLY", "") or ""
        ).strip()

    # Africa's Talking expects a plain 200; Twilio renders TwiML. We return
    # TwiML universally — AT ignores the XML body and just needs the 2xx.
    if reply_message:
        # Escape minimal XML special chars in the operator-configured reply.
        safe = (
            reply_message.replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;")
        )
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f"<Response><Message>{safe}</Message></Response>"
        )
        return HttpResponse(twiml, content_type="application/xml")
    return HttpResponse(_EMPTY_TWIML, content_type="application/xml")


@csrf_exempt
@require_POST
def sms_status_webhook(request: HttpRequest) -> HttpResponse:
    """Twilio delivery status callback → MessageDeliveryReceipt upsert.

    Wired at ``/communication/sms/status/``. Twilio POSTs MessageSid,
    MessageStatus, To, ErrorCode.
    """
    if not _signature_ok(request):
        return HttpResponse("forbidden", status=403)

    p = request.POST
    message_sid = (p.get("MessageSid") or p.get("SmsSid") or p.get("id") or "").strip()
    status = (p.get("MessageStatus") or p.get("SmsStatus") or p.get("status") or "").strip()
    recipient = (p.get("To") or p.get("to") or "").strip()
    error_code = (p.get("ErrorCode") or "").strip()
    if not message_sid:
        return JsonResponse({"ok": True, "recorded": False}, status=200)

    from apps.communication.delivery_receipts import record_delivery_receipt

    recorded = record_delivery_receipt(
        channel="sms",
        provider="twilio",
        provider_message_id=message_sid,
        recipient=recipient,
        status=status,
        error_code=error_code,
        school=getattr(request, "school", None),
    )
    return JsonResponse({"ok": True, "recorded": bool(recorded)}, status=200)
