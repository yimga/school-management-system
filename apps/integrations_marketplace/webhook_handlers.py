"""
First-party webhook handlers for the integrations marketplace.

Each handler is registered against a connector slug via
`@register_webhook_handler("<slug>")` and receives:

    handler(row: ServiceIntegration, payload: dict) -> HttpResponse

The receiver in `webhooks.py` has already:
  - verified the HMAC signature (default scheme OR connector-specific, e.g.
    Slack's `v0:{ts}:{body}` variant)
  - bound `row` to a single (school, campus, connector_slug) tuple

Handlers do NOT need to re-verify. They MUST:
  - return an HttpResponse (200 / 204 for ack; 4xx only for *connector-required*
    refusals like Slack's URL-verification challenge mismatch)
  - never re-raise; any exception is caught one level up and turned into a 500
  - persist tenant-scoped side-effects to `row.school` only
    (`row.campus` is optional context)

Handlers landed in v2.79 — start narrow (challenge / ack / audit-log) so the
inbound side is no longer plumbing-only. Richer per-event business logic
(create attendance records from Zoom participants, file a help-desk ticket
from a Slack slash command, etc.) lands per-school as use-cases mature.
"""

from __future__ import annotations

import logging
from typing import Any

from django.http import HttpResponse, JsonResponse

from apps.integrations_marketplace.signals import webhook_received
from apps.integrations_marketplace.webhooks import register_webhook_handler
from apps.siteconfig.models_platform_catalog import ServiceIntegration

logger = logging.getLogger(__name__)


def _audit(connector: str, row: ServiceIntegration, event_type: str, payload: dict) -> None:
    """Best-effort audit trail + fan-out via Django signal.

    Two responsibilities, in this order:
      1. Persist a row in `compliance.AuditLog` so the events log view has
         tenant-scoped history (and `_audit` failures are swallowed — the
         upstream ack must never depend on logging).
      2. Fire `signals.webhook_received` so per-tenant business logic in
         other apps (apps.communication, apps.evaluations, ...) can react.
         Django's dispatcher catches per-receiver exceptions, so a buggy
         subscriber can't tear down the rest.

    Lazy imports so AppConfig.ready() works without hard-pinning the
    compliance app, and so test rigs that swap AuditLog don't blow up.
    """
    school_id = (
        getattr(row.school, "pk", None) if getattr(row, "school", None) else None
    )
    campus_id = (
        getattr(row.campus, "pk", None) if getattr(row, "campus", None) else None
    )
    payload_keys = list(payload.keys()) if isinstance(payload, dict) else []

    try:
        from apps.compliance.models_audit import AuditLog
    except ImportError:
        logger.info(
            "Webhook audit (compliance.models_audit unavailable): "
            "connector=%s school_id=%s campus_id=%s event=%s keys=%s",
            connector, school_id, campus_id, event_type, payload_keys,
        )
        return
    try:
        # Action choice CREATE = "a new inbound event arrived". The webhook
        # connector + school + campus context lives in new_values so per-tenant
        # dashboards can filter without a schema change.
        AuditLog.objects.create(
            user=None,
            action=AuditLog.Action.CREATE,
            model_name="ServiceIntegration",
            object_id=str(row.pk),
            object_repr=f"{connector}#{row.pk}",
            sensitivity=AuditLog.Sensitivity.LOW,
            app_label="integrations_marketplace",
            reason=f"webhook:{event_type}",
            new_values={
                "connector": connector,
                "school_id": school_id,
                "campus_id": campus_id,
                "event_type": event_type,
                "payload_keys": payload_keys,
            },
        )
    except Exception:  # noqa: BLE001 — audit is best-effort, never block the ack
        logger.exception(
            "Failed to write AuditLog for webhook: connector=%s row_id=%s",
            connector, row.pk,
        )

    # Fan-out to per-tenant subscribers. Django's dispatcher catches
    # per-receiver exceptions so a buggy listener can't take down the ack.
    try:
        webhook_received.send_robust(
            sender="integrations_marketplace.webhook",
            row=row,
            connector=connector,
            event_type=event_type,
            payload=payload if isinstance(payload, dict) else {},
        )
    except Exception:  # noqa: BLE001 — signal dispatch must never block ack
        logger.exception(
            "webhook_received signal dispatch crashed: connector=%s row_id=%s",
            connector, row.pk,
        )


# ---------------------------------------------------------------------------
# Slack — handles the one-time URL verification challenge + event ack.
# https://api.slack.com/events/url_verification
# https://api.slack.com/apis/connections/events-api
# ---------------------------------------------------------------------------

@register_webhook_handler("slack")
def handle_slack(row: ServiceIntegration, payload: dict) -> HttpResponse:
    event_type = str(payload.get("type") or "").strip()

    # 1. URL verification handshake (Slack sends this once when the operator
    #    pastes our receiver URL into the app config). Echo `challenge` back.
    if event_type == "url_verification":
        challenge = str(payload.get("challenge") or "").strip()
        if not challenge:
            return JsonResponse({"error": "missing_challenge"}, status=400)
        return JsonResponse({"challenge": challenge})

    # 2. Real events_api callback wrapping an inner event.
    if event_type == "event_callback":
        inner = payload.get("event") or {}
        inner_type = str(inner.get("type") or "").strip() or "unknown"
        _audit("slack", row, f"events_api.{inner_type}", inner if isinstance(inner, dict) else {})
        return HttpResponse(status=200)

    # 3. Anything else (interactivity, slash commands) — audit + ack so Slack
    #    doesn't retry. Real per-tenant business logic plugs in per-school.
    _audit("slack", row, event_type or "unknown", payload)
    return HttpResponse(status=200)


