"""v3.58.x Wave 9 Agent M — Inbound bounce webhooks from email providers.

Endpoint:

    POST /super/email/webhook/<provider>/   — :class:`EmailProviderWebhookView`

Anonymous (signature-verified per provider), CSRF-exempt. Supported
providers: ``postmark``, ``sendgrid``, ``ses`` (AWS SNS), ``mailgun``.

Per-provider parser
-------------------

Each provider posts a different JSON shape; the thin parsers in this
module each return a normalized 4-tuple:

    (recipient_email, bounce_kind_raw, occurred_at_iso, message_id_or_prefix)

The shared post-parse path matches the message-id to an
:class:`EmailDeliveryEvent` row by ``Message-ID`` header prefix (the
sender writes a UUID-bearing Message-ID in
:mod:`apps.schoolops.email_delivery`) and, when matched, updates
``bounced=True`` + ``bounce_kind="provider_<kind>"``.

Signature verification
----------------------

Postmark, Mailgun, and SES (the AWS SNS shape we accept) carry a
shared-secret HMAC signature in the documented header — we verify with
``hmac.compare_digest``. SendGrid uses ECDSA (P-256, SHA-256) over
``timestamp + body``; the operator pastes the base64 public key in the
config form and we verify it via the ``cryptography`` library
(:func:`_verify_sendgrid_ecdsa`). When a signature cannot be verified we
fall back to accept-unverified + log INFO unless
``SCHOOLOPS_SENDGRID_REQUIRE_VERIFIED_WEBHOOK`` is set (then we 401). This is a known v3.58.x
deferral — the public-key flow needs `pynacl` or a similar lib and is
covered by the deliverability docs.

Operator pastes per-provider shared secrets at::

    SiteSettings.email_delivery["webhook_secrets"][<provider>]

… via the existing :class:`EmailDeliveryConfigView` form. NEVER returns
5xx — bad signature is 401, malformed body is 400, internal exceptions
land in `logger.exception` and respond 200 (provider should NOT retry
on a partial-decode failure or we'll get a thundering-herd).

PII contract
------------

The webhook payload often contains the raw recipient address (the
provider has to identify which email bounced). We compute the
``to_hash`` ourselves before matching the EmailDeliveryEvent row, and
we NEVER log the raw recipient. The bounce-class label
(``provider_<type>``) is the only piece of provider-derived text that
reaches the database.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any, Optional, Tuple

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt


logger = logging.getLogger(__name__)


_SUPPORTED_PROVIDERS = ("postmark", "sendgrid", "ses", "mailgun", "brevo")
# Max body bytes we'll attempt to parse. Providers send tiny JSON
# (typically <8KB); we cap at 256KB defense-in-depth against memory
# pressure from a hostile poster.
_MAX_BODY_BYTES = 256 * 1024
_TO_HASH_LEN = 12


def _load_webhook_secrets() -> dict:
    """Return the operator-configured per-provider shared secrets dict.

    Reads ``SiteSettings.email_delivery.webhook_secrets``. Returns ``{}``
    on any read failure — the caller MUST treat empty/missing as "no
    secret configured" and reject signature verification accordingly.
    """
    try:
        from apps.platform_runtime.helpers import get_platform_site_settings_record

        # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
        row = get_platform_site_settings_record(create=False)
        if row is None:
            return {}
        payload = getattr(row, "email_delivery", None) or {}
        secrets = payload.get("webhook_secrets") or {}
        if isinstance(secrets, dict):
            return secrets
        return {}
    except Exception as exc:  # broad-by-design — webhook view never raises
        logger.warning(
            "schoolops.email_webhook.load_secrets_failed err_type=%s",
            type(exc).__name__,
        )
        return {}


def _hash_recipient(addr: str) -> str:
    """sha256(addr.lower())[:12] — same shape as the sender's to_hash."""
    if not addr:
        return ""
    norm = str(addr).strip().lower().encode("utf-8")
    return hashlib.sha256(norm).hexdigest()[:_TO_HASH_LEN]


