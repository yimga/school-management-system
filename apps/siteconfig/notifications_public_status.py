"""v4.00.49 — Channel adapters for public-incident notifications.

Each ``PublicIncidentSubscription`` row carries a ``channel`` of EMAIL / SMS /
SLACK / DISCORD. The fan-out signal calls :func:`dispatch_to_subscriber` which
routes to the right adapter based on the channel.

Design notes:
  * EMAIL uses ``django.core.mail.send_mail`` (existing path).
  * SMS routes through the platform SMS hook (auto-discovered; falls back to
    a structured log when no provider configured — so dev environments don't
    blow up on opt-in).
  * SLACK + DISCORD POST JSON to the subscriber-supplied webhook URL using
    ``urllib.request`` (stdlib only — no new runtime dependency).

All adapters are wrapped at the signal level by a per-subscriber try/except so
one bad row never breaks the fan-out. We additionally swallow per-channel
exceptions here and surface them as ``DispatchResult.ok=False`` so the caller
can decide whether to update ``last_alerted_at`` (yes on success, no on
failure — so a retry can land on the next state transition).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


_HTTP_TIMEOUT_SECONDS = 5
_USER_AGENT = "RunMyCampus-StatusPage/1.0 (+https://runmycampus.com/status/)"


@dataclass
class DispatchResult:
    ok: bool
    detail: str = ""


def _build_subject_and_body(incident, kind: str, status_url: str, unsub_url: str) -> tuple[str, str]:
    summary = incident.summary or "Operator is investigating."
    subject = (
        f"[RunMyCampus status] {incident.get_severity_display()} {kind}"
        f" — {incident.title[:100]}"
    )
    body = (
        f"{incident.title}\n\n"
        f"Severity: {incident.get_severity_display()}\n"
        f"Status: {incident.get_status_display()}\n"
        f"Started: {incident.started_at.isoformat()}\n"
        f"{'Resolved: ' + incident.resolved_at.isoformat() + chr(10) if incident.resolved_at else ''}"
        f"\n{summary}\n\n"
        f"Live updates: {status_url}\n"
        f"Unsubscribe: {unsub_url}\n"
    )
    return subject, body


def _dispatch_email(sub, incident, subject: str, body: str) -> DispatchResult:
    try:
        from django.conf import settings
        from apps.schoolops.email_compat import send_mail
    except ImportError:
        return DispatchResult(ok=False, detail="email-backend-missing")
    to_addr = sub.email or sub.address
    if not to_addr:
        return DispatchResult(ok=False, detail="no-email-address")
    from_email = (
        getattr(settings, "DEFAULT_FROM_EMAIL", None) or "no-reply@runmycampus.com"
    )
    sent = send_mail(subject, body, from_email, [to_addr], fail_silently=True)
    return DispatchResult(ok=bool(sent), detail=f"sent={sent}")


def _dispatch_sms(sub, incident, body: str) -> DispatchResult:
    # SMS bodies are hard-capped at 160 chars to fit a single segment; we
    # deliberately truncate rather than spread across segments because most
    # public-incident alerts are skim-once.
    sms_text = (
        f"[RMC status] {incident.get_severity_display()} — "
        f"{incident.title[:80]}. {incident.get_status_display()}."
    )[:160]  # magic-number-allow: string-truncation-cap
    address = sub.address.strip()
    if not address:
        return DispatchResult(ok=False, detail="no-sms-address")

    sms_sender = _resolve_sms_sender()
    if sms_sender is None:
        # No SMS provider wired up — fall through to a structured info log so
        # opt-in still works in dev without crashing.
        logger.info(
            "public_status.sms",
            extra={"channel": "SMS", "incident_id": str(incident.pk), "address_len": len(address)},
        )
        return DispatchResult(ok=True, detail="logged-no-provider")
    try:
        sms_sender(address, sms_text)
        return DispatchResult(ok=True, detail="sent")
    except Exception as exc:  # noqa: BLE001 — best-effort fan-out
        logger.debug("public_status: sms dispatch failed", exc_info=True)
        return DispatchResult(ok=False, detail=f"send-failed:{type(exc).__name__}")


def _resolve_sms_sender():
    """Return a callable ``(address, message) -> None`` or None if unwired.

    Best-effort discovery: prefer ``services.sms.send_sms``; fall back to
    ``apps.notifications.sms.send_sms`` if present. The signature is
    intentionally narrow so we don't depend on the provider implementation.
    """
    candidates = (
        ("services.sms", "send_sms"),
        ("apps.notifications.sms", "send_sms"),
    )
    for module_path, attr in candidates:
        try:
            module = __import__(module_path, fromlist=[attr])
        except ImportError:
            continue
        sender = getattr(module, attr, None)
        if callable(sender):
            return sender
    return None


def _dispatch_webhook(sub, incident, kind: str, status_url: str, payload_label: str) -> DispatchResult:
    """POST a JSON payload to a Slack-compatible or Discord-compatible webhook.

    Slack and Discord both accept a top-level ``text``/``content`` field; we
    emit a compact line that covers both surfaces. The webhook URL is the
    subscriber's chosen address — validation lives at subscribe time
    (``views_public_status.public_status_subscribe``).
    """
    webhook_url = sub.address.strip()
    if not webhook_url.startswith(("https://hooks.slack.com/", "https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/")):
        return DispatchResult(ok=False, detail="bad-webhook-url")

    text_line = (
        f"*RunMyCampus status* — {incident.get_severity_display()} "
        f"{kind}: *{incident.title[:120]}* "
        f"({incident.get_status_display()}) · {status_url}"
    )
    if "discord" in webhook_url:
        payload = {"content": text_line[:1900], "username": "RunMyCampus status"}
    else:
        payload = {"text": text_line[:2900], "username": "RunMyCampus status"}  # magic-number-allow: ai-message-char-cap

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SECONDS) as resp:  # nosec: subscriber-provided URL accepted by design
            ok = 200 <= resp.status < 300
            return DispatchResult(ok=ok, detail=f"status={resp.status}")
    except urllib.error.HTTPError as exc:
        return DispatchResult(ok=False, detail=f"http-{exc.code}")
    except urllib.error.URLError as exc:
        return DispatchResult(ok=False, detail=f"url-error:{type(exc).__name__}")
    except Exception as exc:  # noqa: BLE001 — best-effort fan-out
        logger.debug("public_status: webhook dispatch failed", exc_info=True)
        return DispatchResult(ok=False, detail=f"raised:{type(exc).__name__}")


def dispatch_to_subscriber(
    sub,
    incident,
    kind: str,
    *,
    status_url: str,
    unsub_url: str,
) -> DispatchResult:
    """Route a subscriber notification to the right channel adapter."""
    channel = (sub.channel or "EMAIL").upper()
    subject, body = _build_subject_and_body(incident, kind, status_url, unsub_url)
    if channel == "EMAIL":
        return _dispatch_email(sub, incident, subject, body)
    if channel == "SMS":
        return _dispatch_sms(sub, incident, body)
    if channel in ("SLACK", "DISCORD"):
        return _dispatch_webhook(sub, incident, kind, status_url, payload_label=channel)
    return DispatchResult(ok=False, detail=f"unknown-channel:{channel}")


def validate_address(channel: str, address: str) -> Optional[str]:
    """Return None when valid, or a short error code when not."""
    channel = (channel or "EMAIL").upper()
    address = (address or "").strip()
    if channel == "EMAIL":
        if "@" not in address or "." not in address.split("@")[-1]:
            return "bad-email"
        return None
    if channel == "SMS":
        digits = address.lstrip("+")
        if not digits.isdigit() or not (6 <= len(digits) <= 15):
            return "bad-phone"
        return None
    if channel == "SLACK":
        if not address.startswith("https://hooks.slack.com/"):
            return "bad-slack-url"
        return None
    if channel == "DISCORD":
        if not (
            address.startswith("https://discord.com/api/webhooks/")
            or address.startswith("https://discordapp.com/api/webhooks/")
        ):
            return "bad-discord-url"
        return None
    return "unknown-channel"