# ---------------------------------------------------------------------------
# Zoom — `recording.completed` is the headline event we want for compliance
# (every meeting recording is auditable in the tenant's school timeline).
# https://developers.zoom.us/docs/api/rest/webhook-reference/meeting-events/
# ---------------------------------------------------------------------------

@register_webhook_handler("zoom")
def handle_zoom(row: ServiceIntegration, payload: dict) -> HttpResponse:
    event_type = str(payload.get("event") or "").strip()

    # Zoom's CRC validation handshake (sent once on URL registration when the
    # app uses the "Validate" challenge mode). Echo the plain + signed token.
    if event_type == "endpoint.url_validation":
        plain = str((payload.get("payload") or {}).get("plainToken") or "").strip()
        if plain:
            import hashlib
            import hmac
            secret = str((row.config or {}).get("webhook_secret") or "").strip()
            encrypted = hmac.new(
                secret.encode("utf-8"), plain.encode("utf-8"), hashlib.sha256
            ).hexdigest()
            return JsonResponse({"plainToken": plain, "encryptedToken": encrypted})

    _audit("zoom", row, event_type or "unknown", payload.get("payload") or {})
    return HttpResponse(status=200)


# ---------------------------------------------------------------------------
# Microsoft Graph — subscription endpoint MUST echo `validationToken` query
# parameter on subscription registration, then receives change notifications.
# https://learn.microsoft.com/en-us/graph/webhooks
# ---------------------------------------------------------------------------

def _graph_validation_response(row: ServiceIntegration, payload: dict) -> HttpResponse | None:
    """Graph validation: a plain-text echo of the validationToken query string.

    The token reaches us via the request body OR query string depending on the
    Graph API version — we accept either; the receiver hands us `payload` from
    the body, and we cannot see the query string at this layer, so callers MUST
    embed the token in the body or use the receiver's `request.GET` directly.
    We honor both shapes the SDK has used historically.
    """
    token = str(payload.get("validationToken") or "").strip()
    if not token:
        return None
    return HttpResponse(token, content_type="text/plain")


@register_webhook_handler("microsoft_teams")
def handle_microsoft_teams(row: ServiceIntegration, payload: dict) -> HttpResponse:
    validation = _graph_validation_response(row, payload)
    if validation is not None:
        return validation
    notifications = payload.get("value") or []
    for n in notifications if isinstance(notifications, list) else []:
        _audit(
            "microsoft_teams",
            row,
            str((n or {}).get("changeType") or "unknown"),
            n if isinstance(n, dict) else {},
        )
    return HttpResponse(status=202)


@register_webhook_handler("outlook_calendar")
def handle_outlook_calendar(row: ServiceIntegration, payload: dict) -> HttpResponse:
    validation = _graph_validation_response(row, payload)
    if validation is not None:
        return validation
    notifications = payload.get("value") or []
    for n in notifications if isinstance(notifications, list) else []:
        _audit(
            "outlook_calendar",
            row,
            str((n or {}).get("changeType") or "unknown"),
            n if isinstance(n, dict) else {},
        )
    return HttpResponse(status=202)


@register_webhook_handler("outlook_mail")
def handle_outlook_mail(row: ServiceIntegration, payload: dict) -> HttpResponse:
    validation = _graph_validation_response(row, payload)
    if validation is not None:
        return validation
    notifications = payload.get("value") or []
    for n in notifications if isinstance(notifications, list) else []:
        _audit(
            "outlook_mail",
            row,
            str((n or {}).get("changeType") or "unknown"),
            n if isinstance(n, dict) else {},
        )
    return HttpResponse(status=202)


# ---------------------------------------------------------------------------
# Google Calendar — push notifications carry change metadata only; the
# receiver pulls the actual delta via the Calendar API. The notification
# headers (X-Goog-Channel-ID, X-Goog-Resource-State) are the real signal;
# the body is empty for `exists`/`sync` events.
# https://developers.google.com/calendar/api/guides/push
# ---------------------------------------------------------------------------

@register_webhook_handler("google_calendar")
def handle_google_calendar(row: ServiceIntegration, payload: dict) -> HttpResponse:
    # The body is typically empty; the receiver passed us `{}`. We just ack
    # so Google doesn't retry; the per-tenant sync worker fetches deltas
    # using the channel ID + resource ID it persisted at subscribe time.
    _audit("google_calendar", row, "push_notification", payload or {})
    return HttpResponse(status=200)


# ---------------------------------------------------------------------------
# Stripe — webhook signature is verified in the default verifier (operator
# pastes Stripe's signing secret as `config["webhook_secret"]`). We ack and
# audit; real billing-event handling rides on apps.finance.
# ---------------------------------------------------------------------------

@register_webhook_handler("stripe")
def handle_stripe(row: ServiceIntegration, payload: dict) -> HttpResponse:
    event_type = str(payload.get("type") or "").strip() or "unknown"
    _audit("stripe", row, event_type, payload.get("data") or {})
    return HttpResponse(status=200)


__all__ = [
    "handle_google_calendar",
    "handle_microsoft_teams",
    "handle_outlook_calendar",
    "handle_outlook_mail",
    "handle_slack",
    "handle_stripe",
    "handle_zoom",
]