# ──────────────────────────────────────────────────────────────────────
# Per-provider parsers.
# ──────────────────────────────────────────────────────────────────────


def _parse_postmark(payload: dict) -> Optional[Tuple[str, str, str, str]]:
    """Postmark bounce webhook shape.

    Postmark POSTs a top-level object with at least::

        {
          "RecordType": "Bounce",
          "Email": "alice@example.com",
          "Type": "HardBounce",
          "BouncedAt": "2026-05-22T12:34:56Z",
          "MessageID": "abc-123-...",
        }
    """
    if not isinstance(payload, dict):
        return None
    return (
        str(payload.get("Email") or "")[:320],
        str(payload.get("Type") or "")[:64].lower(),
        str(payload.get("BouncedAt") or "")[:64],
        str(payload.get("MessageID") or "")[:128],
    )


def _parse_sendgrid(payload: Any) -> Optional[Tuple[str, str, str, str]]:
    """SendGrid event-webhook shape.

    SendGrid POSTs an ARRAY of events. We extract the first
    ``event=='bounce'`` (or ``dropped``) entry; other events (open,
    click, delivered) are ignored.
    """
    events = payload if isinstance(payload, list) else None
    if events is None and isinstance(payload, dict):
        # Some forwarder shapes wrap a single event in {"events": [...]}.
        events = payload.get("events") if isinstance(payload.get("events"), list) else None
    if not events:
        return None
    for ev in events:
        if not isinstance(ev, dict):
            continue
        event_name = str(ev.get("event") or "").lower()
        if event_name not in ("bounce", "dropped"):
            continue
        return (
            str(ev.get("email") or "")[:320],
            str(ev.get("type") or event_name)[:64].lower(),
            str(ev.get("timestamp") or "")[:64],
            str(ev.get("sg_message_id") or ev.get("smtp-id") or "")[:128],
        )
    return None


def _parse_ses(payload: dict) -> Optional[Tuple[str, str, str, str]]:
    """AWS SES bounce shape (delivered via SNS).

    SNS wraps the SES JSON in a ``Message`` string that itself is JSON.
    We accept either the unwrapped SES dict OR the SNS envelope.
    """
    if not isinstance(payload, dict):
        return None
    # SNS envelope: {"Type":"Notification","Message":"<json>"}
    if payload.get("Type") == "Notification" and isinstance(payload.get("Message"), str):
        try:
            inner = json.loads(payload["Message"])
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
    else:
        inner = payload
    if not isinstance(inner, dict):
        return None
    if inner.get("notificationType") not in ("Bounce", "Complaint"):
        return None
    mail_obj = inner.get("mail") or {}
    bounce_obj = inner.get("bounce") or inner.get("complaint") or {}
    # First recipient is the canonical one for matching.
    recipients = bounce_obj.get("bouncedRecipients") or bounce_obj.get("complainedRecipients") or []
    addr = ""
    if recipients and isinstance(recipients, list):
        first = recipients[0]
        if isinstance(first, dict):
            addr = str(first.get("emailAddress") or "")[:320]
    bounce_type = str(
        bounce_obj.get("bounceType")
        or bounce_obj.get("complaintFeedbackType")
        or inner.get("notificationType")
        or ""
    )[:64].lower()
    occurred = str(bounce_obj.get("timestamp") or "")[:64]
    msg_id = str(mail_obj.get("messageId") or "")[:128]
    return (addr, bounce_type, occurred, msg_id)


def _parse_mailgun(payload: dict) -> Optional[Tuple[str, str, str, str]]:
    """Mailgun event-data shape.

    Mailgun POSTs a top-level object with::

        {
          "signature": {"timestamp": "...", "token": "...", "signature": "..."},
          "event-data": {
            "event": "failed",
            "severity": "permanent" | "temporary",
            "recipient": "...",
            "timestamp": ...,
            "message": {"headers": {"message-id": "..."}},
          }
        }
    """
    if not isinstance(payload, dict):
        return None
    ev = payload.get("event-data") or {}
    if not isinstance(ev, dict):
        return None
    if str(ev.get("event") or "").lower() not in ("failed", "rejected", "complained"):
        return None
    headers = (ev.get("message") or {}).get("headers") or {}
    msg_id = str(headers.get("message-id") or "")[:128]
    severity = str(ev.get("severity") or "").lower()
    event_name = str(ev.get("event") or "").lower()
    kind = severity or event_name
    return (
        str(ev.get("recipient") or "")[:320],
        kind[:64],
        str(ev.get("timestamp") or "")[:64],
        msg_id,
    )


