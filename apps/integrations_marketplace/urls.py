"""URL routes for the integrations marketplace hub + OAuth dance."""

from __future__ import annotations

from django.urls import path

from apps.integrations_marketplace import views, webhooks

app_name = "integrations_marketplace"

urlpatterns = [
    path("", views.integrations_hub, name="hub"),
    path("connect/<slug:connector_slug>/", views.oauth_connect, name="oauth_connect"),
    path(
        "callback/<slug:connector_slug>/",
        views.oauth_callback,
        name="oauth_callback",
    ),
    path(
        "disconnect/<slug:connector_slug>/",
        views.disconnect,
        name="disconnect",
    ),
    path(
        "disconnect/<slug:connector_slug>/<int:campus_id>/",
        views.disconnect,
        name="disconnect_campus",
    ),
    # Wave v2.76 — inbound webhook receiver (Slack events, Zoom recording-completed,
    # Microsoft Graph subscription, etc.). HMAC-verified per integration_id.
    path(
        "webhook/<slug:connector_slug>/<int:integration_id>/",
        webhooks.webhook_receiver,
        name="webhook_receiver",
    ),
    # Wave v2.76 — platform-owner-facing redirect URI registry surface.
    path("admin/redirect-uris/", views.redirect_uri_registry, name="redirect_uri_registry"),
    # Wave v2.79 follow-up — all-campuses rollup table for multi-campus schools.
    path("rollup/", views.integrations_rollup, name="rollup"),
    # Wave v2.89 — tenant-scoped webhook delivery log (queries compliance.AuditLog).
    path("events/", views.integrations_events, name="events"),
    # Wave v2.94 — operator-triggered synthetic webhook delivery.
    path(
        "test-webhook/<slug:connector_slug>/<int:integration_id>/",
        views.test_webhook, name="test_webhook",
    ),
    # Wave v2.94 — per-tenant OAuth scope override UI.
    path(
        "scopes/<slug:connector_slug>/",
        views.scope_override, name="scope_override",
    ),
    # Wave v2.100 — webhook REJECTION log (failures that didn't pass HMAC/rate-limit).
    path("rejections/", views.integrations_rejections, name="rejections"),
    # Wave v3.4 — operator one-click webhook secret rotation.
    path(
        "rotate-secret/<slug:connector_slug>/<int:integration_id>/",
        views.rotate_webhook_secret, name="rotate_webhook_secret",
    ),
    # Wave v3.4 — tenant kill-switch: disable every row for a connector.
    path(
        "bulk-disconnect/<slug:connector_slug>/",
        views.bulk_disconnect, name="bulk_disconnect",
    ),
    # Wave v3.4 — FERPA/GDPR data inventory CSV export.
    path(
        "data-inventory.csv",
        views.integrations_data_inventory_csv, name="data_inventory_csv",
    ),
]
