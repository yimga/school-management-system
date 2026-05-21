"""Cockpit front-office 200x defaults — v3.57.0 (2026-05-21).

Default payloads for the 10 luxury "200x" elements layered platform-wide
over `/super/**` pages (Agent A1 of the v3.57.0 front-office sweep).

These extend the 10 manager-cockpit elements shipped in v3.55.0+ /
v3.56.0 (`cockpit_manager_200x.py`). Where the v3.56 set targets the
manager dashboard's universal chrome (AI Copilot rail, world map,
forecast lane, etc.), this v3.57 set delivers 10 NEW elements that
purpose-match common `/super/**` page archetypes:

  1. Revenue cohort retention chart            (cohort × month heatmap)
  2. NPS sentiment ticker                      (rolling 30-day)
  3. Support-queue burndown                    (sparkline + counts)
  4. Deploy pipeline status                    (last 5 deploys)
  5. Tenant churn-risk scorecard               (top 10 tenants at risk)
  6. AI-suggested fixes feed                   (a8-wire-pending stub)
  7. Automated capacity-planning chart         (utilization vs ceiling)
  8. Regional time-zone clocks                 (4 zones)
  9. Tenant-onboarding pipeline                (kanban lanes)
 10. Audit-event word-cloud                    (top tokens 7d)

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
- The orchestrator at `cockpit_context.py` (NOT this module) is
  responsible for never returning these keys on non-manager hosts.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _


# ============================================================
# Element 1 — Revenue cohort retention chart
# ============================================================

def _front_office_revenue_cohort_defaults() -> dict[str, Any]:
    """Revenue cohort retention chart (cohort × month heatmap).

    Shape:
        enabled        bool
        eyebrow        str        — "Revenue retention by cohort"
        title          str        — "Stickiness"
        title_em       str        — italic "by signup cohort"
        meta_text      str        — right-aligned meta caption
        month_labels   list[str]  — column headers (e.g. ["M0","M1",…,"M11"])
        cohorts        list[dict] — one row per cohort (most recent last)
            [{
                label:  str        — "2025-Q3", "Aug 2025", etc.
                count:  str        — initial cohort size (e.g. "42")
                cells:  list[dict] — exactly len(month_labels) cells
                    [{retention: str (e.g. "94"), heat: "0"-"9"|"x" }]
                      heat "x" = empty/not-yet-collected
            }]
        legend         list[dict] — bottom legend rows
            [{label: str, swatch: "0"-"9"}]
    """
    return {
        "enabled": False,
        "eyebrow": _("Revenue retention · by cohort"),
        "title": _("Stickiness"),
        "title_em": _("by signup cohort"),
        "meta_text": "",
        "month_labels": [],
        "cohorts": [],
        "legend": [],
    }


# ============================================================
# Element 2 — NPS sentiment ticker
# ============================================================

def _front_office_nps_ticker_defaults() -> dict[str, Any]:
    """NPS sentiment ticker (rolling 30-day).

    Shape:
        enabled       bool
        eyebrow       str       — "Net promoter · rolling 30d"
        score         str       — big number ("62" / "—")
        score_status  str       — "promoter" | "passive" | "detractor"
        delta_text    str       — "+4 vs prior 30d"
        delta_tone    str       — "up" | "down" | "flat"
        breakdown     list[dict] — 3 rows
            [{label, count: str, pct: str, kind: "promoters"|"passives"|"detractors"}]
        verbatim      list[dict] — quote ticker rows (no PII; redacted upstream)
            [{quote, score_tag: str (e.g. "9 · promoter")}]
        caption       str       — italic serif footer caption
    """
    return {
        "enabled": False,
        "eyebrow": _("Net promoter · rolling 30d"),
        "score": "—",
        "score_status": "passive",
        "delta_text": "",
        "delta_tone": "flat",
        "breakdown": [],
        "verbatim": [],
        "caption": "",
    }


# ============================================================
# Element 3 — Support-queue burndown
# ============================================================

def _front_office_support_burndown_defaults() -> dict[str, Any]:
    """Support-queue burndown (sparkline + counts).

    Shape:
        enabled         bool
        eyebrow         str
        title           str
        title_em        str
        counts          list[dict] — left pills: [{label, value: str, tone}]
        sparkline       dict — single-line burndown
            {
                points:        list[[x,y]]   — polyline (recent N days)
                stroke_color:  str
                fill_color:    str
                target_y:      int|None      — SLA ceiling line (optional)
                width:         int           — viewBox width
                height:        int           — viewBox height
            }
        sla_caption     str  — right-aligned italic caption
        legend_rows     list[dict] — [{label, value, tone}]
    """
    return {
        "enabled": False,
        "eyebrow": _("Support queue · burndown"),
        "title": _("Open tickets"),
        "title_em": _("trending down"),
        "counts": [],
        "sparkline": {},
        "sla_caption": "",
        "legend_rows": [],
    }


# ============================================================
# Element 4 — Deploy pipeline status (last 5)
# ============================================================

def _front_office_deploy_pipeline_defaults() -> dict[str, Any]:
    """Deploy pipeline status — last 5 deploys.

    Shape:
        enabled    bool
        eyebrow    str
        title      str
        title_em   str
        deploys    list[dict] — exactly 5 entries (most recent first)
            [{
                sha_short:   str    — "a4f1c2"
                version:     str    — "v3.39.0"
                slug:        str    — release slug
                actor:       str    — already PII-redacted upstream
                started:     str    — "2026-05-19 14:38 UTC"
                duration:    str    — "4m 22s"
                status:      str    — "success"|"failed"|"in_progress"|"canceled"
                stage:       str    — current stage label (e.g. "smoke")
            }]
        meta_text  str
    """
    return {
        "enabled": False,
        "eyebrow": _("Deploy pipeline · last 5"),
        "title": _("Releases"),
        "title_em": _("shipped"),
        "deploys": [],
        "meta_text": "",
    }


# ============================================================
# Element 5 — Tenant churn-risk scorecard
# ============================================================

def _front_office_churn_scorecard_defaults() -> dict[str, Any]:
    """Tenant churn-risk scorecard (top 10).

    Shape:
        enabled    bool
        eyebrow    str
        title      str
        title_em   str
        meta_text  str
        rows       list[dict] — exactly 10 entries (highest risk first)
            [{
                rank:        int
                tenant_hash: str    — 12-hex sha256 prefix (never raw slug)
                tenant_alias: str   — operator-chosen short alias (no PII)
                score:       str    — "0.94"
                tier:        str    — "critical"|"high"|"medium"|"low"
                signals:     list[str] — short signal labels (3 max)
                last_activity: str  — relative ("3d ago" / "—")
            }]
        legend_text str
    """
    return {
        "enabled": False,
        "eyebrow": _("Churn risk · top 10"),
        "title": _("At-risk tenants"),
        "title_em": _("retention call list"),
        "meta_text": "",
        "rows": [],
        "legend_text": "",
    }


# ============================================================
# Element 6 — AI-suggested fixes feed (a8-wire-pending)
# ============================================================

def _front_office_ai_fixes_feed_defaults() -> dict[str, Any]:
    """AI-suggested fixes feed (consumes A8 stub for v3.57; real wiring in A8).

    Shape:
        enabled         bool
        eyebrow         str
        title           str
        title_em        str
        meta_text       str
        suggestions     list[dict]
            [{
                slug:        str
                summary:     str    — one-sentence headline
                rationale:   str    — italic serif rationale
                confidence:  str    — "0.91"
                impact:      str    — "high"|"medium"|"low"
                apply_url:   str    — operator-action link (CSRF protected on POST)
                dismiss_url: str    — operator-dismiss link
                created:     str    — relative timestamp
            }]
        empty_state_text str
    """
    return {
        "enabled": False,
        "eyebrow": _("AI · suggested fixes"),
        "title": _("Copilot suggestions"),
        "title_em": _("waiting for review"),
        "meta_text": "",
        "suggestions": [],
        "empty_state_text": _("No suggestions right now — Copilot will surface ideas as signals appear."),
    }


# ============================================================
# Element 7 — Automated capacity-planning chart
# ============================================================

def _front_office_capacity_planning_defaults() -> dict[str, Any]:
    """Automated capacity-planning chart (utilization vs ceiling).

    Shape:
        enabled        bool
        eyebrow        str
        title          str
        title_em       str
        meta_text      str
        resources      list[dict] — one stacked-bar per resource
            [{
                slug:           str
                label:          str        — "Postgres connections"
                current:        str        — "182 / 400"
                pct:            int        — 0..100  (used %)
                ceiling_pct:    int        — soft-cap %  (e.g. 75)
                tone:           str        — "ok"|"warn"|"danger"
                forecast:       str        — italic forecast caption
            }]
        legend_text    str
    """
    return {
        "enabled": False,
        "eyebrow": _("Capacity · forecast"),
        "title": _("Headroom"),
        "title_em": _("vs ceilings"),
        "meta_text": "",
        "resources": [],
        "legend_text": "",
    }


# ============================================================
# Element 8 — Regional time-zone clocks (4 zones)
# ============================================================

def _front_office_regional_clocks_defaults() -> dict[str, Any]:
    """Regional time-zone clocks (4 zones).

    Shape:
        enabled  bool
        clocks   list[dict] — exactly 4 clocks (or fewer; partial honored)
            [{
                label:        str    — "NYC", "LON", "SGP", "SYD"
                tz_name:      str    — IANA tz ("America/New_York")
                time_text:    str    — operator-supplied "14:38" (or computed upstream)
                day_label:    str    — "Tue" / "Wed"
                business_hours: bool — True when 09:00≤local<18:00
                business_status_label: str — "Office hours" / "After hours"
            }]
        caption  str  — italic serif footer caption
    """
    return {
        "enabled": False,
        "clocks": [],
        "caption": "",
    }


# ============================================================
# Element 9 — Tenant-onboarding pipeline (kanban)
# ============================================================

def _front_office_onboarding_pipeline_defaults() -> dict[str, Any]:
    """Tenant-onboarding pipeline (kanban lanes).

    Shape:
        enabled    bool
        eyebrow    str
        title      str
        title_em   str
        meta_text  str
        lanes      list[dict] — typically 4-6 lanes (Lead → Trial → Migrate → Live)
            [{
                slug:    str
                label:   str
                count:   int
                tone:    str          — "neutral"|"emerald"|"amber"|"indigo"|"rose"
                cards:   list[dict]
                    [{tenant_alias: str, age_text: str, owner_initials: str (max 3 chars)}]
            }]
    """
    return {
        "enabled": False,
        "eyebrow": _("Onboarding · pipeline"),
        "title": _("Tenant journey"),
        "title_em": _("lead to live"),
        "meta_text": "",
        "lanes": [],
    }


# ============================================================
# Element 10 — Audit-event word-cloud
# ============================================================

def _front_office_audit_wordcloud_defaults() -> dict[str, Any]:
    """Audit-event word-cloud (top tokens, last 7 days).

    Shape:
        enabled     bool
        eyebrow     str
        title       str
        title_em    str
        meta_text   str
        tokens      list[dict] — ordered (largest weight first)
            [{
                text:    str        — already-redacted token (event types,
                                       scopes, etc. — NEVER raw PII)
                weight:  int        — 1..5 (drives type-size class)
                tone:    str        — "neutral"|"info"|"warn"|"danger"
            }]
        footer_em   str             — italic caption
    """
    return {
        "enabled": False,
        "eyebrow": _("Audit signals · 7d word-cloud"),
        "title": _("Loudest events"),
        "title_em": _("by frequency"),
        "meta_text": "",
        "tokens": [],
        "footer_em": "",
    }


# ============================================================
# Aggregator
# ============================================================

def front_office_200x_defaults() -> dict[str, Any]:
    """Aggregate all 10 front-office sections into a single nested dict.

    The orchestrator in `cockpit_context.py` merges these into the
    `cockpit` mapping it returns for manager hosts. Each top-level key
    is named to match the partial filename (drop the leading underscore
    and `.html`). E.g. `revenue_cohort` ↔ `_revenue_cohort.html`.
    """
    return {
        "revenue_cohort": _front_office_revenue_cohort_defaults(),
        "nps_ticker": _front_office_nps_ticker_defaults(),
        "support_burndown": _front_office_support_burndown_defaults(),
        "deploy_pipeline": _front_office_deploy_pipeline_defaults(),
        "churn_scorecard": _front_office_churn_scorecard_defaults(),
        "ai_fixes_feed": _front_office_ai_fixes_feed_defaults(),
        "capacity_planning": _front_office_capacity_planning_defaults(),
        "regional_clocks": _front_office_regional_clocks_defaults(),
        "onboarding_pipeline": _front_office_onboarding_pipeline_defaults(),
        "audit_wordcloud": _front_office_audit_wordcloud_defaults(),
    }
