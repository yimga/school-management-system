"""
v2.89 follow-up — Django signals fired by the integrations marketplace.

`webhook_received` is the canonical hook for **per-tenant business logic**
that needs to react to an inbound webhook AFTER:
  - the HMAC signature has been verified by `webhooks._verify`
  - the row has been bound to one (school, campus, connector_slug) tuple
  - the connector-specific handler in `webhook_handlers.py` has audited
    and decided which event_type the payload represents

Receivers subscribe with the standard Django pattern:

    from django.dispatch import receiver
    from apps.integrations_marketplace.signals import webhook_received

    @receiver(webhook_received)
    def my_handler(sender, *, row, connector, event_type, payload, **kw):
        if connector == "zoom" and event_type == "recording.completed":
            ...

The sender is always the string `"integrations_marketplace.webhook"` so
receivers can wildcard-subscribe (`receiver(webhook_received)`) and filter
in their body, which is more ergonomic than per-connector signal classes.

Why a signal not a hardcoded dispatcher:
  - Receivers can live in any app (apps.communication, apps.evaluations,
    apps.lms_integrations, ...) without the marketplace having to know
    about them.
  - Multiple subscribers per event are natural — e.g. zoom recording
    triggers both an evidence-archive write AND a parent-notify task.
  - Receivers self-isolate failures — Django's signal dispatcher catches
    per-receiver exceptions and continues. The marketplace's ack to the
    upstream is never blocked by a subscriber crash.
"""

from __future__ import annotations

from django.dispatch import Signal

# Args (kwargs, per Django convention):
#   row: ServiceIntegration row the inbound payload was bound to
#   connector: lowercase connector slug (e.g. "zoom", "slack")
#   event_type: connector-native event name (e.g. "recording.completed",
#               "events_api.message", "endpoint.url_validation")
#   payload: parsed JSON body (dict). Never None.
webhook_received = Signal()


# v2.100 — fired by the mailbox fetch loop (`mailbox_fetch.py`) once per new
# message pulled from gmail / outlook_mail. Kwargs:
#   row:       ServiceIntegration row
#   provider:  "gmail" | "outlook_mail"
#   message:   dict — provider-native message payload (headers + snippet + id)
# Per-tenant code subscribes to drive help-desk ticket creation, auto-reply
# detection, parent-message routing, etc.
mailbox_message_received = Signal()


# v3.4 — connection lifecycle. Fired by oauth.persist_oauth_tokens AFTER the
# row is upserted (connected) and by views.disconnect / bulk_disconnect AFTER
# the row is flipped to is_active=False (disconnected). Per-app cleanup
# (retire stored channel_ids, drop cached state, send a notification) plugs
# in here. Sender is always the string `"integrations_marketplace.connector"`.
#
# Kwargs:
#   row:       ServiceIntegration row (always present)
#   connector: lowercase slug (always present)
#   school:    School instance (always present)
#   campus:    Campus or None
#   action:    "connected" | "reconnected" | "disconnected" | "bulk_disconnected"
connector_connected = Signal()
connector_disconnected = Signal()


__all__ = [
    "connector_connected",
    "connector_disconnected",
    "mailbox_message_received",
    "webhook_received",
]
