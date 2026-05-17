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

# v2.94 — per-integration rate limit on the inbound receiver. Upstream gone
# wild = we eat the storm without this. Bucket key is (integration_id, ip)
# so a misbehaving relay can't drown other tenants' inbound traffic. Cache
# backend is shared with the rest of the platform (Redis in prod).
WEBHOOK_RATE_LIMIT_PER_MINUTE = 120
WEBHOOK_RATE_LIMIT_WINDOW_SECONDS = 60


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


def _client_ip(request: HttpRequest) -> str:
    """Best-effort client IP extraction respecting X-Forwarded-For."""
    xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return (request.META.get("REMOTE_ADDR") or "0.0.0.0").strip()


def rate_limit_check(
    *, scope: str, identifier: str, limit_per_minute: int,
    window_seconds: int = 60,
) -> bool:
    """v3.4 — unified per-(scope, identifier) rate-limit primitive.

    Shared by the webhook receiver and (in future) by `TenantApiQuotaMiddleware`
    so the rate-limit accounting story isn't fragmented across two systems.
    `scope` is a stable string like "webhook" or "api"; `identifier` is the
    per-actor key (e.g. `f"{integration_id}:{client_ip}"`). Returns True when
    the request is within budget; False when it should be denied. Falls open
    on cache outage — denying a customer because Redis blipped is worse than
    serving over-quota for a minute.
    """
    try:
        from django.core.cache import cache

        key = f"rl:{scope}:{identifier}"
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=window_seconds)
            count = 1
        return count <= int(limit_per_minute)
    except Exception:  # noqa: BLE001 — cache outage must not block legitimate traffic
        logger.warning("Rate-limit cache failed (scope=%s); falling open", scope)
        return True


def _rate_limit_ok(
    *, integration_id: int, request: HttpRequest,
    row: ServiceIntegration | None = None,
) -> bool:
    """Per-(integration_id, client_ip) webhook rate limit.

    v3.4 — honors a per-tenant override at `row.school.settings["webhook_rate_limit_per_minute"]`
    so a high-traffic school can be raised above the platform default without
    touching the constant.
    """
    limit = WEBHOOK_RATE_LIMIT_PER_MINUTE
    try:
        if row is not None and getattr(row, "school", None) is not None:
            school_settings = getattr(row.school, "settings", None) or {}
            override = school_settings.get("webhook_rate_limit_per_minute")
            if isinstance(override, int) and override > 0:
                limit = override
            elif isinstance(override, str) and override.isdigit():
                limit = int(override)
    except Exception:  # noqa: BLE001 — never let a settings lookup block traffic
        pass
    return rate_limit_check(
        scope="webhook",
        identifier=f"{integration_id}:{_client_ip(request)}",
        limit_per_minute=limit,
        window_seconds=WEBHOOK_RATE_LIMIT_WINDOW_SECONDS,
    )


def _persist_rejection(
    *, connector: str, row: ServiceIntegration, reason: str, client_ip: str
) -> None:
    """v2.100 — persist a rejected delivery to compliance.AuditLog so the
    operator-facing /integrations/rejections/ view has tenant-scoped history.

    Best-effort: any failure here is swallowed (logger.warning already fired
    upstream). Lazy import so apps without compliance still boot.
    """
    try:
        from apps.compliance.models_audit import AuditLog
    except ImportError:
        return
    try:
        school = getattr(row, "school", None) if row is not None else None
        AuditLog.objects.create(
            user=None,
            action=AuditLog.Action.ACCESS_DENIED,
            model_name="ServiceIntegration",
            object_id=str(getattr(row, "pk", "")),
            object_repr=f"{connector}#{getattr(row, 'pk', '?')}",
            sensitivity=AuditLog.Sensitivity.MEDIUM,
            app_label="integrations_marketplace",
            reason=f"webhook_rejected:{reason}",
            new_values={
                "connector": connector,
                "school_id": getattr(school, "pk", None) if school else None,
                "reason": reason,
                "client_ip": client_ip,
            },
        )
    except Exception:  # noqa: BLE001 — rejection logging is best-effort
        logger.exception(
            "Failed to persist webhook rejection: connector=%s reason=%s",
            connector, reason,
        )


def _verify(*, request: HttpRequest, row: ServiceIntegration) -> tuple[bool, str]:
    secret = str((row.config or {}).get("webhook_secret") or "").strip()
    if not secret:
        return False, "no_webhook_secret_configured"
    verifier = _SPECIAL_VERIFIERS.get(row.connector_slug.lower())
    fn = verifier if verifier is not None else _verify_default_signature
    ok, reason = fn(request=request, secret=secret)
    if ok:
        return True, reason
    # v3.4 — during the rotation grace window we also accept the prior secret
    # so a slow upstream-update doesn't immediately start failing. The grace
    # window is implicit: prev is only set right after rotation, and the
    # operator clears it (or it ages out next rotation).
    prev = str((row.config or {}).get("webhook_secret_prev") or "").strip()
    if prev and prev != secret:
        ok2, _ = fn(request=request, secret=prev)
        if ok2:
            return True, "ok_via_prev_secret"
    return False, reason


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

    # v2.94 — per-integration + per-IP rate limit. Check BEFORE HMAC verify
    # so a flood doesn't consume HMAC CPU budget.
    if not _rate_limit_ok(integration_id=integration_id, request=request, row=row):
        logger.warning(
            "Webhook rate-limited: connector=%s integration_id=%s ip=%s",
            connector_slug, integration_id, _client_ip(request),
        )
        _persist_rejection(connector=connector_slug, row=row, reason="rate_limited",
                           client_ip=_client_ip(request))
        resp = JsonResponse({"error": "rate_limited"}, status=429)
        resp["Retry-After"] = str(WEBHOOK_RATE_LIMIT_WINDOW_SECONDS)
        return resp

    ok, reason = _verify(request=request, row=row)
    if not ok:
        logger.warning(
            "Webhook rejected: connector=%s integration_id=%s reason=%s",
            connector_slug, integration_id, reason,
        )
        _persist_rejection(connector=connector_slug, row=row, reason=reason,
                           client_ip=_client_ip(request))
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
    "WEBHOOK_RATE_LIMIT_PER_MINUTE",
    "WEBHOOK_RATE_LIMIT_WINDOW_SECONDS",
    "_client_ip",
    "_rate_limit_ok",
    "rate_limit_check",
    "register_webhook_handler",
    "webhook_receiver",
]