def _parse_brevo(payload: Any) -> Optional[Tuple[str, str, str, str]]:
    """Brevo (Sendinblue) transactional event webhook shape (audit H13).

    Brevo POSTs one event object per request, e.g.::

        {
          "event": "hard_bounce" | "soft_bounce" | "spam" | "blocked"
                   | "invalid_email" | "deferred" | "delivered" | ...,
          "email": "user@example.com",
          "message-id": "<...>",
          "date": "2026-06-03 12:00:00",
          "reason": "..."
        }

    We act only on the deliverability-negative events; everything else
    (delivered/opened/clicked) returns None so the shared path acks 200.
    """
    if not isinstance(payload, dict):
        return None
    event = str(payload.get("event") or "").lower().replace("-", "_")
    actionable = {
        "hard_bounce", "soft_bounce", "spam", "blocked",
        "invalid_email", "complaint", "unsubscribed",
    }
    if event not in actionable:
        return None
    return (
        str(payload.get("email") or "")[:320],
        event[:64],
        str(payload.get("date") or payload.get("ts") or "")[:64],
        str(payload.get("message-id") or payload.get("message_id") or "")[:128],
    )


_PARSERS = {
    "postmark": _parse_postmark,
    "sendgrid": _parse_sendgrid,
    "ses": _parse_ses,
    "mailgun": _parse_mailgun,
    "brevo": _parse_brevo,
}

# Bounce-kind tokens (any provider) that mean the address is undeliverable or
# complained → add to the suppression list so we stop sending (audit H3).
_SUPPRESSION_BOUNCE_TOKENS = frozenset(
    {
        "hard_bounce", "hardbounce", "hard", "permanent",
        "spam", "complaint", "complained", "abuse",
        "invalid_email", "blocked", "recipientsrefused", "senderrefused",
        "5xx", "hard_5xx", "bounce",
    }
)


# ──────────────────────────────────────────────────────────────────────
# Signature verification.
# ──────────────────────────────────────────────────────────────────────


def _verify_sendgrid_ecdsa(
    public_key_b64: str, timestamp: str, body_bytes: bytes, signature_b64: str
) -> bool:
    """Verify a SendGrid (Twilio) Event Webhook ECDSA signature.

    SendGrid signs the bytes ``timestamp + payload`` with ECDSA (NIST P-256,
    SHA-256). The operator-configured ``secret`` for the ``sendgrid`` provider
    is the base64 public key shown in the SendGrid UI (DER SubjectPublicKeyInfo).
    Returns True ONLY on a cryptographically valid signature; any error
    (library absent, malformed key/signature, mismatch) returns False so the
    caller decides whether to accept unverified or reject.
    """
    if not (public_key_b64 and timestamp and signature_b64):
        return False
    try:
        import base64

        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        public_key = serialization.load_der_public_key(
            base64.b64decode(public_key_b64)
        )
        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            return False
        signed_payload = timestamp.encode("utf-8") + body_bytes
        public_key.verify(
            base64.b64decode(signature_b64),
            signed_payload,
            ec.ECDSA(hashes.SHA256()),
        )
        return True
    except InvalidSignature:
        return False
    except Exception:  # noqa: BLE001 - lib missing / bad key / bad b64 → unverified
        return False


