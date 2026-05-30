"""URL routes for the integrations marketplace hub + OAuth dance."""

from __future__ import annotations

from django.urls import path

from apps.integrations_marketplace import views, webhooks
from apps.integrations_marketplace import views_studio_os_10x_w1 as s10x

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
    # v4.00.91 Studio-OS-10X W1 Pillar A — 14 operator UI surfaces.
    path("studio-os-10x/",                              s10x.studio_home,                   name="s10x_home"),
    path("studio-os-10x/quick-actions/",                s10x.quick_actions,                 name="s10x_quick_actions"),
    path("studio-os-10x/oauth-metrics/",                s10x.oauth_metrics_dashboard,       name="s10x_oauth_metrics"),
    path("studio-os-10x/saml-idp-registry/",            s10x.saml_idp_registry,             name="s10x_saml_idp_registry"),
    path("studio-os-10x/lms-provider-rollup/",          s10x.lms_provider_rollup,           name="s10x_lms_rollup"),
    path("studio-os-10x/retention-preview/",            s10x.retention_preview_historical,  name="s10x_retention_preview"),
    path("studio-os-10x/dlq-filter-nav/",               s10x.dlq_filter_nav,                name="s10x_dlq_filter_nav"),
    path("studio-os-10x/audit-packet-export/",          s10x.audit_packet_export,           name="s10x_audit_packet_export"),
    path("studio-os-10x/diagnostics-alarms/",           s10x.diagnostics_alarm_panel,       name="s10x_diagnostics_alarms"),
    path("studio-os-10x/pki-bundle-viewer/",            s10x.pki_bundle_viewer,             name="s10x_pki_bundle_viewer"),
    path("studio-os-10x/tenant-retention-override/",    s10x.tenant_retention_override,     name="s10x_tenant_retention_override"),
    path("studio-os-10x/token-rotation-timeline/",      s10x.token_rotation_timeline,       name="s10x_token_rotation_timeline"),
    path("studio-os-10x/billing-summary/",              s10x.billing_summary,               name="s10x_billing_summary"),
    path("studio-os-10x/nav-sidebar/",                  s10x.studio_nav_sidebar,            name="s10x_nav_sidebar"),
]
