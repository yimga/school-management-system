"""
Inbound webhook receiver for connectors.

Each connector that pushes events back to us (Slack `events_api`, Discord
`webhook`, Zoom `recording_completed`, Microsoft Graph `subscription`, etc.)
needs a stable receiver URL with HMAC-SHA256 signature verification keyed to
its `ServiceIntegration` row.

URL grammar:
    POST /integrations/webhook/<connector_slug>/<integration_id>/

The `<integration_id>` lets us bind the inbound payload to one specific
`(school, campus, connector_slug)` row without leaking which connector belongs
to which tenant via URL guessing. The shared secret lives in
`ServiceIntegration.config["webhook_secret"]` (operator-generated, surfaced
in the hub UI).

Signature algorithm (default):
    header  = X-RMC-Signature
    value   = "v0={hex-sha256-hmac}"
    payload = "{timestamp}:{raw_body_bytes}"
    secret  = config["webhook_secret"]
    timestamp header = X-RMC-Timestamp (epoch seconds, ±300s window)

Connector-specific verifiers (Slack, Zoom, etc.) can override by setting
`config["webhook_signature_header"]` / `config["webhook_signature_algorithm"]`
on the row. The base verifier above is the default.

After verification, the request is dispatched to a connector-specific handler
via the `WEBHOOK_HANDLERS` registry (slug → callable). If no handler is
registered for that slug, the payload is logged + acknowledged with 204 so
upstream services don't retry forever.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any, Callable

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.integrations_marketplace.connector_registry import get_connector
from apps.siteconfig.models_platform_catalog import ServiceIntegration

logger = logging.getLogger(__name__)


SIGNATURE_WINDOW_SECONDS = 300  # 5-minute replay window
DEFAULT_SIGNATURE_HEADER = "X-RMC-Signature"
DEFAULT_TIMESTAMP_HEADER = "X-RMC-Timestamp"


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

WEBHOOK_HANDLERS: dict[str, Callable[[ServiceIntegration, dict], HttpResponse]] = {}


def register_webhook_handler(slug: str):
    """Decorator: register a connector-specific webhook handler.

    Usage:
        @register_webhook_handler("slack")
        def handle_slack(row, payload):
            ...
            return JsonResponse({"ok": True})
    """
    def _wrap(fn):
        WEBHOOK_HANDLERS[slug.lower()] = fn
        return fn
    return _wrap


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------

def _expected_signature(*, secret: str, timestamp: str, body: bytes) -> str:
    msg = f"{timestamp}:".encode("utf-8") + body
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def _verify_default_signature(
    *, request: HttpRequest, secret: str
) -> tuple[bool, str]:
    headers = getattr(request, "headers", {}) or {}
    raw_sig = (
        headers.get(DEFAULT_SIGNATURE_HEADER)
        or headers.get(DEFAULT_SIGNATURE_HEADER.lower())
        or ""
    ).strip()
    raw_ts = (
        headers.get(DEFAULT_TIMESTAMP_HEADER)
        or headers.get(DEFAULT_TIMESTAMP_HEADER.lower())
        or ""
    ).strip()
    if not raw_sig or not raw_ts:
        return False, "missing_signature_or_timestamp"
    try:
        ts = int(raw_ts)
    except (TypeError, ValueError):
        return False, "bad_timestamp"
    if abs(int(time.time()) - ts) > SIGNATURE_WINDOW_SECONDS:
        return False, "timestamp_outside_window"
    if not raw_sig.startswith("v0="):
        return False, "unknown_signature_format"
    candidate = raw_sig.split("=", 1)[1].strip()
    expected = _expected_signature(
        secret=secret, timestamp=raw_ts, body=request.body or b""
    )
    if hmac.compare_digest(candidate.lower(), expected.lower()):
        return True, "ok"
    return False, "signature_mismatch"


# ---------------------------------------------------------------------------
# Slack-specific verifier (Slack uses its own X-Slack-Signature scheme)
# ---------------------------------------------------------------------------

def _verify_slack_signature(*, request: HttpRequest, secret: str) -> tuple[bool, str]:
    headers = getattr(request, "headers", {}) or {}
    raw_sig = (
        headers.get("X-Slack-Signature") or headers.get("x-slack-signature") or ""
    ).strip()
    raw_ts = (
        headers.get("X-Slack-Request-Timestamp")
        or headers.get("x-slack-request-timestamp")
        or ""
    ).strip()
    if not raw_sig or not raw_ts:
        return False, "missing_slack_headers"
    try:
        ts = int(raw_ts)
    except (TypeError, ValueError):
        return False, "bad_slack_timestamp"
    if abs(int(time.time()) - ts) > SIGNATURE_WINDOW_SECONDS:
        return False, "slack_timestamp_outside_window"
    if not raw_sig.startswith("v0="):
        return False, "unknown_slack_format"
    body = request.body or b""
    base = f"v0:{raw_ts}:".encode("utf-8") + body
    expected = "v0=" + hmac.new(
        secret.encode("utf-8"), base, hashlib.sha256
    ).hexdigest()
    if hmac.compare_digest(raw_sig.lower(), expected.lower()):
        return True, "ok"
    return False, "slack_signature_mismatch"


_SPECIAL_VERIFIERS: dict[str, Callable[..., tuple[bool, str]]] = {
    "slack": _verify_slack_signature,
}


def _verify(*, request: HttpRequest, row: ServiceIntegration) -> tuple[bool, str]:
    secret = str((row.config or {}).get("webhook_secret") or "").strip()
    if not secret:
        return False, "no_webhook_secret_configured"
    verifier = _SPECIAL_VERIFIERS.get(row.connector_slug.lower())
    if verifier is not None:
        return verifier(request=request, secret=secret)
    return _verify_default_signature(request=request, secret=secret)


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

@csrf_exempt
@require_POST
def webhook_receiver(
    request: HttpRequest, connector_slug: str, integration_id: int
) -> HttpResponse:
    """Single inbound entry-point. Verify, dispatch, ack."""
    connector = get_connector(connector_slug)
    if connector is None:
        return JsonResponse(
            {"error": "unknown_connector", "slug": connector_slug}, status=404
        )
    row = ServiceIntegration.objects.filter(
        pk=integration_id, connector_slug__iexact=connector_slug, is_active=True
    ).first()
    if row is None:
        # Don't leak which IDs exist for which connectors.
        return JsonResponse({"error": "not_found"}, status=404)

    ok, reason = _verify(request=request, row=row)
    if not ok:
        logger.warning(
            "Webhook rejected: connector=%s integration_id=%s reason=%s",
            connector_slug, integration_id, reason,
        )
        return JsonResponse({"error": reason}, status=401)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (TypeError, ValueError):
        payload = {}

    handler = WEBHOOK_HANDLERS.get(connector_slug.lower())
    if handler is None:
        logger.info(
            "Webhook accepted but no handler registered: connector=%s integration_id=%s "
            "payload_keys=%s",
            connector_slug, integration_id, list(payload.keys()),
        )
        return HttpResponse(status=204)

    try:
        return handler(row, payload)
    except Exception:  # noqa: BLE001 — never echo handler errors upstream
        logger.exception(
            "Webhook handler crashed: connector=%s integration_id=%s",
            connector_slug, integration_id,
        )
        return JsonResponse({"error": "handler_error"}, status=500)


__all__ = [
    "DEFAULT_SIGNATURE_HEADER",
    "DEFAULT_TIMESTAMP_HEADER",
    "SIGNATURE_WINDOW_SECONDS",
    "WEBHOOK_HANDLERS",
    "register_webhook_handler",
    "webhook_receiver",
]
