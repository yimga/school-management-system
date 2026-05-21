"""Cockpit context processor — v3.55.0 (2026-05-21).

Provides safe defaults for the v7 cockpit surfaces (brand tagline,
activity ticker, platform pulse, workspace context, breadcrumb) AND
the v3.55.0 civic 4-tier footer (brand+motto, trust pillars, language
switcher, app badges, social, contacts, stat line, legal links).

CONFIGURABILITY CONTRACT
------------------------
Every value here is intended to flow from `SiteSettings.cockpit_payload`
once the operator admin UI lands. For this initial wave, we return
sensible defaults so the manager dashboard renders correctly the moment
the new partials are wired in. The shape mirrors the SiteSettings
schema scheduled for the v3.56 admin UI wave:

    cockpit:
      brand:
        wordmark         str
        product_pill     str
        tagline          str
      activity_feed:
        enabled          bool
        scroll_seconds   int
        events           list[{icon, severity, text, time_label}]
      pulse_metrics:
        label            str
        show_live_dot    bool
        cards            list[{head, severity, value, label, delta, delta_direction}]
      workspace_context:
        enabled          bool
        show_role        bool
        scope_dropdown   bool
        collapse_toggle  bool
        scope_label      str
      breadcrumb:
        show_root_link   bool
        separator        str
      footer:                                  # v3.55.0
        brand:
          wordmark         str
          motto            str                 # italic Source Serif 4 quote
          founded_year     int | None
          descriptor       str                 # e.g. "Family portal" / "Manager"
        trust_pillars      list[{label, tone}] # tone: secure | cert | neutral
        language:
          label            str
          current_locale   str
          has_switcher     bool
        app_badges         list[{label, glyph, url}]
        social             list[{platform, glyph, url, label}]
        contacts           list[{kind, value, href, glyph}]
        stat_line          str (may contain HTML — passed through |safe)
        legal_links        list[{label, url}]
        copyright_holder   str
        powered_by         {label, url}

PII SAFETY
----------
Operator identity values for the workspace context are NOT returned here.
The partial reads `actor_display.{initials,label,role_label}` from the
existing PII-safe `actor_display` context (rendered by views.py). This
keeps raw emails/usernames out of templates.

Tenant footer contact info (school phone, email, address) IS PII at the
school-entity level (not user-entity level) and is intentionally
returned by this processor when on a tenant host — but ONLY values
operators have explicitly published in SiteSettings.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

# v3.56.0 (2026-05-21): helper modules from the parallel trifecta wave.
# Each module returns a dict keyed by cockpit section name. Imported here so
# the context processor merges them into the appropriate host branch.
from .cockpit_tenant_dashboard import build_tenant_dashboard_cockpit
from .cockpit_manager_200x import manager_200x_defaults

# v3.57.0 (2026-05-21): platform-wide parity sweep helpers.
#   * cockpit_front_office_200x.front_office_200x_defaults — 10 NEW manager-host
#     /super/** elements (revenue cohort / NPS ticker / support burndown / deploy
#     pipeline / churn scorecard / AI fixes feed / capacity planning / regional
#     clocks / onboarding pipeline / audit wordcloud). Keys verified disjoint
#     from the 10 v3.56.0 manager_200x keys.
#   * cockpit_tenant_v3_extended.build_tenant_v3_extended_cockpit — 10 NEW
#     tenant-host v3 sections (ai_study_buddy / parent_teacher_thread /
#     realtime_presence / gradebook_trend / attendance_heatmap /
#     financial_timeline / sibling_compare / life_event_timeline /
#     calendar_weather / lesson_of_day). Keys verified disjoint from the 7
#     v3.56.0 tenant_dashboard keys + footer/community_band/newsletter_band.
from .cockpit_front_office_200x import front_office_200x_defaults
from .cockpit_tenant_v3_extended import build_tenant_v3_extended_cockpit


# ============================================================
# v3.56.0 — operator override overlay
# ============================================================

def _deep_merge(base: Any, override: Any) -> Any:
    """Recursively merge `override` ON TOP OF `base`.

    Rules:
      - dict + dict → recurse per key (override wins per leaf)
      - list (in override) → replaces base list wholesale (operators set their
        own trust pillar / contact / quote lists; partial-list merging would be
        surprising)
      - scalars (str/int/bool/None/lazy) in override → wins UNLESS override is
        None or empty-string (keeps base — empty operator field shouldn't blank
        out a sensible default)
      - type mismatch → override wins

    Lazy-translation objects from `gettext_lazy` are treated as scalars.
    """
    if isinstance(base, dict) and isinstance(override, dict):
        out: dict[str, Any] = dict(base)
        for key, val in override.items():
            if key in out:
                out[key] = _deep_merge(out[key], val)
            else:
                out[key] = val
        return out
    # Empty override → preserve base default
    if override is None:
        return base
    if isinstance(override, str) and override == "":
        return base
    return override


def _resolve_cockpit_payload(request) -> dict[str, Any]:
    """Pull `cockpit_payload` from SiteSettings (v3.56.0 admin-UI wave field).

    Returns `{}` when:
      - no SiteSettings attached to request
      - field absent (older deployment that hasn't migrated)
      - field is non-dict (corrupted state)
    """
    site = getattr(request, "site_settings", None) or getattr(request, "SITE", None)
    if site is None:
        return {}
    payload = getattr(site, "cockpit_payload", None)
    if not isinstance(payload, dict):
        return {}
    return payload


# Default activity feed events. Production wave will source these from
# the platform event stream (audit log + provisioning events + billing).
_DEFAULT_ACTIVITY_EVENTS: list[dict[str, Any]] = [
    {
        "icon": "🆕",
        "severity": "success",
        "text": _("New school provisioned — Saint Sebastien Academy"),
        "time_label": _("12s ago"),
    },
    {
        "icon": "↗",
        "severity": "success",
        "text": _("MRR up $420 this week"),
        "time_label": _("1m ago"),
    },
    {
        "icon": "🚨",
        "severity": "danger",
        "text": _("Tenant #567 webhook drift detected"),
        "time_label": _("2m ago"),
    },
    {
        "icon": "🎫",
        "severity": "info",
        "text": _("5 new support tickets"),
        "time_label": _("4m ago"),
    },
    {
        "icon": "✓",
        "severity": "success",
        "text": _("Migration sync complete for 12 schools"),
        "time_label": _("6m ago"),
    },
    {
        "icon": "⚠",
        "severity": "warn",
        "text": _("2 schools approaching invoice due date"),
        "time_label": _("8m ago"),
    },
    {
        "icon": "⚡",
        "severity": "info",
        "text": _("Marketplace app \"Attendance Pro\" updated"),
        "time_label": _("15m ago"),
    },
]


# Default platform pulse cards. Values are placeholders until the admin
# wave wires them to live aggregates (apps/observability/metrics.py
# already exposes the underlying counts).
_DEFAULT_PULSE_CARDS: list[dict[str, Any]] = [
    {
        "head": _("Schools"),
        "severity": "ok",
        "value": "—",
        "label": _("Healthy"),
        "delta": None,
        "delta_direction": None,
    },
    {
        "head": _("Incidents"),
        "severity": "warn",
        "value": "—",
        "label": _("Open"),
        "delta": None,
        "delta_direction": None,
    },
    {
        "head": _("Countries"),
        "severity": "info",
        "value": "—",
        "label": _("Live coverage"),
        "delta": None,
        "delta_direction": None,
    },
    {
        "head": _("MRR"),
        "severity": "ok",
        "value": "—",
        "label": _("Recurring"),
        "delta": None,
        "delta_direction": None,
    },
    {
        "head": _("Webhooks"),
        "severity": "ok",
        "value": "—",
        "label": _("Drift"),
        "delta": None,
        "delta_direction": None,
    },
    {
        "head": _("Pipeline"),
        "severity": "info",
        "value": "—",
        "label": _("Onboarding"),
        "delta": None,
        "delta_direction": None,
    },
]


# ============================================================
# v3.55.0 civic footer defaults
# ============================================================

# Manager (operator) footer — corporate gateway pattern, dark chrome.
# Template already inlines the dark variant; this is the structured config
# operators can override in SiteSettings.cockpit_payload.footer.
_DEFAULT_MANAGER_FOOTER: dict[str, Any] = {
    "brand": {
        "wordmark": "RunMyCampus Manager",
        "motto": _("Operator command surface."),
        "descriptor": _("Corporate gateway"),
        "founded_year": None,
    },
    "trust_pillars": [
        {"label": "🔒 SOC 2 · ISO 27001 · FERPA · GDPR", "tone": "secure"},
    ],
    "language": {"label": "English", "current_locale": "en", "has_switcher": False},
    "app_badges": [],
    "social": [],
    "contacts": [],
    "stat_line": _("Operating globally · 24×7 SOC · Audit-grade logs"),
    "legal_links": [
        {"label": _("Security"), "url": "#"},
        {"label": _("Privacy"), "url": "#"},
        {"label": _("Terms"), "url": "#"},
        {"label": _("Cookies"), "url": "#"},
    ],
    "copyright_holder": "RunMyCampus",
    "powered_by": {"label": "", "url": ""},  # operator footer doesn't show "powered by"
}


# ============================================================
# v3.55.2 tenant canvas community + newsletter bands
# ============================================================

def _tenant_community_band_defaults() -> dict[str, Any]:
    """Community band — student of the month, parent testimonial, district map.

    All three sub-blocks default to `enabled=False`. Operators opt in via
    `SiteSettings.cockpit_payload.community_band.*` (admin UI lands in a
    follow-up wave). Per-page templates can suppress via empty block override:

        {% block portal_community_band %}{% endblock %}
    """
    return {
        "enabled": False,
        "achievement": {
            "enabled": False,
            "title": _("Student of the month"),
            "period_label": "",
            "student_initials": "",
            "student_name": "",
            "student_subline": "",
            "teacher_quote": "",
            "teacher_cite": "",
        },
        "testimonial": {
            "enabled": False,
            "title": _("Parent voices"),
            "quotes": [],
            "interval_ms": 7000,
        },
        "map": {
            "enabled": False,
            "title": _("Visit us"),
            "period_label": "",
            "address_line_1": "",
            "address_line_2": "",
            "maps_url": "",
            "cta_label": _("Open in maps ↗"),
        },
    }


def _tenant_newsletter_band_defaults() -> dict[str, Any]:
    """Newsletter band — gradient signup banner above the footer.

    Disabled by default. Operator wires `submit_url` to in-platform endpoint
    (CSRF-protected) OR to external service like Mailchimp / Klaviyo
    (no CSRF — partial omits the token when submit_url is external).
    """
    return {
        "enabled": False,
        "title": _("Stay in the loop · weekly family digest"),
        "subtitle": _("Term highlights · upcoming events · 1 email every Sunday"),
        "placeholder": "parent@email.com",
        "cta_label": _("Subscribe →"),
        "submit_url": "",
        "privacy_url": "",
        "privacy_label": _("privacy notice"),
    }


def _tenant_footer_defaults(site: Any | None) -> dict[str, Any]:
    """Tenant civic footer — pulled from SITE model when available.

    `site` is the tenant's SiteSettings instance (or None on PUBLIC_BRAND_MODE).
    Returns a structure the partial can render even when most fields are
    empty — the partial short-circuits per-tier when its data is absent.
    """
    wordmark = ""
    motto = ""
    founded_year: int | None = None
    phone = ""
    email = ""
    address = ""

    if site is not None:
        wordmark = getattr(site, "company_name", "") or getattr(site, "site_name", "") or ""
        motto = getattr(site, "footer_motto", "") or ""
        try:
            founded_year = int(getattr(site, "footer_founded_year", 0) or 0) or None
        except (TypeError, ValueError):
            founded_year = None
        phone = getattr(site, "company_phone", "") or ""
        email = getattr(site, "company_email", "") or ""
        address = getattr(site, "company_address", "") or ""

    contacts: list[dict[str, Any]] = []
    if phone:
        contacts.append({"kind": "phone", "value": phone, "href": f"tel:{phone}", "glyph": "📞"})
    if email:
        contacts.append({"kind": "email", "value": email, "href": f"mailto:{email}", "glyph": "📧"})
    if address:
        contacts.append({"kind": "address", "value": address, "href": "", "glyph": "📍"})

    return {
        "brand": {
            "wordmark": wordmark,
            "motto": motto,
            "founded_year": founded_year,
            "descriptor": _("Family portal"),
        },
        # Default tenant trust pillar — operators can extend in SiteSettings.
        "trust_pillars": [
            {"label": "🔒 FERPA · WCAG 2.1 AA", "tone": "secure"},
        ],
        "language": {
            "label": "",  # template falls back to LANGUAGE_NAME_LOCAL
            "current_locale": "",
            "has_switcher": True,
        },
        # App badges + social default to empty — operators publish via SiteSettings.
        "app_badges": [],
        "social": [],
        "contacts": contacts,
        "stat_line": "",
        "legal_links": [],
        "copyright_holder": wordmark,
        "powered_by": {"label": "RunMyCampus", "url": ""},
    }


def cockpit_context(request) -> dict[str, Any]:
    """Cockpit v7 defaults + future SiteSettings override hook.

    Returns a single top-level key `cockpit` so templates can write
    `{{ cockpit.brand.tagline }}` / `{% if cockpit.activity_feed.enabled %}`
    etc. without polluting the global context namespace.

    Activity ticker + pulse metrics render only when their `enabled`
    flag is True AND their data list is non-empty. That makes the
    partials safe to include unconditionally — non-cockpit surfaces
    that don't populate this context simply skip rendering.

    v3.55.0 adds `cockpit.footer.*` for the civic 4-tier footer, emitted
    on BOTH manager AND tenant hosts (with different default shapes).
    """
    is_manager_host = False
    try:
        is_manager_host = getattr(request, "public_host_kind", "") == "manager"
    except AttributeError:
        pass

    # Manager host — full operator cockpit + dark-chrome footer config +
    # v3.56.0 200x manager elements (AI copilot rail / world map / forecast /
    # heatmap / waterfall / audit feed / trust nutrition / SLO clocks / op
    # presence / notebook). All 200x sections default `enabled=False`.
    if is_manager_host:
        manager_cockpit: dict[str, Any] = {
            "brand": {
                "wordmark": "RunMyCampus",
                "product_pill": _("Manager"),
                "tagline": _("Operator command surface"),
            },
            "activity_feed": {
                "enabled": True,
                "scroll_seconds": 60,
                "events": _DEFAULT_ACTIVITY_EVENTS,
            },
            "pulse_metrics": {
                "label": _("Platform pulse · live"),
                "show_live_dot": True,
                "cards": _DEFAULT_PULSE_CARDS,
            },
            "workspace_context": {
                "enabled": True,
                "show_role": True,
                "scope_dropdown": True,
                "collapse_toggle": True,
                "scope_label": _("All tenants · Global"),
            },
            "breadcrumb": {
                "show_root_link": True,
                "separator": "›",
            },
            "footer": _DEFAULT_MANAGER_FOOTER,
        }
        # 200x manager element defaults (all enabled=False).
        manager_cockpit.update(manager_200x_defaults())
        # v3.57.0: 10 NEW /super/** front-office 200x elements (all enabled=False).
        manager_cockpit.update(front_office_200x_defaults())

        # Overlay operator-saved cockpit_payload (footer / community_band /
        # newsletter_band per Agent A's admin form; future waves extend to
        # cover dashboard + 200x sections).
        payload = _resolve_cockpit_payload(request)
        if payload:
            manager_cockpit = _deep_merge(manager_cockpit, payload)

        return {"cockpit": manager_cockpit}

    # Tenant host — civic footer + community band + newsletter band +
    # v3.56.0 v2 dashboard sections (workspace_context_tenant / today_snapshot /
    # quick_actions / upcoming_events / activity_timeline / achievements /
    # teacher_spotlight). All dashboard sections default `enabled=False`.
    # No operator pulse/ticker leak. PII safety: school-entity values only.
    site = getattr(request, "site_settings", None) or getattr(request, "SITE", None)
    tenant_cockpit: dict[str, Any] = {
        "footer": _tenant_footer_defaults(site),
        "community_band": _tenant_community_band_defaults(),
        "newsletter_band": _tenant_newsletter_band_defaults(),
    }
    # v2 dashboard section defaults from cockpit_tenant_dashboard helper.
    tenant_cockpit.update(build_tenant_dashboard_cockpit())
    # v3.57.0: 10 NEW v3 100x tenant cockpit sections (all enabled=False).
    tenant_cockpit.update(build_tenant_v3_extended_cockpit())

    # Overlay operator-saved cockpit_payload.
    payload = _resolve_cockpit_payload(request)
    if payload:
        tenant_cockpit = _deep_merge(tenant_cockpit, payload)

    return {"cockpit": tenant_cockpit}
