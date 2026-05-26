"""Wave H (v3.95.0 — 2026-05-26) — Meta WhatsApp Business webhook receiver.

Three responsibilities:

1. GET verification handshake (subscribe to webhook).
2. POST inbound message: verify HMAC signature, parse, hand to the Parent OS
   kernel (:mod:`whatsapp_parent_os`), send the outbound response.
3. Feature-flag gating: ignores all traffic when
   ``whatsapp_parent_os_enabled`` is False for the tenant.

NO PII is logged. Phone numbers are hashed before any audit row.
"""

from __future__ import annotations

import json
import logging

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .integrations import WhatsAppIntegration
from .whatsapp_parent_os import (
    InboundMessage,
    RoutingConfig,
    route_inbound_message,
)


logger = logging.getLogger(__name__)


def _hash_phone(phone: str) -> str:
    import hashlib
    if not phone:
        return ""
    return hashlib.sha256(phone.encode("utf-8")).hexdigest()[:12]


def _tenant_id_for_request(request: HttpRequest) -> str:
    """Resolve the tenant id from the request. Meta does not include tenant
    information so we use the host header to derive it. Returns "" when
    indeterminate (caller may still process anonymous traffic in dev)."""
    school = getattr(request, "school", None)
    if school is not None:
        return str(getattr(school, "pk", "") or getattr(school, "id", "") or "")
    return ""


def _is_enabled_for_tenant(request: HttpRequest) -> bool:
    """Check the tenant's ``whatsapp_parent_os_enabled`` flag — defaults to
    False everywhere. Fail-closed."""
    try:
        from apps.platform_runtime.helpers import get_effective_flags  # type: ignore
        flags = get_effective_flags(request) or {}
    except Exception:  # noqa: BLE001
        flags = {}
    return bool(flags.get("whatsapp_parent_os_enabled"))


def _parse_meta_webhook(payload: dict) -> list[InboundMessage]:
    """Parse Meta's WhatsApp Cloud API webhook envelope into our InboundMessage.

    Schema reference (Meta v17+):
    {"entry": [{"changes": [{"value": {"messages": [...], "contacts": [...]}}]}]}
    """
    out: list[InboundMessage] = []
    if not isinstance(payload, dict):
        return out
    for entry in payload.get("entry", []) or []:
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes", []) or []:
            if not isinstance(change, dict):
                continue
            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue
            for msg in value.get("messages", []) or []:
                if not isinstance(msg, dict):
                    continue
                msg_type = (msg.get("type") or "").lower()
                from_phone = (msg.get("from") or "").strip()
                msg_id = (msg.get("id") or "").strip()
                if msg_type == "text":
                    body = ((msg.get("text") or {}).get("body") or "").strip()
                    button_payload = ""
                elif msg_type == "button":
                    body = ((msg.get("button") or {}).get("text") or "").strip()
                    button_payload = ((msg.get("button") or {}).get("payload") or "").strip()
                elif msg_type == "interactive":
                    inter = msg.get("interactive") or {}
                    br = inter.get("button_reply") or inter.get("list_reply") or {}
                    body = (br.get("title") or "").strip()
                    button_payload = (br.get("id") or "").strip()
                else:
                    # Unsupported types (image / audio / location etc.) — ignored
                    # for now. Wave H+1 can add media handling.
                    continue
                if not from_phone:
                    continue
                out.append(
                    InboundMessage(
                        from_phone=from_phone,
                        body=body,
                        tenant_id="",  # filled in by caller
                        button_payload=button_payload,
                        message_id=msg_id,
                    )
                )
    return out


@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp_webhook(request: HttpRequest) -> HttpResponse:
    """Meta WhatsApp webhook endpoint.

    Wired at ``/comms/whatsapp/webhook/`` (see :mod:`apps.communication.urls`).
    """
    integration = WhatsAppIntegration(school=getattr(request, "school", None))

    if request.method == "GET":
        # Verification handshake.
        if integration.verify_webhook(request):
            challenge = (request.GET.get("hub.challenge") or "").strip()
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponse("forbidden", status=403)

    # POST — inbound event delivery.
    if not integration.verify_webhook(request):
        # Don't leak which check failed. Always 403 on bad signature.
        return HttpResponse("forbidden", status=403)

    if not _is_enabled_for_tenant(request):
        # Tenant has not opted in. Acknowledge the delivery (Meta requires 2xx
        # within 20s or they retry) but do nothing.
        return JsonResponse({"status": "disabled"}, status=200)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"status": "invalid_json"}, status=400)

    tenant_id = _tenant_id_for_request(request)
    inbound_msgs = _parse_meta_webhook(payload)

    config = _load_routing_config_for_tenant(request)
    default_locale = _default_locale_for_tenant(request)
    handled = 0
    for inb in inbound_msgs:
        # Fill in tenant_id resolved from request scope. When the inbound
        # message has no locale (Meta rarely supplies one), fall back to the
        # tenant's ``whatsapp_parent_os_locale_default`` flag.
        inb = InboundMessage(
            from_phone=inb.from_phone,
            body=inb.body,
            tenant_id=tenant_id,
            locale=inb.locale or default_locale,
            message_id=inb.message_id,
            button_payload=inb.button_payload,
            received_at=inb.received_at,
        )
        try:
            outbound = route_inbound_message(inb, config=config)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "parent_os route failed phone=%s err=%s",
                _hash_phone(inb.from_phone), exc,
            )
            continue
        try:
            integration.send_message(inb.from_phone, outbound.body_text)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "parent_os send failed phone=%s intent=%s err=%s",
                _hash_phone(inb.from_phone), outbound.intent, exc,
            )
            continue
        handled += 1
        logger.info(
            "parent_os dispatched tenant=%s phone=%s intent=%s rate_limited=%s",
            tenant_id, _hash_phone(inb.from_phone),
            outbound.intent, outbound.rate_limited,
            extra={"scope": "whatsapp_parent_os.dispatch"},
        )

    return JsonResponse({"status": "ok", "handled": handled}, status=200)


def _default_locale_for_tenant(request: HttpRequest) -> str:
    """Resolve the tenant's ``whatsapp_parent_os_locale_default`` flag — used
    as a fallback when an inbound message has no locale (the common case for
    Meta payloads). Defaults to "en"."""
    try:
        from apps.platform_runtime.helpers import get_effective_flags  # type: ignore
        flags = get_effective_flags(request) or {}
    except Exception:  # noqa: BLE001
        flags = {}
    return str(flags.get("whatsapp_parent_os_locale_default") or "en")


def _load_routing_config_for_tenant(request: HttpRequest) -> RoutingConfig:
    """Resolve allowlist + rate limit + placeholder resolver from the
    tenant's effective flags."""
    try:
        from apps.platform_runtime.helpers import get_effective_flags  # type: ignore
        flags = get_effective_flags(request) or {}
    except Exception:  # noqa: BLE001
        flags = {}
    allowlist = tuple(flags.get("whatsapp_parent_os_intent_allowlist") or ())
    rate_limit = int(flags.get("whatsapp_parent_os_rate_limit_per_hour") or 30)
    kwargs: dict = {}
    if allowlist:
        kwargs["allowlist"] = allowlist
    if rate_limit:
        kwargs["rate_limit_per_hour"] = rate_limit
    # Wave P-D: wire the placeholder resolver that looks up guardian + student
    # records. Failures inside the resolver are swallowed by the kernel.
    try:
        from .whatsapp_parent_os_resolvers import resolve as _resolver
        kwargs["placeholder_resolver"] = _resolver
    except Exception:  # noqa: BLE001
        pass
    return RoutingConfig(**kwargs)
