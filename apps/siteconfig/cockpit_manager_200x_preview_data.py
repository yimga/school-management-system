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
    return {
        "enabled": True,
        "eyebrow": _("Global footprint"),
        "schools_live": "127",
        "schools_live_label": _("schools live"),
        "subline": _("Across 14 districts · 9 countries · 3 time zones live"),
        "regional_breakdown": [
            {"label": _("North America"), "count": "62", "dot_color_token": "var(--success, #22c55e)"},
            {"label": _("West Africa"), "count": "31", "dot_color_token": "var(--info, #60a5fa)"},
            {"label": _("Europe"), "count": "22", "dot_color_token": "var(--warning, #f59e0b)"},
            {"label": _("Asia · Oceania"), "count": "12", "dot_color_token": "var(--text-secondary, #64748b)"},
        ],
        "tenant_dots": [
            {"cx": 180, "cy": 110, "color_token": "var(--success, #22c55e)", "ring_color": "rgba(34,197,94,0.32)", "delay_s": 0.0},
            {"cx": 280, "cy": 180, "color_token": "var(--success, #22c55e)", "ring_color": "rgba(34,197,94,0.32)", "delay_s": 0.4},
            {"cx": 350, "cy": 220, "color_token": "var(--info, #60a5fa)", "ring_color": "rgba(96,165,250,0.32)", "delay_s": 0.8},
            {"cx": 470, "cy": 160, "color_token": "var(--warning, #f59e0b)", "ring_color": "rgba(245,158,11,0.32)", "delay_s": 1.2},
            {"cx": 560, "cy": 240, "color_token": "var(--info, #60a5fa)", "ring_color": "rgba(96,165,250,0.32)", "delay_s": 1.6},
        ],
    }


# ============================================================
# Element 3 — Forecast lane
# ============================================================

def _forecast_demo() -> dict[str, Any]:
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
                "past_points": [[10, 90], [40, 82], [70, 88], [100, 76], [130, 70]],
                "future_points": [[130, 70], [160, 65], [190, 60], [220, 58], [250, 56]],
                "band_path": "M130,70 C160,55 190,50 220,48 L250,46 L250,68 L220,68 C190,68 160,68 130,68 Z",
                "today_x": 130,
                "caption_left": _("today"),
                "caption_right": _("+7 days"),
            },
            {
                "slug": "new_schools",
                "label": _("New schools · 7-day forecast"),
                "value": "4–6",
                "prediction": _("expected · 88% confidence"),
                "stroke_color": "#60a5fa",
                "fill_color": "rgba(96,165,250,0.10)",
                "past_points": [[10, 88], [40, 80], [70, 84], [100, 72], [130, 68]],
                "future_points": [[130, 68], [160, 62], [190, 58], [220, 54], [250, 50]],
                "band_path": "M130,68 C160,52 190,46 220,44 L250,40 L250,64 L220,64 C190,64 160,64 130,64 Z",
                "today_x": 130,
                "caption_left": _("today"),
                "caption_right": _("+7 days"),
            },
            {
                "slug": "incidents",
                "label": _("Incidents · 7-day forecast"),
                "value": "3",
                "prediction": _("low · 95% confidence"),
                "stroke_color": "#f59e0b",
                "fill_color": "rgba(245,158,11,0.10)",
                "past_points": [[10, 84], [40, 90], [70, 86], [100, 88], [130, 84]],
                "future_points": [[130, 84], [160, 86], [190, 82], [220, 80], [250, 78]],
                "band_path": "M130,84 C160,76 190,72 220,70 L250,68 L250,90 L220,90 C190,90 160,90 130,90 Z",
                "today_x": 130,
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
    status_pattern = (
        ["healthy"] * 38
        + ["okay"] * 12
        + ["warn"] * 5
        + ["danger"] * 2
        + ["idle"] * 3
    )
    tiles = [
        {"label": f"Tenant {i + 1:02d}", "status": status_pattern[i]}
        for i in range(60)
    ]
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
        "scroll_seconds": 60,
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
    }


__all__ = ["manager_200x_demo_payload"]
