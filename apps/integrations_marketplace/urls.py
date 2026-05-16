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
]
