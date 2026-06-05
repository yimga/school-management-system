"""Cockpit manager 200x defaults — v3.55.0+ (2026-05-21).

Default payloads for the 10 luxury "200x" elements layered over the v7
manager cockpit. Most sections default to `enabled=False`; the AI copilot
rail defaults to `enabled=True` so page-help and the operator rail ship on
manager hosts without demo overlay. Operators may still disable via
SiteSettings.cockpit_payload.

This module is consumed by `apps/siteconfig/cockpit_context.py` (the
orchestrator integrates these into the manager-host branch). Helpers
are kept pure: no Django request access, no DB I/O, no PII.

CONFIGURABILITY CONTRACT
------------------------
Each helper returns the SOT shape that admin UI forms will write into
SiteSettings.cockpit_payload.<section>. The partial that consumes each
section MUST short-circuit when `enabled=False` so unconfigured tenants
render nothing (tenant-bleed defense — operator surfaces never leak to
portal hosts).

PII / TENANT-BLEED SAFETY
-------------------------
- No raw operator emails, usernames, or tenant slugs in defaults.
- All user-facing strings wrapped in gettext_lazy for i18n.
- Numeric/financial placeholders use "—" so honest "no data" beats
  fabricated counts.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _


# ============================================================
# Element 1 — AI Copilot persistent rail
# ============================================================

def _manager_ai_copilot_defaults() -> dict[str, Any]:
    """AI Copilot rail (44px collapsed / 360px expanded).

    Shape:
        enabled            bool       — master switch
        default_state      str        — "collapsed" | "expanded"
        title              str        — header title
        title_em           str        — italic serif tail (e.g. "always listening")
        insight_text       str        — top insight pill (lead sentence)
        insight_em         str        — italic serif fragment inside insight
        messages           list       — thread messages
            [{role: "ai"|"user", text: str, em_text: str (optional)}]
        suggested_actions  list[str]  — suggestion pill labels
        input_placeholder  str        — textarea placeholder
        cmdk_hint          str        — bottom-left ⌘K label
        send_label         str        — send button label
    """
    return {
        "enabled": True,
        "default_state": "collapsed",
        "title": _("Copilot"),
        "title_em": _("always listening"),
        "insight_text": "",
        "insight_em": "",
        "messages": [],
        "suggested_actions": [],
        "input_placeholder": _("Ask anything about your platform…"),
        "cmdk_hint": _("⌘ K · command palette"),
        "send_label": _("Send →"),
    }


# ============================================================
# Element 2 — Live world map card
# ============================================================

def _manager_world_map_defaults() -> dict[str, Any]:
    """Live world map (stylized continents + tenant dots + heatmap halos).

    Shape:
        enabled              bool
        eyebrow              str    — small eyebrow above the count
        schools_live         str    — big "127" mega-number (string for "—" honesty)
        schools_live_label   str    — "schools live" suffix
        subline              str    — italic line below ("Across X districts · Y countries")
        regional_breakdown   list   — legend rows
            [{label: str, count: str, dot_color_token: str}]
        tenant_dots          list   — pulse dots on the map (visual only)
            [{cx: int, cy: int, color_token: str, ring_color: str, delay_s: float}]
    """
    return {
        "enabled": True,  # v3.58.10: surface live world map on landing by default
        "eyebrow": _("Global footprint"),
        "schools_live": "—",
        "schools_live_label": _("schools live"),
        "subline": "",
        "regional_breakdown": [],
        "tenant_dots": [],
    }


# ============================================================
# Element 3 — Forecast lane (3-card triptych)
# ============================================================

def _manager_forecast_defaults() -> dict[str, Any]:
    """Forecast lane — MRR / new schools / incidents 7-day forecasts.

    Shape:
        enabled    bool
        label      str           — section label
        cards      list[dict]    — exactly 3 cards (MRR / new schools / incidents)
            [{
                slug:        str   — "mrr" | "new_schools" | "incidents"
                label:       str   — uppercase title
                value:       str   — big value (e.g. "$45.8k" / "4–6" / "3")
                prediction:  str   — italic prediction line
                stroke_color: str  — line color token (e.g. "#22c55e")
                fill_color:   str  — confidence band fill (rgba)
                past_points:  list[[x:int, y:int]]  — past polyline
                future_points: list[[x:int, y:int]] — future polyline (dashed)
                band_path:   str   — confidence band SVG path "d" attr
                today_x:     int   — vertical "today" tick x coord
                caption_left:  str
                caption_right: str
            }]
    """
    return {
        "enabled": True,  # v3.58.10: forecast lane live on landing by default
        "label": _("Forecast · next 7 days"),
        "cards": [],
    }


# ============================================================
# Element 4 — Operator notebook quick-capture (floating)
# ============================================================

def _manager_notebook_defaults() -> dict[str, Any]:
    """Bottom-right floating frosted-dark quick-capture widget.

    Shape:
        enabled       bool
        title         str   — uppercase tiny title ("Add to notebook")
        placeholder   str   — serif-italic textarea placeholder
        mic_enabled   bool  — show dictation mic button
        save_url      str   — POST endpoint for saving entries (CSRF protected)
        save_label    str   — save button label
        hint_text     str   — bottom hint text
        hint_em       str   — italicized fragment of the hint (e.g. "operator/em · private")
    """
    return {
        # v3.58 (2026-05-22): default ON. Per operator feedback the notebook
        # is more useful displayed-by-default-minimizable than hidden-by-default.
        # Operators can still flip it off via the admin form if they want a
        # clean canvas.
        "enabled": True,
        "title": _("Add to notebook"),
        "placeholder": _("Capture a thought, decision, or question…"),
        "mic_enabled": True,
        "save_url": "",
        "save_label": _("Save →"),
        "hint_text": "",
        "hint_em": "",
        # v3.58 (2026-05-22): recent-notes panel — last N entries shown
        # compact inside the notebook, persisted client-side via localStorage
        # (operator's own browser, never leaves device unless save_url is set).
        "recent_limit": 10,
        "recent_label": _("Recent notes"),
        # v3.58 (2026-05-22): drag handle. The frosted widget is positioned
        # fixed and the operator can drag it to any corner; position persists
        # per-operator via localStorage. Snap-to-corner on release within
        # 80px of any edge.
        "draggable": True,
        # v4.02.0: tray mode disables drag — notebook lives inside Tools panel.
        "tray_mode": True,
    }


# ============================================================
# Element 4a — Nav sidebar rail + resize (v4.02.1)
# ============================================================

def _nav_sidebar_defaults() -> dict[str, Any]:
    """Left nav sidebar icon rail + drag resize contract.

    Shape:
        enabled         bool  — master switch for rail/resize UX
        default_mode    str   — ``normal`` | ``rail``
        default_width   int   — px when expanded (200–420)
        min_width       int
        max_width       int
        rail_width      int   — icon rail width (44)
    """
    return {
        "enabled": True,
        "default_mode": "normal",
        "default_width": 280,
        "min_width": 200,
        "max_width": 420,
        "rail_width": 44,
    }


# ============================================================
# Element 4b — Operator Tools edge-tray (v4.02.0)
# ============================================================

def _operator_tools_defaults() -> dict[str, Any]:
    """Vertical edge tab + horizontal tray consolidating page utilities.

    Shape:
        enabled                 bool  — master switch for edge-tray layout
        layout                  str   — ``edge-tray`` (only supported value)
        tab_label               str   — vertical tab caption
        tray_notebook           bool  — render notebook inside tray panel
        hide_floating_notebook  bool  — suppress fixed-position notebook card
        workflow_header_only    bool  — workflow chip in header, not dock
        back_to_top_corner      str   — ``bottom-left`` | ``bottom-right``
    """
    return {
        "enabled": True,
        "layout": "edge-tray",
        "tab_label": _("Tools"),
        "tray_notebook": True,
        "hide_floating_notebook": True,
        "workflow_header_only": True,
        "back_to_top_corner": "bottom-left",
    }


# ============================================================
# Element 5 — Tenant heatmap (20-col dense grid)
# ============================================================

def _manager_heatmap_defaults() -> dict[str, Any]:
    """Per-tenant 20-col health heatmap.

    Shape:
        enabled       bool
        eyebrow       str    — "Tenants · health grid"
        title         str    — "Every school"
        title_em      str    — italic tail "one tile each"
        meta_text     str    — top-right meta (count + last-refreshed)
        tiles         list   — ordered list of tiles (max ~60 visible)
            [{label: str (data-label hover text), status: str}]
            status ∈ {"healthy", "okay", "warn", "danger", "idle"}
        legend_hint   str    — italic right-floating hint
    """
    return {
        "enabled": True,  # v3.58.10: tenant heatmap live on landing by default
        "eyebrow": _("Tenants · health grid"),
        "title": _("Every school,"),
        "title_em": _("one tile each"),
        "meta_text": "",
        "tiles": [],
        "legend_hint": _("hover any tile for tenant name"),
    }


# ============================================================
# Element 6 — Revenue waterfall card
# ============================================================

def _manager_waterfall_defaults() -> dict[str, Any]:
    """MRR waterfall: Starting / New / Expansion / Churn / Ending.

    Shape:
        enabled    bool
        eyebrow    str        — "MRR waterfall · this month"
        title      str        — "From $39.2k"
        title_em   str        — italic "to a closing"
        title_end  str        — "$42.1k"
        meta_text  str        — "closing day 18 of 31 · pacing +7.4%"
        bars       list[dict] — 5 bars in order
            [{
                slug:    "start" | "new" | "expansion" | "churn" | "end"
                label:   str   — bar caption ("Starting MRR", "New business", …)
                value:   str   — top-text value ("$39.2k" / "+$3.8k" / "-$2.1k")
                x:       int   — left x (px in 760 viewBox)
                y:       int   — top y
                width:   int
                height:  int
                gradient_id: str  — "lx-wf-anchor" | "lx-wf-up" | "lx-wf-down"
                value_color: str  — text fill color (defaults to text-primary)
            }]
        connector_dashes  list — visual connector lines between bars
            [{x1:int, y1:int, x2:int, y2:int}]
        legend_rows       list  — bottom legend
            [{label: str, value: str, value_color: str}]
    """
    return {
        "enabled": True,  # v3.58.10: revenue waterfall live on landing by default
        "eyebrow": _("MRR waterfall · this month"),
        "title": "",
        "title_em": _("to a closing"),
        "title_end": "",
        "meta_text": "",
        "bars": [],
        "connector_dashes": [],
        "legend_rows": [],
    }


# ============================================================
# Element 7 — Structured audit feed
# ============================================================

def _manager_audit_feed_defaults() -> dict[str, Any]:
    """Tabular audit feed with severity stripe + colored pill.

    Shape:
        enabled       bool
        title         str   — "Audit feed"
        title_em      str   — italic tail
        filter_text   str   — scope filter caption ("scope: super-admin · last 24h")
        events        list  — rows
            [{
                time:     str   — "14:38:02"
                actor:    str   — actor display (already PII-redacted upstream)
                event:    str   — event_type human label
                scope:    str   — tenant prefix + key version etc.
                severity: str   — "ok" | "info" | "warn" | "danger"
                severity_label: str  — "OK" | "INFO" | "WATCH" | "RISK"
            }]
    """
    return {
        "enabled": True,  # v3.58.10: audit feed live on landing by default
        "title": _("Audit feed"),
        "title_em": _("every consequential write"),
        "filter_text": "",
        "events": [],
    }


# ============================================================
# Element 8 — Trust nutrition label
# ============================================================

def _manager_trust_nutrition_defaults() -> dict[str, Any]:
    """Nutrition-label trust card (8 inline rows).

    Shape:
        enabled    bool
        title      str        — italic serif title ("Trust nutrition")
        caption    str        — top-right uppercase small
        footer     str        — italic serif footer caption
        rows       list[dict] — exactly 8 rows
            [{
                label:  str   — "Uptime · 30d", etc.
                value:  str   — "99.987%", "0", "—"
                status: str   — "ok" | "warn" | "danger" | "neutral"
            }]
    """
    return {
        "enabled": True,  # v3.58.10: trust nutrition live on landing by default
        "title": _("Trust nutrition"),
        "caption": _("per Apple Watch complications"),
        "footer": "",
        "rows": [],
    }


# ============================================================
# Element 9 — Live SLO clocks (4 dark cards)
# ============================================================

def _manager_slo_clocks_defaults() -> dict[str, Any]:
    """4 dark inset cards with monospace digits + pulse dot.

    Shape:
        enabled    bool
        clocks     list[dict] — exactly 4 clocks
            [{
                label:    str   — "P99 latency budget", "Audit chain verify", …
                value:    str   — big monospace value ("32", "4d", "14d", "21d")
                value_suffix: str  — small inline suffix ("m left", "6h", "02h", "11h")
                sublabel: str   — small line below ("api · 28d window")
                dot_status: str — "ok" | "warn" | "danger" | "info"
            }]
    """
    return {
        "enabled": True,  # v3.58.10: SLO clocks live on landing by default
        "clocks": [],
    }


# ============================================================
# Element 10 — Operator presence indicator (header capsule)
# ============================================================

def _manager_operator_presence_defaults() -> dict[str, Any]:
    """3 overlapping avatar dots + count + status pill.

    Shape:
        enabled                bool
        avatars                list[dict] — overlapping initials chips
            [{initials: str, gradient_slug: str}]
            gradient_slug ∈ {"indigo", "emerald", "amber"} — chooses tinted chip
        operators_online_count int        — used to render "N operators online"
        operators_online_label str        — i18n-ready label ("operators online")
        status_pill_text       str        — "All systems handling well"
        aria_label             str        — overall aria-label for the capsule
    """
    return {
        "enabled": True,  # v3.58.10: operator presence live on landing by default
        "avatars": [],
        "operators_online_count": 0,
        "operators_online_label": _("operators online"),
        "status_pill_text": "",
        "aria_label": _("Operators online and platform status"),
    }


# ============================================================
# Element 12 — Trust pillars alerts (v3.58.x Wave 10 Agent S — v8 200x gap)
# ============================================================

def _trust_pillars_alerts_defaults() -> dict[str, Any]:
    """Alerts-feed-style display of the 7 platform trust pillars.

    Distinct from `trust_nutrition` (nutrition-label card paired with the
    heatmap). This section is the alerts feed visible at the bottom of the
    v8 200x operator landing — one row per pillar with status dot + label +
    value + last-checked timestamp + optional drill-in link.

    PII contract: only the 7 named platform pillars are pre-wired; operator
    overrides via SiteSettings.cockpit_payload can add/rename rows without
    introducing PII (label/value strings are operator-authored copy).

    Shape:
        enabled      bool
        eyebrow      str   — uppercase eyebrow
        title        str   — h3 title
        title_em     str   — italic tail
        meta_text    str   — top-right meta (last-refreshed)
        footer_text  str   — italic serif caption beneath the rows
        pillars      list[dict] — typically 7 rows
            [{
                slug:         str  — stable identifier
                label:        str  — left primary line
                value:        str  — middle status value
                status:       str  — "ok" | "warn" | "danger" | "info" | "neutral"
                last_checked: str  — small right-side timestamp
                detail_url:   str  — optional drill-in link
                detail_label: str  — sr-only label
            }]

    The 7 platform pillars are:
        audit_chain          — Audit chain integrity (verifier beat result)
        maa_signatures       — MAA signatures (campaign progress)
        encryption_at_rest   — Encryption at rest (DJANGO_CRYPTOGRAPHY_KEYS check)
        ferpa_retention      — FERPA retention (90d floor)
        webhook_signing      — Webhook signing (HMAC-SHA256 + canonical JSON)
        mfa_enforcement      — MFA enforcement (operator-required)
        companion_handshake  — Companion handshake (X25519 sealed box)
    """
    return {
        # v3.59.6 Wave C (2026-05-22): flipped to True per v8 200x preview
        # parity — operators expect the 7-pillar trust posture visible by
        # default on landing. Demo overlay + real-data resolver populate the
        # pillars list. Operators can still disable per-tenant via
        # SiteSettings.cockpit_payload.trust_pillars_alerts.enabled=False.
        "enabled": True,
        "eyebrow": _("Trust pillars · alerts"),
        "title": _("Platform posture"),
        "title_em": _("seven pillars at a glance"),
        "meta_text": "",
        "footer_text": "",
        "pillars": [],
    }


# ============================================================
# Element 11 — Live activity ticker (landing-page chrome)
# ============================================================

def _activity_ticker_defaults() -> dict[str, Any]:
    """Bloomberg-style horizontal scrolling LIVE platform activity feed.

    Rendered on the manager landing (schools/super_dashboard.html) just above
    the platform pulse strip — NOT in the universal header (that would push the
    ticker onto every /super/* config page, blurring landing vs configuration
    surfaces). The partial `templates/partials/cockpit/_activity_ticker.html`
    gates on `cockpit.activity_ticker.cards` and short-circuits when empty.

    Shape:
        enabled            bool       — master switch (default: True since v3.59.6)
        scroll_seconds     int        — animation duration (default: 40 since v3.60.0)
        live_badge_label   str        — red pill caption (default: "LIVE")
        cards              list[dict] — ordered events
            [{
                text:      str   — main headline ("MRR up $420 this week")
                timestamp: str   — relative time ("12s ago")
                icon:      str   — single glyph (optional)
                severity:  str   — success | warn | danger | info (drives icon color)
            }]
    """
    return {
        # v3.59.6 Wave C (2026-05-22): flipped to True per v8 200x preview
        # parity — preview shows the LIVE ticker on landing chrome. Partial
        # short-circuits on empty `cards` list so default-on with no data is
        # a no-op. Operators can disable per-tenant via SiteSettings.
        "enabled": True,
        # v3.60.0 (2026-05-22): tuned from 60s → 40s for a snappier feel
        # that still keeps each card legible. 60s read as nearly static; 40s
        # matches the cadence of Bloomberg / financial-terminal tickers.
        # Operators can override per-tenant via SiteSettings.
        "scroll_seconds": 40,
        "live_badge_label": _("LIVE"),
        "cards": [],
    }


# ============================================================
# Aggregator
# ============================================================

def manager_200x_defaults() -> dict[str, Any]:
    """Aggregate all sections into a single nested dict.

    The orchestrator in `cockpit_context.py` merges these into the
    `cockpit` mapping it returns for manager hosts. Each top-level key
    is named to match the partial filename (drop the leading underscore
    and `.html`). E.g. `ai_copilot_rail` ↔ `_ai_copilot_rail.html`.

    v3.57.11 (2026-05-22): added `activity_ticker` (Element 11) so the
    landing page can populate the live event feed via the same
    cockpit_payload override pattern as the other 200x sections.

    v3.58.x Wave 10 (2026-05-22): added `trust_pillars_alerts` (Element 12)
    to close the v8 200x preview's alerts-feed gap. Renders the 7 platform
    trust pillars in an alert-list style distinct from `trust_nutrition`.
    """
    return {
        "ai_copilot_rail": _manager_ai_copilot_defaults(),
        "live_world_map": _manager_world_map_defaults(),
        "forecast_lane": _manager_forecast_defaults(),
        "operator_notebook": _manager_notebook_defaults(),
        "nav_sidebar": _nav_sidebar_defaults(),
        "operator_tools": _operator_tools_defaults(),
        "tenant_heatmap": _manager_heatmap_defaults(),
        "revenue_waterfall": _manager_waterfall_defaults(),
        "audit_feed": _manager_audit_feed_defaults(),
        "trust_nutrition": _manager_trust_nutrition_defaults(),
        "slo_clocks": _manager_slo_clocks_defaults(),
        "operator_presence": _manager_operator_presence_defaults(),
        "activity_ticker": _activity_ticker_defaults(),
        "trust_pillars_alerts": _trust_pillars_alerts_defaults(),
    }
