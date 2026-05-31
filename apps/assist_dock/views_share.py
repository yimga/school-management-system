"""v4.00.95 Wave E5 — share short-link endpoints (+ Wave F4 recipients)."""

from __future__ import annotations

import json
import logging
import re

from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseRedirect,
    JsonResponse,
)
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_safe

from .short_links import (
    SHORT_LINK_DEFAULT_TTL_HOURS,
    SHORT_LINK_MAX_TTL_HOURS,
    mint_short_link,
    record_short_link_hit,
    resolve_short_link,
)

# Conservative RFC 5321-ish address shape; we don't pretend to be a full
# email validator — this is just a "looks like an address" gate.
_EMAIL_RE = re.compile(r"^[^\s@]{1,64}@[^\s@]{3,255}\.[^\s@]{2,24}$")

# Caps for the recipient picker.
_MAX_RECIPIENTS_PER_MINT = 12
_MAX_RECIPIENT_LEN = 320

_MAX_MINT_BODY_BYTES = 4 * 1024


@login_required
@require_http_methods(["POST"])
@csrf_protect
def mint_share_link(request):
    """Body: ``{"target": "/portal/dashboard/", "ttl_hours": 24}``."""
    raw = request.body or b""
    if len(raw) > _MAX_MINT_BODY_BYTES:
        return HttpResponseBadRequest("payload too large")
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("bad json")
    if not isinstance(body, dict):
        return HttpResponseBadRequest("body must be object")
    target = str(body.get("target") or "")
    ttl_hours = body.get("ttl_hours", SHORT_LINK_DEFAULT_TTL_HOURS)
    try:
        ttl_hours = int(ttl_hours)
    except (TypeError, ValueError):
        ttl_hours = SHORT_LINK_DEFAULT_TTL_HOURS
    link, err = mint_short_link(
        target_url=target, created_by=request.user, ttl_hours=ttl_hours
    )
    if link is None:
        return JsonResponse({"ok": False, "error": err}, status=400)
    short_path = "/assist-dock/s/" + link.token + "/"
    absolute = request.build_absolute_uri(short_path)
    return JsonResponse(
        {
            "ok": True,
            "token": link.token,
            "short_path": short_path,
            "short_url": absolute,
            "expires_at": link.expires_at.isoformat() if link.expires_at else None,
            "ttl_hours_max": SHORT_LINK_MAX_TTL_HOURS,
        }
    )


@login_required
@require_http_methods(["POST"])
@csrf_protect
def mint_and_email_share_link(request):
    """v4.00.96 Wave F4 — recipient picker + email send.

    Body:
      ``{"target": "/portal/x/", "ttl_hours": 24, "recipients": ["a@x", ...], "note": "..."}``

    Mints a short link AND emails each recipient. Records per-recipient
    receipts in ``AssistDockShortLinkRecipient`` so the operator gets a
    paper trail. Email send is best-effort: failures land as
    ``send_status="failed"`` on the receipt row but the link is still
    returned for clipboard fallback.
    """
    raw = request.body or b""
    if len(raw) > _MAX_MINT_BODY_BYTES * 4:
        return HttpResponseBadRequest("payload too large")
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("bad json")
    if not isinstance(body, dict):
        return HttpResponseBadRequest("body must be object")

    target = str(body.get("target") or "")
    ttl_hours = body.get("ttl_hours", SHORT_LINK_DEFAULT_TTL_HOURS)
    try:
        ttl_hours = int(ttl_hours)
    except (TypeError, ValueError):
        ttl_hours = SHORT_LINK_DEFAULT_TTL_HOURS
    note = str(body.get("note") or "")[:200]

    raw_recipients = body.get("recipients") or []
    if not isinstance(raw_recipients, list):
        return HttpResponseBadRequest("recipients must be array")
    recipients = _sanitize_recipients(raw_recipients)
    if not recipients:
        return HttpResponseBadRequest("at least one valid recipient required")

    link, err = mint_short_link(
        target_url=target, created_by=request.user, ttl_hours=ttl_hours
    )
    if link is None:
        return JsonResponse({"ok": False, "error": err}, status=400)

    short_path = "/assist-dock/s/" + link.token + "/"
    absolute = request.build_absolute_uri(short_path)
    sender_label = _sender_label(request.user)
    subject = f"{sender_label} shared a RunMyCampus view"
    text_body = _build_email_body(
        sender_label=sender_label,
        absolute_url=absolute,
        note=note,
        ttl_hours=ttl_hours,
    )

    receipts = []
    for address in recipients:
        status = "failed"
        notes = ""
        try:
            sent = send_mail(
                subject,
                text_body,
                None,  # use DEFAULT_FROM_EMAIL
                [address],
                fail_silently=False,
            )
            status = "sent" if sent else "failed"
        except Exception as exc:  # noqa: BLE001 — email backends raise broadly
            notes = str(exc)[:256]
            logger.debug("share email to %s failed: %s", address, exc)
        try:
            from .models import AssistDockShortLinkRecipient

            # tenant-isolation-allow: assist-dock-share-recipient-receipt-link-fk-public-schema-shared
            AssistDockShortLinkRecipient.objects.create(
                short_link=link,
                address=address[:_MAX_RECIPIENT_LEN],
                send_status=status,
                notes=notes,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("share recipient receipt write failed: %s", exc)
        receipts.append({"address": address, "send_status": status})

    return JsonResponse(
        {
            "ok": True,
            "token": link.token,
            "short_path": short_path,
            "short_url": absolute,
            "expires_at": link.expires_at.isoformat() if link.expires_at else None,
            "recipients": receipts,
            "sent_count": sum(1 for r in receipts if r["send_status"] == "sent"),
        }
    )


def _sanitize_recipients(raw_list: list) -> list[str]:
    """Lowercase, dedupe, validate shape, cap count."""
    seen: set[str] = set()
    out: list[str] = []
    for entry in raw_list:
        if not entry:
            continue
        address = str(entry).strip().lower()[:_MAX_RECIPIENT_LEN]
        if not address or address in seen:
            continue
        if not _EMAIL_RE.match(address):
            continue
        seen.add(address)
        out.append(address)
        if len(out) >= _MAX_RECIPIENTS_PER_MINT:
            break
    return out


def _sender_label(user) -> str:
    for attr in ("get_full_name", "get_short_name"):
        getter = getattr(user, attr, None)
        if callable(getter):
            try:
                value = getter()
                if value:
                    return str(value)[:80]
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
    for attr in ("username", "email"):
        value = getattr(user, attr, "") or ""
        if value:
            return str(value)[:80]
    return "A RunMyCampus user"


def _build_email_body(*, sender_label: str, absolute_url: str, note: str, ttl_hours: int) -> str:
    lines = [
        f"{sender_label} shared a RunMyCampus view with you.",
        "",
        absolute_url,
        "",
        f"This link expires in {ttl_hours} hour(s).",
    ]
    if note:
        lines.extend(["", "Note:", note])
    lines.append("")
    lines.append("— RunMyCampus")
    return "\n".join(lines)


@require_safe
def resolve_share_link(request, token):
    """Public 302 redirect to the saved target URL — gone after expiry.

    Note: no @login_required here so a recipient who isn't on the platform
    can still follow the link; the underlying target enforces its own auth.
    """
    link = resolve_short_link(token)
    if link is None:
        return HttpResponse("Link expired or not found.", status=410)
    record_short_link_hit(link)
    target = link.target_url
    if not target:
        return HttpResponse("Link malformed.", status=410)
    return HttpResponseRedirect(target)