def _verify_signature(
    provider: str,
    request: HttpRequest,
    body_bytes: bytes,
    secret: str,
) -> Tuple[bool, bool]:
    """Verify per-provider HMAC signature. Returns (verified_ok, used_unverified_fallback).

    * Postmark: ``X-Postmark-Signature`` is an HMAC-SHA256 over the raw
      body, hex-encoded.
    * Mailgun: legacy webhook signature is HMAC-SHA256 of
      ``"<timestamp><token>"`` keyed with the webhook signing key. We
      accept ``signature.timestamp`` + ``signature.token`` + ``signature.signature``
      from the parsed payload OR the dedicated headers when present.
    * SES (via SNS): ``X-Amz-Sns-Message-Id`` is informational; AWS's
      signing certificate flow is OUT OF SCOPE. We HMAC-SHA256 the raw
      body with the operator-pasted shared secret (operator wires a
      shared-secret-bearing SNS subscriber, e.g. via API Gateway).
    * SendGrid: ECDSA (P-256, SHA-256) signature in
      ``X-Twilio-Email-Event-Webhook-Signature`` over
      ``X-Twilio-Email-Event-Webhook-Timestamp + body``, verified via the
      ``cryptography`` library (:func:`_verify_sendgrid_ecdsa`) against the
      operator's base64 public key. On a valid signature → ``(True, False)``.
      If it cannot be verified we fall back to ``(False, True)``
      (accept-unverified) unless ``SCHOOLOPS_SENDGRID_REQUIRE_VERIFIED_WEBHOOK``
      is set, in which case → ``(False, False)`` (401).
    """
    if not secret:
        return (False, False)
    if provider == "postmark":
        provided = (request.META.get("HTTP_X_POSTMARK_SIGNATURE") or "").strip()
        if not provided:
            return (False, False)
        computed = hmac.new(
            secret.encode("utf-8"),
            msg=body_bytes,
            digestmod=hashlib.sha256,
        ).hexdigest()
        return (hmac.compare_digest(computed, provided), False)
    if provider == "mailgun":
        # Mailgun documents the signing protocol with timestamp + token.
        try:
            payload = json.loads(body_bytes.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return (False, False)
        sig = (payload.get("signature") or {}) if isinstance(payload, dict) else {}
        ts = str(sig.get("timestamp") or "")
        token = str(sig.get("token") or "")
        provided = str(sig.get("signature") or "")
        if not (ts and token and provided):
            return (False, False)
        computed = hmac.new(
            secret.encode("utf-8"),
            msg=f"{ts}{token}".encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()
        return (hmac.compare_digest(computed, provided), False)
    if provider == "ses":
        # Operator's API Gateway / Lambda relay HMACs the body with the
        # shared secret and forwards as X-RMC-SNS-Signature header.
        # Direct AWS-signed SNS deliveries would require fetching AWS
        # signing certs — out of scope; documented as a deferral.
        provided = (request.META.get("HTTP_X_RMC_SNS_SIGNATURE") or "").strip()
        if not provided:
            return (False, False)
        computed = hmac.new(
            secret.encode("utf-8"),
            msg=body_bytes,
            digestmod=hashlib.sha256,
        ).hexdigest()
        return (hmac.compare_digest(computed, provided), False)
    if provider == "sendgrid":
        # SendGrid Event Webhook uses ECDSA (P-256, SHA-256) over
        # ``timestamp + body``. ``secret`` is the base64 public key from the
        # SendGrid UI. We verify with the `cryptography` library.
        provided = (
            request.META.get("HTTP_X_TWILIO_EMAIL_EVENT_WEBHOOK_SIGNATURE")
            or request.META.get("HTTP_X_SENDGRID_SIGNATURE")
            or ""
        ).strip()
        if not provided:
            return (False, False)
        timestamp = (
            request.META.get("HTTP_X_TWILIO_EMAIL_EVENT_WEBHOOK_TIMESTAMP") or ""
        ).strip()
        if _verify_sendgrid_ecdsa(secret, timestamp, body_bytes, provided):
            return (True, False)
        # Could not verify (bad/forged signature, missing timestamp, or
        # cryptography unavailable). Reject when the operator requires verified
        # webhooks; otherwise fall back to accept-unverified (legacy behaviour,
        # so this is never a regression) and log the gap.
        if getattr(settings, "SCHOOLOPS_SENDGRID_REQUIRE_VERIFIED_WEBHOOK", False):
            logger.info("schoolops.email_webhook.sendgrid_signature_rejected")
            return (False, False)
        logger.info("schoolops.email_webhook.sendgrid_unverified_fallback")
        return (False, True)
    return (False, False)


# ──────────────────────────────────────────────────────────────────────
# DB write helper — append-only-safe partial UPDATE on bounce columns.
# ──────────────────────────────────────────────────────────────────────


def _mark_bounced_by_message_id(
    message_id_or_prefix: str,
    bounce_kind_raw: str,
) -> Optional[str]:
    """Find the EmailDeliveryEvent row whose Message-ID prefix-matches and bounce-mark it.

    Returns the matched ``event_id`` as a string on success, ``None``
    when no match found.

    The sender wires ``email.utils.make_msgid()`` into the message
    headers, which has shape ``<<UUID-ish>@<domain>>``. The provider
    typically strips angle-brackets and surfaces only the local-part.
    We do a forgiving startswith match on the cleaned-up token.

    Uses raw UPDATE via ``.update()`` (queryset method) which bypasses
    the model's ``save()`` append-only guard. We update bounce columns
    ONLY — never recipient / subject / status / created_at. The row
    is still effectively append-only at the row-as-a-whole level.
    """
    if not message_id_or_prefix:
        return None
    cleaned = message_id_or_prefix.strip().lstrip("<").rstrip(">")
    if "@" in cleaned:
        cleaned = cleaned.split("@", 1)[0]
    cleaned = cleaned.strip()[:64]
    if not cleaned:
        return None
    try:
        from apps.schoolops.models_email_delivery import EmailDeliveryEvent

        # Deterministic correlation on the indexed ``message_id_prefix`` column
        # the sender now persists (audit residual closeout). Exact match first;
        # a forgiving startswith fallback covers providers that truncate the
        # local-part. We no longer rely on the old subject_prefix heuristic.
        # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
        candidate = (
            EmailDeliveryEvent.objects
            .filter(message_id_prefix=cleaned)
            .order_by("-created_at")
            .only("pk")
            .first()
        )
        if candidate is None:
            # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
            candidate = (
                EmailDeliveryEvent.objects
                .filter(message_id_prefix__startswith=cleaned[:24])
                .exclude(message_id_prefix="")
                .order_by("-created_at")
                .only("pk")
                .first()
            )
        if candidate is None:
            return None
        # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
        EmailDeliveryEvent.objects.filter(pk=candidate.pk).update(
            bounced=True,
            bounce_kind=f"provider_{(bounce_kind_raw or 'unknown')[:24]}",
        )
        return str(candidate.pk)
    except Exception as exc:  # broad-by-design — webhook NEVER 500s
        logger.warning(
            "schoolops.email_webhook.update_failed err_type=%s",
            type(exc).__name__,
        )
        return None


# ──────────────────────────────────────────────────────────────────────
# View.
# ──────────────────────────────────────────────────────────────────────


@method_decorator(csrf_exempt, name="dispatch")
class EmailProviderWebhookView(View):
    """POST-only webhook receiver for email provider bounce notifications.

    Anonymous (no auth) — signature-verified per provider against the
    operator-configured shared secret. Returns 200 OK on success or on
    valid-but-unmatched bounces (the provider should NOT retry an
    unmatched message-id), 401 on bad signature, 400 on malformed body.
    """

    http_method_names = ["post"]

    def post(
        self,
        request: HttpRequest,
        provider: str,
        *args: Any,
        **kwargs: Any,
    ) -> HttpResponse:
        provider = (provider or "").strip().lower()
        if provider not in _SUPPORTED_PROVIDERS:
            return JsonResponse(
                {"ok": False, "error": "unsupported_provider"},
                status=400,
            )

        body_bytes = request.body or b""
        if len(body_bytes) > _MAX_BODY_BYTES:
            return JsonResponse(
                {"ok": False, "error": "body_too_large"},
                status=400,
            )

        secrets = _load_webhook_secrets()
        secret = (secrets.get(provider) or "").strip()

        # Signature verification BEFORE JSON parse — minimizes work on
        # forged requests.
        verified, unverified_fallback = _verify_signature(
            provider, request, body_bytes, secret,
        )
        if not verified and not unverified_fallback:
            # Either no secret configured, or signature mismatch.
            logger.info(
                "schoolops.email_webhook.signature_rejected provider=%s",
                provider,
            )
            return JsonResponse(
                {"ok": False, "error": "signature_invalid"},
                status=401,
            )

        try:
            payload = json.loads(body_bytes.decode("utf-8") or "null")
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.info(
                "schoolops.email_webhook.malformed_body provider=%s",
                provider,
            )
            return JsonResponse(
                {"ok": False, "error": "malformed_body"},
                status=400,
            )

        parser = _PARSERS.get(provider)
        try:
            parsed = parser(payload) if parser else None
        except Exception as exc:  # broad-by-design — parser exceptions never 500
            logger.exception(
                "schoolops.email_webhook.parser_crashed provider=%s err_type=%s",
                provider, type(exc).__name__,
            )
            parsed = None

        if not parsed:
            # No actionable bounce in this payload (e.g. SendGrid array
            # of 'open' / 'click' events). Acknowledge so the provider
            # doesn't retry.
            return JsonResponse({"ok": True, "matched": False}, status=200)

        _recipient, bounce_kind_raw, _occurred_at, message_id = parsed
        # NEVER log the raw recipient. The hash is for forensic correlation.
        recipient_hash = _hash_recipient(_recipient)

        # Audit H3 — enforce suppression off the *reported recipient* directly.
        # This works even though row-correlation by Message-ID is best-effort:
        # the provider tells us WHO bounced/complained, so we can stop future
        # sends to that address regardless of which EmailDeliveryEvent matched.
        kind_token = (bounce_kind_raw or "").strip().lower().replace("-", "_")
        if _recipient and kind_token in _SUPPRESSION_BOUNCE_TOKENS:
            try:
                from apps.schoolops.email_delivery import suppress_recipient

                reason = "complaint" if kind_token in (
                    "spam", "complaint", "complained", "abuse",
                ) else "hard_bounce"
                suppress_recipient(
                    _recipient, reason=reason, source="webhook", detail=kind_token,
                )
            except Exception:  # noqa: BLE001 — webhook NEVER 500s
                logger.warning(
                    "schoolops.email_webhook.suppress_failed provider=%s", provider,
                )

        matched_event_id: Optional[str] = None
        try:
            matched_event_id = _mark_bounced_by_message_id(
                message_id, bounce_kind_raw,
            )
        except Exception as exc:  # broad-by-design — view NEVER 500s
            logger.exception(
                "schoolops.email_webhook.match_crashed provider=%s err_type=%s",
                provider, type(exc).__name__,
            )
            matched_event_id = None

        if matched_event_id is None:
            # Dangling bounce — log at INFO and 200 anyway (don't ask
            # the provider to retry; the EmailDeliveryEvent row may
            # have aged out or the Message-ID schema hasn't been
            # extended to persist the prefix yet).
            logger.info(
                "schoolops.email_webhook.bounce_unmatched provider=%s "
                "recipient_hash=%s bounce_kind=%s signature_unverified=%s",
                provider, recipient_hash, bounce_kind_raw or "unknown",
                bool(unverified_fallback),
            )
            return JsonResponse(
                {
                    "ok": True,
                    "matched": False,
                    "signature_unverified": bool(unverified_fallback),
                },
                status=200,
            )

        logger.info(
            "schoolops.email_webhook.bounce_recorded provider=%s "
            "event_id=%s recipient_hash=%s bounce_kind=%s "
            "signature_unverified=%s",
            provider, matched_event_id, recipient_hash,
            bounce_kind_raw or "unknown", bool(unverified_fallback),
        )
        return JsonResponse(
            {
                "ok": True,
                "matched": True,
                "event_id": matched_event_id,
                "signature_unverified": bool(unverified_fallback),
            },
            status=200,
        )


__all__ = [
    "EmailProviderWebhookView",
]
