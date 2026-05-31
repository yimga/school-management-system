"""v4.00.91 — assist dock URL placeholder.

Wave A registers the module so other apps can `include("apps.assist_dock.urls")`
without import errors; the endpoints land in Wave B (badges + page-aware
context fetch).
"""

from __future__ import annotations

from django.urls import path

from . import (
    power_views,
    views,
    views_ai,
    views_cursors,
    views_impersonation,
    views_presence,
    views_share,
    views_wave,
)

app_name = "assist_dock"

urlpatterns = [
    # Wave A — registry introspection (staff-only).
    # rbac-allow: assist-dock-registry-staff-introspection-staff-staff
    path(
        "registry.json",
        views.registry_introspect,
        name="registry_introspect",
    ),
    # Wave B — per-page context JSON the JS polls for badges + quick actions.
    # Auth-only. rbac-allow: assist-dock-context-poll-authenticated-user-scope
    path(
        "context.json",
        views.dock_context_view,
        name="context",
    ),
    # Wave E3 — SSE upgrade for live badge push.
    # rbac-allow: assist-dock-context-stream-authenticated-user-sse-channel
    path(
        "context/stream/",
        views.dock_context_stream_view,
        name="context_stream",
    ),
    # Wave C — power chip landings.
    # rbac-allow: assist-dock-translate-landing-authenticated-locale-picker
    path("translate/", power_views.translate_landing, name="translate"),
    # rbac-allow: assist-dock-share-landing-authenticated-page-url-sheet
    path("share/", power_views.share_landing, name="share"),
    # rbac-allow: assist-dock-theme-landing-authenticated-aesthetic-picker
    path("theme/", power_views.theme_landing, name="theme"),
    # rbac-allow: assist-dock-inspect-landing-super-only-rbac-overlay
    path("inspect/", power_views.inspect_landing, name="inspect"),
    # rbac-allow: assist-dock-impersonate-landing-super-only-role-switch
    path("impersonate/", power_views.impersonate_landing, name="impersonate"),
    # rbac-allow: assist-dock-prefs-authenticated-user-pk-own-row-public-schema-shared
    path("prefs.json", power_views.prefs_view, name="prefs"),
    # Wave D — AI deep features.
    # rbac-allow: assist-dock-ai-actions-list-authenticated-registry-introspection
    path("ai/actions.json", views_ai.list_ai_actions, name="ai_actions"),
    # rbac-allow: assist-dock-ai-invoke-authenticated-page-aware-action-dispatch
    path(
        "ai/<str:action_id>/",
        views_ai.invoke_ai_action_view,
        name="ai_invoke",
    ),
    # rbac-allow: assist-dock-insights-list-authenticated-user-pk-process-ring
    path("insights.json", views_ai.list_insights_view, name="insights"),
    # rbac-allow: assist-dock-insights-clear-authenticated-user-pk-own-ring-entry
    path(
        "insights/clear/",
        views_ai.clear_insight_view,
        name="insights_clear",
    ),
    # Wave E1 — presence chip.
    # rbac-allow: assist-dock-presence-heartbeat-authenticated-user-page-keyed
    path(
        "presence/heartbeat/",
        views_presence.presence_heartbeat,
        name="presence_heartbeat",
    ),
    # rbac-allow: assist-dock-presence-list-authenticated-page-keyed-exclude-self
    path(
        "presence/list.json",
        views_presence.presence_list,
        name="presence_list",
    ),
    # rbac-allow: assist-dock-presence-landing-authenticated-page-keyed-overlay
    path(
        "presence/",
        power_views.presence_landing,
        name="presence",
    ),
    # Wave E4 — drag-to-pin prefs editor.
    # rbac-allow: assist-dock-settings-landing-authenticated-user-prefs-editor
    path(
        "settings/",
        power_views.settings_landing,
        name="settings",
    ),
    # Wave E5 — 24h short links.
    # rbac-allow: assist-dock-share-mint-authenticated-user-target-allowed-host
    path(
        "share/mint/",
        views_share.mint_share_link,
        name="share_mint",
    ),
    # rbac-allow: assist-dock-share-resolve-anonymous-token-redirect-expires-24h-default
    path(
        "s/<str:token>/",
        views_share.resolve_share_link,
        name="share_resolve",
    ),
    # Wave F2 — wave at a co-viewer (pushes an Insight to their copilot ring).
    # rbac-allow: assist-dock-wave-at-authenticated-target-must-be-co-viewer-rate-limited
    path(
        "wave/",
        views_wave.wave_at_view,
        name="wave_at",
    ),
    # Wave F4 — recipient picker + email send (wraps share/mint).
    # rbac-allow: assist-dock-share-mint-and-email-authenticated-user-rfc5321-validated
    path(
        "share/mint-and-email/",
        views_share.mint_and_email_share_link,
        name="share_mint_and_email",
    ),
    # Wave G1 — pseudo-cobrowse cursor heartbeat + list.
    # rbac-allow: assist-dock-cursor-heartbeat-authenticated-user-in-memory-volatile-4hz
    path(
        "cursors/heartbeat/",
        views_cursors.cursor_heartbeat,
        name="cursor_heartbeat",
    ),
    # rbac-allow: assist-dock-cursor-list-authenticated-page-keyed-exclude-self
    path(
        "cursors/list.json",
        views_cursors.cursor_list,
        name="cursor_list",
    ),
    # Wave G2 — dual-control impersonation flow.
    # rbac-allow: assist-dock-impersonation-picker-super-only-dual-control-landing
    path(
        "impersonation/",
        views_impersonation.impersonation_picker,
        name="impersonation_picker",
    ),
    # rbac-allow: assist-dock-impersonation-request-super-only-create-requested-grant
    path(
        "impersonation/request/",
        views_impersonation.impersonation_request,
        name="impersonation_request",
    ),
    # rbac-allow: assist-dock-impersonation-approve-super-only-not-grantor-dual-control
    path(
        "impersonation/approve/",
        views_impersonation.impersonation_approve,
        name="impersonation_approve",
    ),
    # rbac-allow: assist-dock-impersonation-revoke-super-only-any-non-consumed-state
    path(
        "impersonation/revoke/",
        views_impersonation.impersonation_revoke,
        name="impersonation_revoke",
    ),
    # rbac-allow: assist-dock-impersonation-start-super-only-consume-approved-grant
    path(
        "impersonation/start/",
        views_impersonation.impersonation_start,
        name="impersonation_start",
    ),
    # rbac-allow: assist-dock-impersonation-stop-authenticated-self-session-only
    path(
        "impersonation/stop/",
        views_impersonation.impersonation_stop,
        name="impersonation_stop",
    ),
    # rbac-allow: assist-dock-impersonation-stop-redirect-authenticated-self-session-only
    path(
        "impersonation/stop-redirect/",
        views_impersonation.impersonation_stop_and_redirect,
        name="impersonation_stop_redirect",
    ),
    # rbac-allow: assist-dock-impersonation-banner-state-authenticated-self-session-poll
    path(
        "impersonation/banner-state.json",
        views_impersonation.impersonation_banner_state,
        name="impersonation_banner_state",
    ),
]
