"""Cockpit manager 200x preview data — v3.57.3 (2026-05-21).

Pre-populated sample payload that mirrors the v8 200x design preview at
``docs/generated/preview_app_shell_manager_v8_200x.html``. When the
``COCKPIT_200X_RENDER_PREVIEW_DEMO`` setting is True (default: True so the
shell renders the v8 200x experience out of the box), this payload is
overlaid on top of ``manager_200x_defaults()`` so every section's
``enabled`` flag becomes True AND every list is populated with the
preview's sample content.

PII / TENANT-BLEED SAFETY
-------------------------
Every string in this module is generic platform copy from the design
preview — no real tenant slugs, operator emails, or student data. The
"Saint Sebastien Academy" / "Brookline Prep" labels are illustrative
names borrowed verbatim from the preview HTML.

OVERRIDABILITY
--------------
Operators can override individual sections via SiteSettings.cockpit_payload —
``_deep_merge`` in ``cockpit_context.py`` recursively overlays operator
values on top of this demo payload. To turn off a section, the operator
flips its enable toggle on the cockpit configuration page (v3.57.1 admin
UI). To turn off the WHOLE demo, set
``COCKPIT_200X_RENDER_PREVIEW_DEMO=False`` in settings.

The demo payload is byte-stable: with the same source preview, this
module returns the same dict every call (no random ids, no datetime
stamps).
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _


# ============================================================
# Element 1 — AI Copilot persistent rail
# ============================================================

def _ai_copilot_demo() -> dict[str, Any]:
    return {
        "enabled": True,
        "default_state": "collapsed",
        "title": _("Copilot"),
        "title_em": _("always listening"),
        "insight_text": _("Tenants at risk this week: 3"),
        "insight_em": _("two churn signals, one billing escalation"),
        "messages": [
            {
                "role": "ai",
                "text": _("Want to triage the 3 risk tenants by likely churn driver?"),
                "em_text": _("(I can group them by signal)"),
            },
            {
                "role": "user",
                "text": _("yes, group them by signal."),
                "em_text": "",
            },
            {
                "role": "ai",
                "text": _("Done — 1 billing overdue, 1 low logins, 1 NPS slip. Open as a triage board?"),
                "em_text": "",
            },
        ],
        "suggested_actions": [
            _("Open triage board"),
            _("Email tenant success"),
            _("Schedule check-in"),
        ],
        "input_placeholder": _("Ask anything about your platform…"),
        "cmdk_hint": _("⌘ K · command palette"),
        "send_label": _("Send →"),
    }


# ============================================================
# Element 2 — Live world map
# ============================================================

def _world_map_demo() -> dict[str, Any]:
    import json

    from apps.siteconfig.cockpit_panels_realdata_service import _world_map_tenant_dots
    from apps.siteconfig.world_map_geo import build_globe_markers, build_globe_payload, enrich_regional_breakdown

    demo_rows = [
        {"country_code": "US", "is_frozen": False, "name": "Brookline Prep", "settings": {"location": {"city": "New York"}}},
        {"country_code": "US", "is_frozen": False, "name": "Pacific Academy", "settings": {"location": {"city": "Los Angeles"}}},
        {"country_code": "NG", "is_frozen": False, "name": "Saint Sebastien Academy", "settings": {"location": {"city": "Lagos"}}},
        {"country_code": "GB", "is_active": False, "name": "Thames College", "settings": {"location": {"city": "London"}}},
        {"country_code": "IN", "is_frozen": True, "name": "Delhi Tech High", "settings": {"location": {"city": "New Delhi"}}},
    ]
    markers = build_globe_markers(demo_rows)
    globe_payload = build_globe_payload(markers, layout="hero", tour_enabled=True)
    return {
        "enabled": True,
        "eyebrow": _("Global footprint"),
        "schools_live": "127",
        "schools_live_label": _("schools live"),
        "subline": _("Across 14 districts · 9 countries · 3 time zones live"),
        "layout": "hero",
        "tour_enabled": True,
        "regional_breakdown": enrich_regional_breakdown([
            {"label": _("North America"), "count": "62", "dot_color_token": "emerald"},
            {"label": _("West Africa"), "count": "31", "dot_color_token": "indigo"},
            {"label": _("Europe"), "count": "22", "dot_color_token": "amber"},
            {"label": _("Asia · Oceania"), "count": "12", "dot_color_token": "rose"},
        ]),
        "tenant_dots": _world_map_tenant_dots(demo_rows),
        "globe_payload": globe_payload,
        "globe_payload_json": json.dumps(globe_payload),
        "svg_country_labels": globe_payload.get("country_labels") or [],
    }


# ============================================================
# Element 3 — Forecast lane
# ============================================================

def _forecast_demo() -> dict[str, Any]:
    # Wave B (2026-05-22): band_path values upgraded to Quadratic Bezier
    # ("M..Q..Q..Q.. L..Q..Q..Q.. Z") matching the v8 200x preview HTML's
    # confidence-band curvature. Quadratic Bezier (one control point per
    # segment) gives a tighter, more honest-looking confidence envelope
    # than the previous Cubic Bezier paths. All numeric values fit the
    # production partial's viewBox="0 0 240 56" with today_x=120.
    #
    # Path-builder pattern (server-emitted, trusted — no user input):
    #   M  <fx>,<top>            move to start of upper-band edge (today)
    #   Q  <cx>,<cy> <x>,<y>     quad-bezier segment (one control point)
    #   …  repeat 3x to +7d horizon
    #   L  <240>,<bottom>        line down to bottom-right corner
    #   Q  <cx>,<cy> <x>,<y>     quad-bezier back along lower-band edge
    #   …  repeat 3x back to today
    #   Z                        close polygon
    #
    # When a real forecast resolver lands (see apps/observability/), it
    # SHOULD emit paths in this same shape; the partial passes the string
    # through |default and renders it verbatim as the SVG `d` attribute.
    return {
        "enabled": True,
        "label": _("Forecast · next 7 days"),
        "cards": [
            {
                "slug": "mrr",
                "label": _("MRR · 7-day forecast"),
                "value": "$45.8k",
                "prediction": _("steady · 92% confidence"),
                "stroke_color": "#22c55e",
                "fill_color": "rgba(34,197,94,0.10)",
                "past_points": [[0, 42], [20, 40], [40, 38], [60, 34], [80, 32], [100, 28], [120, 26]],
                "future_points": [[120, 26], [140, 22], [160, 20], [180, 18], [200, 16], [220, 14], [240, 12]],
                "band_path": "M120,28 Q150,18 180,16 Q210,14 240,12 L240,32 Q210,30 180,28 Q150,26 120,28 Z",
                "today_x": 120,
                "caption_left": _("today"),
                "caption_right": _("+7 days"),
            },
            {
                "slug": "new_schools",
                "label": _("New schools · 7-day forecast"),
                "value": "4–6",
                "prediction": _("expected · 88% confidence"),
                "stroke_color": "#6366f1",
                "fill_color": "rgba(99,102,241,0.12)",
                "past_points": [[0, 44], [20, 42], [40, 40], [60, 38], [80, 36], [100, 34], [120, 32]],
                "future_points": [[120, 32], [140, 30], [160, 26], [180, 22], [200, 20], [220, 18], [240, 16]],
                "band_path": "M120,32 Q150,26 180,22 Q210,18 240,16 L240,38 Q210,38 180,36 Q150,34 120,32 Z",
                "today_x": 120,
                "caption_left": _("today"),
                "caption_right": _("+7 days"),
            },
            {
                "slug": "incidents",
                "label": _("Incidents · 7-day forecast"),
                "value": "3",
                "prediction": _("low · 95% confidence"),
                "stroke_color": "#f59e0b",
                "fill_color": "rgba(245,158,11,0.12)",
                "past_points": [[0, 30], [20, 32], [40, 26], [60, 28], [80, 24], [100, 30], [120, 28]],
                "future_points": [[120, 28], [140, 28], [160, 26], [180, 28], [200, 30], [220, 28], [240, 26]],
                "band_path": "M120,28 Q150,24 180,28 Q210,30 240,26 L240,46 Q210,44 180,46 Q150,46 120,42 Z",
                "today_x": 120,
                "caption_left": _("today"),
                "caption_right": _("+7 days"),
            },
        ],
    }


# ============================================================
# Element 4 — Operator notebook
# ============================================================

def _notebook_demo() -> dict[str, Any]:
    return {
        "enabled": True,
        "title": _("Add to notebook"),
        "placeholder": _("Capture a thought, decision, or question…"),
        "mic_enabled": True,
        "save_url": "",  # operator wires their own POST endpoint
        "save_label": _("Save →"),
        "hint_text": _("Private to you · searchable later"),
        "hint_em": _("synced to your operator profile"),
    }


# ============================================================
# Element 5 — Tenant heatmap
# ============================================================

def _heatmap_demo() -> dict[str, Any]:
    # 60 tiles in deterministic status pattern (mostly healthy, sprinkled).
    # Wave B (2026-05-22): tiles now emit `cell_value` (primary stat) and
    # `cell_secondary` (delta) so the JS-driven tooltip in rmc-data-viz.js
    # renders the rich preview shape ("Saint Sebastien · 1,242 active ·
    # +3.1% WoW"). Values are illustrative and byte-stable.
    status_pattern = (
        ["healthy"] * 38
        + ["okay"] * 12
        + ["warn"] * 5
        + ["danger"] * 2
        + ["idle"] * 3
    )
    # Deterministic synthetic active-user count per status tier, used only
    # for demo overlay (operator-real-data wiring deferred to forecast_service
    # / heatmap_service helpers in a future wave). No real tenant slugs.
    base_actives = {"healthy": 1180, "okay": 540, "warn": 240, "danger": 90, "idle": 0}
    delta_by_status = {
        "healthy": "+3.1% WoW",
        "okay": "+0.4% WoW",
        "warn": "-1.8% WoW",
        "danger": "-6.2% WoW",
        "idle": "no traffic",
    }
    tiles = []
    for i in range(60):
        status = status_pattern[i]
        # Deterministic per-tile offset so tiles aren't identical.
        offset = (i * 37) % 211
        active = base_actives[status] + offset if status != "idle" else 0
        active_label = f"{active:,} active" if active else "pilot · 0 active"
        tiles.append({
            "label": f"Tenant {i + 1:02d}",
            "status": status,
            "cell_value": active_label,
            "cell_secondary": delta_by_status[status],
            "tenant_slug": f"tenant-{i + 1:02d}",
        })
    return {
        "enabled": True,
        "eyebrow": _("Tenants · health grid"),
        "title": _("Every school,"),
        "title_em": _("one tile each"),
        "meta_text": _("60 of 127 · refreshed 12s ago"),
        "tiles": tiles,
        "legend_hint": _("hover any tile for tenant name"),
    }


# ============================================================
# Element 6 — Revenue waterfall
# ============================================================

def _waterfall_demo() -> dict[str, Any]:
    return {
        "enabled": True,
        "eyebrow": _("MRR waterfall · this month"),
        "title": "$39.2k",
        "title_em": _("to a closing"),
        "title_end": "$42.1k",
        "meta_text": _("closing day 18 of 31 · pacing +7.4%"),
        "bars": [
            {"slug": "start", "label": _("Starting MRR"), "value": "$39.2k", "x": 40, "y": 80, "width": 100, "height": 140, "gradient_id": "lx-wf-anchor", "value_color": "var(--text-primary)"},
            {"slug": "new", "label": _("New business"), "value": "+$3.8k", "x": 200, "y": 60, "width": 100, "height": 30, "gradient_id": "lx-wf-up", "value_color": "var(--success, #22c55e)"},
            {"slug": "expansion", "label": _("Expansion"), "value": "+$1.6k", "x": 360, "y": 48, "width": 100, "height": 18, "gradient_id": "lx-wf-up", "value_color": "var(--success, #22c55e)"},
            {"slug": "churn", "label": _("Churn"), "value": "-$2.5k", "x": 520, "y": 66, "width": 100, "height": 32, "gradient_id": "lx-wf-down", "value_color": "var(--danger, #ef4444)"},
            {"slug": "end", "label": _("Ending MRR"), "value": "$42.1k", "x": 680, "y": 70, "width": 100, "height": 150, "gradient_id": "lx-wf-anchor", "value_color": "var(--text-primary)"},
        ],
        "connector_dashes": [
            {"x1": 140, "y1": 80, "x2": 200, "y2": 60},
            {"x1": 300, "y1": 60, "x2": 360, "y2": 48},
            {"x1": 460, "y1": 48, "x2": 520, "y2": 66},
            {"x1": 620, "y1": 66, "x2": 680, "y2": 70},
        ],
        "legend_rows": [
            {"label": _("Starting"), "value": "$39.2k", "value_color": "var(--text-primary)"},
            {"label": _("Net new"), "value": "+$5.4k", "value_color": "var(--success, #22c55e)"},
            {"label": _("Churn"), "value": "-$2.5k", "value_color": "var(--danger, #ef4444)"},
            {"label": _("Closing"), "value": "$42.1k", "value_color": "var(--text-primary)"},
        ],
    }


# ============================================================
# Element 7 — Structured audit feed
# ============================================================

def _audit_feed_demo() -> dict[str, Any]:
    return {
        "enabled": True,
        "title": _("Audit feed"),
        "title_em": _("every consequential write"),
        "filter_text": _("scope: super-admin · last 24h"),
        "events": [
            {"time": "14:38:02", "actor": "ops-admin-7a", "event": "key.rotate", "scope": "ten-9f2a · v3", "severity": "ok", "severity_label": "OK"},
            {"time": "14:21:55", "actor": "ops-admin-2c", "event": "maa.sign", "scope": "ten-b41e · v1.0", "severity": "info", "severity_label": "INFO"},
            {"time": "13:52:11", "actor": "auto-task", "event": "webhook.delivery.replay", "scope": "ten-3c11 · attempt 2", "severity": "warn", "severity_label": "WATCH"},
            {"time": "13:38:44", "actor": "ops-admin-1d", "event": "token.mint", "scope": "ten-7e08 · scope:bundles", "severity": "ok", "severity_label": "OK"},
            {"time": "12:14:09", "actor": "auto-task", "event": "audit.chain.verify", "scope": "all tenants", "severity": "ok", "severity_label": "OK"},
            {"time": "10:02:18", "actor": "ops-admin-5b", "event": "webhook.subscription.deleted", "scope": "ten-a229 · sub-44", "severity": "danger", "severity_label": "RISK"},
        ],
    }


# ============================================================
# Element 8 — Trust nutrition label
# ============================================================

def _trust_nutrition_demo() -> dict[str, Any]:
    return {
        "enabled": True,
        "title": _("Trust nutrition"),
        "caption": _("per Apple Watch complications"),
        "footer": _("audit-grade · refreshed every 60s"),
        "rows": [
            {"label": _("Uptime · 30d"), "value": "99.987%", "status": "ok"},
            {"label": _("Active incidents"), "value": "0", "status": "ok"},
            {"label": _("Avg p95 latency · api"), "value": "184ms", "status": "ok"},
            {"label": _("Webhook delivery success"), "value": "99.4%", "status": "ok"},
            {"label": _("Audit chain integrity"), "value": "verified", "status": "ok"},
            {"label": _("Key rotation due"), "value": "14d", "status": "warn"},
            {"label": _("DR drill"), "value": "21d", "status": "warn"},
            {"label": _("Pending compliance reviews"), "value": "2", "status": "neutral"},
        ],
    }


# ============================================================
# Element 9 — Live SLO clocks (4 dark cards)
# ============================================================

def _slo_clocks_demo() -> dict[str, Any]:
    return {
        "enabled": True,
        "clocks": [
            {"label": _("P99 latency budget"), "value": "32", "value_suffix": _("m left"), "sublabel": _("api · 28d window"), "dot_status": "ok"},
            {"label": _("Audit chain verify"), "value": "4d", "value_suffix": "6h", "sublabel": _("scheduled Mon · 02:00 UTC"), "dot_status": "info"},
            {"label": _("Next key rotation"), "value": "14d", "value_suffix": "02h", "sublabel": _("MultiFernet · monthly"), "dot_status": "warn"},
            {"label": _("Backup drill"), "value": "21d", "value_suffix": "11h", "sublabel": _("DR cadence · quarterly"), "dot_status": "ok"},
        ],
    }


# ============================================================
# Element 10 — Operator presence indicator (header)
# ============================================================

def _operator_presence_demo() -> dict[str, Any]:
    return {
        "enabled": True,
        "avatars": [
            {"initials": "AB", "gradient_slug": "indigo"},
            {"initials": "CD", "gradient_slug": "emerald"},
            {"initials": "EF", "gradient_slug": "amber"},
        ],
        "operators_online_count": 7,
        "operators_online_label": _("operators online"),
        "status_pill_text": _("All systems handling well"),
        "aria_label": _("Operators online and platform status"),
    }


# ============================================================
# Element 11 — Live activity ticker (landing-page chrome)
# ============================================================

def _activity_ticker_demo() -> dict[str, Any]:
    """6 cards mirroring the LIVE ticker headlines in the v8 200x preview.

    Card text + severity + icon + timestamp byte-mirror the
    ``.cp-activity-event`` spans in the v8 preview's
    ``.cp-activity-ticker__track`` block (Saint Sebastien Academy /
    MRR / webhook drift / support tickets / migration sync / invoice
    due). Operators override individual events via SiteSettings —
    production wave will source from the platform event stream
    (audit log + provisioning + billing).
    """
    return {
        "enabled": True,
        # v3.60.0 (2026-05-22): tuned from 60s → 40s for a snappier feel.
        "scroll_seconds": 40,
        "live_badge_label": _("LIVE"),
        "cards": [
            {
                "icon": "🆕",
                "severity": "success",
                "text": _("New school provisioned — Saint Sebastien Academy"),
                "timestamp": _("12s ago"),
            },
            {
                "icon": "↗",
                "severity": "success",
                "text": _("MRR up $420 this week"),
                "timestamp": _("1m ago"),
            },
            {
                "icon": "🚨",
                "severity": "danger",
                "text": _("Tenant #567 webhook drift detected"),
                "timestamp": _("2m ago"),
            },
            {
                "icon": "🎫",
                "severity": "info",
                "text": _("5 new support tickets"),
                "timestamp": _("4m ago"),
            },
            {
                "icon": "✓",
                "severity": "success",
                "text": _("Migration sync complete for 12 schools"),
                "timestamp": _("6m ago"),
            },
            {
                "icon": "⚠",
                "severity": "warn",
                "text": _("2 schools approaching invoice due date"),
                "timestamp": _("8m ago"),
            },
        ],
    }


# ============================================================
# Aggregator
# ============================================================

def _trust_pillars_alerts_demo() -> dict[str, Any]:
    """v3.58.x Wave 10 Agent S — alerts-feed-style 7-pillar demo payload.

    Closes the v8 200x preview's alerts-feed gap. Renders out of the box so
    operators see the section the moment they land; the real-data resolver's
    `_resolve_trust_pillars_alerts()` overlays live posture on top of this
    via `_deep_merge`.
    """
    return {
        "enabled": True,
        "eyebrow": _("Trust pillars · alerts"),
        "title": _("Platform posture"),
        "title_em": _("seven pillars at a glance"),
        "meta_text": _("audit-grade · refreshed every 60s"),
        "footer_text": _(
            "A buyer can read this card and know within seconds whether to keep talking."
        ),
        "pillars": [
            {
                "slug": "audit_chain",
                "label": _("Audit chain integrity"),
                "value": _("verified"),
                "status": "ok",
                "last_checked": _("Mon · 02:00 UTC"),
            },
            {
                "slug": "maa_signatures",
                "label": _("MAA signatures"),
                "value": _("counsel-blessed v1.0"),
                "status": "ok",
                "last_checked": _("on each sign"),
            },
            {
                "slug": "encryption_at_rest",
                "label": _("Encryption at rest"),
                "value": _("AES-256 · MultiFernet"),
                "status": "ok",
                "last_checked": _("monthly rotation"),
            },
            {
                "slug": "ferpa_retention",
                "label": _("FERPA retention"),
                "value": _("90d floor"),
                "status": "ok",
                "last_checked": _("docs/SECURITY_KEYS.md"),
            },
            {
                "slug": "webhook_signing",
                "label": _("Webhook signing"),
                "value": _("HMAC-SHA256 + canonical JSON"),
                "status": "ok",
                "last_checked": _("per delivery"),
            },
            {
                "slug": "mfa_enforcement",
                "label": _("MFA enforcement"),
                "value": _("operator-required"),
                "status": "ok",
                "last_checked": _("on each sign-in"),
            },
            {
                "slug": "companion_handshake",
                "label": _("Companion handshake"),
                "value": _("X25519 sealed box"),
                "status": "ok",
                "last_checked": _("per upload"),
            },
        ],
    }


def manager_200x_demo_payload() -> dict[str, Any]:
    """Return the full demo payload — all sections enabled + populated.

    Consumed by ``cockpit_context.py`` when ``settings.COCKPIT_200X_RENDER_PREVIEW_DEMO``
    is True (default in dev / preview environments). Operators flip individual
    sections off via the v3.57.1 admin toggles; ``_deep_merge`` overlays their
    cockpit_payload values on top of this payload.

    v3.57.11 (2026-05-22): added ``activity_ticker`` (Element 11) so the
    landing page ticker renders out of the box matching the v8 200x preview
    HTML (6 cards: Saint Sebastien Academy / MRR / webhook drift / support
    tickets / migration sync / invoice due).

    v3.58.x Wave 10 (2026-05-22): added ``trust_pillars_alerts`` (Element 12)
    so the v8 200x preview's alerts-feed gap closes out of the box.
    """
    return {
        "ai_copilot_rail": _ai_copilot_demo(),
        "live_world_map": _world_map_demo(),
        "forecast_lane": _forecast_demo(),
        "operator_notebook": _notebook_demo(),
        "tenant_heatmap": _heatmap_demo(),
        "revenue_waterfall": _waterfall_demo(),
        "audit_feed": _audit_feed_demo(),
        "trust_nutrition": _trust_nutrition_demo(),
        "slo_clocks": _slo_clocks_demo(),
        "operator_presence": _operator_presence_demo(),
        "activity_ticker": _activity_ticker_demo(),
        "trust_pillars_alerts": _trust_pillars_alerts_demo(),
    }


__all__ = ["manager_200x_demo_payload"]
