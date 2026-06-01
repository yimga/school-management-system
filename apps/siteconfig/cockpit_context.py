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

# v3.57.3 (2026-05-21): preview demo payloads — pre-populated sample content
# that mirrors the v8 200x manager preview + v3 100x tenant preview HTML
# artifacts in `docs/generated/`. When the corresponding settings flags are
# True (defaults: True so the shell renders the preview UI out of the box),
# the orchestrator overlays these payloads onto the helper defaults so each
# 200x / 100x section becomes `enabled=True` + populated with sample data.
# Operators override individual sections via SiteSettings.cockpit_payload
# (the v3.57.1 admin toggle UI). To disable the whole demo, set
# COCKPIT_200X_RENDER_PREVIEW_DEMO=False / COCKPIT_100X_RENDER_PREVIEW_DEMO=False.
from .cockpit_manager_200x_preview_data import manager_200x_demo_payload
from .cockpit_tenant_v3_preview_data import tenant_v3_extended_demo_payload


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


def _pick_activity_incident_banner(ticker_section: dict[str, Any]) -> dict[str, Any] | None:
    from apps.siteconfig.cockpit_incident_banner import _pick_activity_incident_banner as _pick

    return _pick(ticker_section)


def _pick_operator_incident_banner(
    manager_cockpit: dict[str, Any],
    request=None,
) -> dict[str, Any] | None:
    """First warn/danger operator activity card for Tier-3 ephemeral canvas banner."""
    if request is not None:
        from apps.siteconfig.cockpit_incident_banner import resolve_operator_incident_banner

        return resolve_operator_incident_banner(request, manager_cockpit)
    return _pick_activity_incident_banner(manager_cockpit.get("activity_ticker") or {})


def _pick_tenant_incident_banner(
    tenant_cockpit: dict[str, Any],
    request=None,
) -> dict[str, Any] | None:
    """Tenant Tier-3 banner — never reads operator activity_ticker."""
    if request is not None:
        from apps.siteconfig.cockpit_incident_banner import resolve_tenant_incident_banner

        return resolve_tenant_incident_banner(request, tenant_cockpit)
    return _pick_activity_incident_banner(tenant_cockpit.get("tenant_activity_ticker") or {})


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


# Default platform pulse cards — v3.57.4 demo values byte-mirrored from the
# v8 200x preview at docs/generated/preview_app_shell_manager_v8_200x.html.
# To restore honest "—" placeholders (e.g. for a production deploy before
# real metrics are wired), set settings.COCKPIT_200X_RENDER_PREVIEW_DEMO=False
# (the orchestrator below replaces these cards with all-"—" placeholders in
# that branch). Live aggregates from apps/observability/metrics.py will land
# in a follow-up wave per the cockpit configurability contract.
# v3.58.0 (2026-05-22): real-data resolver bridge. The service module ships
# 6 query-based resolvers + a deterministic empty-state contract. We wrap the
# import + call in a top-level try/except so even a module-load failure cannot
# break the context processor (which runs on every request).
def _resolve_pulse_cards_safely() -> list[dict[str, Any]]:
    try:
        from .cockpit_platform_pulse_service import resolve_pulse_cards
        return resolve_pulse_cards()
    except Exception:
        # Module unavailable or all resolvers crashed — fall back to a static
        # 6-card empty-state shell so the strip still renders 6 cards.
        return [
            {"head": _("Schools"),   "severity": "muted", "value": "—", "label": _("Healthy"),       "delta": "", "delta_direction": None},
            {"head": _("Incidents"), "severity": "muted", "value": "—", "label": _("Open"),          "delta": "", "delta_direction": None},
            {"head": _("Countries"), "severity": "muted", "value": "—", "label": _("Live coverage"), "delta": "", "delta_direction": None},
            {"head": _("MRR"),       "severity": "muted", "value": "—", "label": _("Recurring"),     "delta": "", "delta_direction": None},
            {"head": _("Webhooks"),  "severity": "muted", "value": "—", "label": _("Drift"),         "delta": "", "delta_direction": None},
            {"head": _("Pipeline"),  "severity": "muted", "value": "—", "label": _("Onboarding"),    "delta": "", "delta_direction": None},
        ]


_DEFAULT_PULSE_CARDS: list[dict[str, Any]] = [
    {
        "head": _("Schools"),
        "severity": "ok",
        "value": "168",
        "label": _("Healthy"),
        "delta": "▲ +3 this week",
        "delta_direction": "up",
        "spark_points": "158,160,162,164,166,167,168",
    },
    {
        "head": _("Incidents"),
        "severity": "warn",
        "value": "12",
        "label": _("Open"),
        "delta": "▲ 4 vs 7d avg",
        "delta_direction": "up",
        "spark_points": "8,9,9,10,11,11,12",
    },
    {
        "head": _("Countries"),
        "severity": "info",
        "value": "2 / 249",
        "label": _("Live coverage"),
        "delta": "→ no change",
        "delta_direction": None,
        "spark_points": "2,2,2,2,2,2,2",
    },
    {
        "head": _("MRR"),
        "severity": "ok",
        "value": "$42k",
        "label": _("Recurring"),
        "delta": "▲ +$420 wk",
        "delta_direction": "up",
        "spark_points": "39000,39800,40100,40800,41200,41600,42000",
    },
    {
        "head": _("Webhooks"),
        "severity": "ok",
        "value": "0",
        "label": _("Drift"),
        "delta": "— stable",
        "delta_direction": None,
        "spark_points": "0,0,0,0,0,0,0",
    },
    {
        "head": _("Pipeline"),
        "severity": "info",
        "value": "3",
        "label": _("Onboarding"),
        "delta": "▲ 1 new today",
        "delta_direction": "up",
        "spark_points": "1,1,2,2,2,2,3",
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


# ============================================================
# v3.58.x Wave 9 — sibling_compare operator-editable copy defaults
# ============================================================


def _sibling_compare_defaults() -> dict[str, Any]:
    """Sibling-compare operator-editable chrome — PRIVACY-CONTRACT BOUNDED.

    PRIVACY CONTRACT (load-bearing — DO NOT relax)
    ----------------------------------------------
    Sibling-compare ``opt_in`` MUST remain False by default — NO sibling data
    renders without parent consent. This default factory deliberately does
    NOT carry an ``opt_in`` key into the cockpit cascade:

      - The cockpit payload (operator-published) configures ONLY copy +
        chrome: section ``enabled`` flag, titles, CTA labels, consent
        banner copy, denied-state message.
      - The ``opt_in`` boolean lives on a per-parent consent record
        OUTSIDE the cockpit payload (sourced at render time by the view
        context, not the operator admin UI).
      - There is intentionally NO ``opt_in_default`` field in this
        factory or in ``CockpitPayloadForm``. An operator-toggled
        opt-in default would defeat parent consent.

    The partial template ``templates/partials/cockpit/_sibling_compare.html``
    enforces the gate via:

        {% if cockpit.sibling_compare.enabled
              and cockpit.sibling_compare.opt_in
              and cockpit.sibling_compare.metrics %}

    Operator ``enabled=True`` surfaces the section CTA. Parent ``opt_in=True``
    (per-family consent record, NOT in cockpit_payload) is still required
    to render actual data. Helper module
    ``cockpit_tenant_v3_extended._tenant_sibling_compare_defaults()`` is the
    authoritative source for ``opt_in`` + ``metrics`` + ``privacy_notice``
    defaults; ``_deep_merge`` preserves those keys when this overlay lands.

    Schema (operator-editable subset only):
        enabled                          bool  (default False — section off)
        title                            str
        subtitle                         str
        cta_label                        str
        consent_banner_title             str
        consent_banner_body              str
        consent_grant_button_label       str
        consent_decline_button_label     str
        denied_state_message             str
    """
    return {
        "enabled": False,
        "title": _("Compare with siblings"),
        "subtitle": _("Side-by-side trend across your family"),
        "cta_label": _("Compare now"),
        "consent_banner_title": _("Family-comparison view"),
        "consent_banner_body": _(
            "Comparing siblings shows initials, current trend, and a small "
            "sparkline per metric — never full names. This view is hidden "
            "until you give consent and can be turned off at any time from "
            "Family settings."
        ),
        "consent_grant_button_label": _("Show sibling view"),
        "consent_decline_button_label": _("Keep private"),
        "denied_state_message": _(
            "No sibling data visible. You can opt in at any time from "
            "Family settings."
        ),
    }


# ============================================================
# v3.57.18 Wave 8 — public school-signup form defaults
# ============================================================

def _signup_form_defaults() -> dict[str, Any]:
    """Public self-service ``/signup/`` form — operator-configurable copy.

    Unlike most cockpit sections (which default to ``enabled=False`` and
    require operators to opt in), the signup form is the marketing-host
    front door — defaults to ``enabled=True`` so the page renders the
    moment the cascade lands.

    Schema (mirrors operator admin UI fields):
        signup_form:
          enabled           bool  (default True — front door)
          heading           str
          subheading        str
          button_label      str
          trust_pill_lines  list[{icon, label}]
          show_trust_pills  bool
          show_calendar_cards bool
          footer_login_label str
          footer_login_url  str   (empty → template falls back to
                                   {% url 'global_login_discovery' %})
    """
    return {
        "enabled": True,
        "heading": _("Start your school workspace"),
        "subheading": _(
            "Create your school on RunMyCampus. We'll send a verification "
            "link to your email — usually within a minute."
        ),
        "button_label": _("Create my school workspace"),
        "trust_pill_lines": [
            {"icon": "🔒", "label": _("256-bit SSL encryption")},
            {"icon": "🛡", "label": _("FERPA-aligned data handling")},
            {"icon": "☁", "label": _("Daily encrypted backups")},
            {"icon": "💳", "label": _("Stripe-secure billing")},
        ],
        "show_trust_pills": True,
        "show_calendar_cards": True,
        "footer_login_label": _("Find your school"),
        "footer_login_url": "",
    }


def _resolve_footer_language() -> tuple[str, str]:
    """Human-readable language label + BCP-47-ish code for civic footer."""
    from django.utils import translation

    from apps.siteconfig.translations import SUPPORTED_LANGUAGES

    code = (translation.get_language() or "en").strip() or "en"
    label = SUPPORTED_LANGUAGES.get(code)
    if not label and "-" in code:
        label = SUPPORTED_LANGUAGES.get(code.split("-", 1)[0])
    return label or "English", code


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

    lang_label, lang_code = _resolve_footer_language()

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
            "label": lang_label,
            "current_locale": lang_code,
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
                # v3.60.0 (2026-05-22): tuned from 60s → 40s.
                "scroll_seconds": 40,
                "events": _DEFAULT_ACTIVITY_EVENTS,
            },
            "pulse_metrics": {
                "label": _("Platform pulse · live"),
                "show_live_dot": True,
                # v3.58.0 (2026-05-22): real-data resolver. The
                # cockpit_platform_pulse_service queries actual models for the
                # 6 KPI cards (Schools / Incidents / Countries / MRR / Webhooks
                # / Pipeline). Each resolver is wrapped in try/except and
                # returns an honest empty-state card (value="—") on failure,
                # so the layout always renders 6 cards even when DB queries
                # fail or models aren't migrated on this environment.
                # The demo payload below still wins when
                # COCKPIT_200X_RENDER_PREVIEW_DEMO is True.
                "cards": _resolve_pulse_cards_safely(),
            },
            "workspace_context": {
                "enabled": False,
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
            # v3.57.18 Wave 8 — emit signup_form on the manager branch too
            # so a manager-host request to ``/signup/`` (e.g. via the public
            # marketing surface mounted on the same wsgi) still receives the
            # operator-configurable copy. The template's `cockpit.signup_form.
            # enabled` gate is the visibility control.
            "signup_form": _signup_form_defaults(),
        }
        # 200x manager element defaults (all enabled=False).
        manager_cockpit.update(manager_200x_defaults())
        # v3.57.0: 10 NEW /super/** front-office 200x elements (all enabled=False).
        manager_cockpit.update(front_office_200x_defaults())
        # v3.58.x Wave 9: sibling_compare operator-editable copy overlay.
        # Privacy-contract: this overlay carries copy + chrome only —
        # `opt_in` / `metrics` / `privacy_notice` flow from the helper
        # module's tenant defaults via _deep_merge (manager host doesn't
        # render the section but the key is published for parity with the
        # admin UI so operators see a unified cockpit_payload schema).
        manager_cockpit["sibling_compare"] = _deep_merge(
            manager_cockpit.get("sibling_compare", {}),
            _sibling_compare_defaults(),
        )

        # v3.57.3: overlay the preview demo payload so the 10 manager 200x
        # sections render out of the box matching the v8 200x preview HTML.
        # Operators disable individual sections via the v3.57.1 admin toggles;
        # to disable the whole demo set COCKPIT_200X_RENDER_PREVIEW_DEMO=False.
        from django.conf import settings as _dj_settings
        if getattr(_dj_settings, "COCKPIT_200X_RENDER_PREVIEW_DEMO", True):
            manager_cockpit = _deep_merge(
                manager_cockpit, manager_200x_demo_payload()
            )

        # v3.58.2 (2026-05-22): real-data resolver overlay. The
        # cockpit_panels_realdata_service queries the platform models for the
        # 9 manager cockpit panels (operator_presence, activity_ticker,
        # audit_feed, live_world_map, tenant_heatmap, forecast_lane, slo_clocks,
        # revenue_waterfall, trust_nutrition). Each resolver is wrapped in
        # try/except — a None return leaves the slot pointed at whatever the
        # demo overlay (or static default) provided. Operator override below
        # still wins, so a SiteSettings.cockpit_payload value is final.
        try:
            from .cockpit_panels_realdata_service import resolve_panel_overrides
            real_panels = resolve_panel_overrides()
        except Exception:
            real_panels = {}
        if real_panels:
            manager_cockpit = _deep_merge(manager_cockpit, real_panels)

        # v3.58.x Wave 10 Agent Q (2026-05-22): GLOBAL activity ticker
        # real-data overlay. Runs only when (a) the Django settings flag
        # `ATK_REALDATA_ENABLED` is True (default), AND (b) the operator
        # hasn't disabled realdata via cockpit_payload.activity_ticker.
        # realdata_enabled=False. Best-effort — any failure returns {} so
        # we cleanly fall back to the demo/seed cards.
        from django.conf import settings as _atk_settings
        _atk_pre_payload = _resolve_cockpit_payload(request).get(
            "activity_ticker"
        ) or {}
        _atk_realdata_ok = (
            getattr(_atk_settings, "ATK_REALDATA_ENABLED", True)
            and _atk_pre_payload.get("realdata_enabled", True)
        )
        if _atk_realdata_ok:
            try:
                from .cockpit_activity_ticker_realdata import (
                    merge_activity_ticker_sections,
                    resolve_activity_ticker_cards,
                )
                ticker_real = resolve_activity_ticker_cards(request)
            except Exception:
                ticker_real = {}
            if ticker_real:
                manager_cockpit = merge_activity_ticker_sections(
                    manager_cockpit, ticker_real
                )

        # Overlay operator-saved cockpit_payload LAST so per-site overrides
        # (including section.enabled = False) win over both defaults and demo.
        payload = _resolve_cockpit_payload(request)
        if payload:
            manager_cockpit = _deep_merge(manager_cockpit, payload)

        acr = manager_cockpit.get("ai_copilot_rail") or {}
        if acr.get("enabled"):
            try:
                from apps.observability.ai_copilot_service import enrich_manager_copilot_rail

                manager_cockpit["ai_copilot_rail"] = _deep_merge(
                    acr, enrich_manager_copilot_rail(request)
                )
            except Exception:
                pass

        # v3.58.x Wave 10 Agent Q (2026-05-22): host-routing post-gate.
        # When `atk_enabled_on_manager=False` was persisted by the operator
        # in cockpit_payload.activity_ticker, force `enabled=False` so the
        # partial early-exits on `cockpit.activity_ticker.enabled` even
        # though `cards` are still populated by the demo/resolver. Default
        # (key absent) is True per the form field declaration.
        atk_section = manager_cockpit.get("activity_ticker") or {}
        if "enabled_on_manager" in atk_section and not atk_section.get(
            "enabled_on_manager"
        ):
            atk_section["enabled"] = False
            manager_cockpit["activity_ticker"] = atk_section
        elif atk_section.get("cards") and atk_section.get("enabled") is not False:
            atk_section["enabled"] = True
            manager_cockpit["activity_ticker"] = atk_section

        try:
            from .cockpit_calendar_weather_runtime import resolve_calendar_weather_runtime

            cw_runtime = resolve_calendar_weather_runtime(request)
            manager_cockpit["calendar_weather"] = _deep_merge(
                cw_runtime,
                manager_cockpit.get("calendar_weather") or {},
            )
        except Exception:
            pass

        rmc_page_help_on_copilot_rail = bool(
            (manager_cockpit.get("ai_copilot_rail") or {}).get("enabled")
        )
        return {
            "cockpit": manager_cockpit,
            "rmc_page_help_on_copilot_rail": rmc_page_help_on_copilot_rail,
            "operator_incident_banner": _pick_operator_incident_banner(
                manager_cockpit, request
            ),
        }

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
        # v3.57.18 Wave 8 — emit signup_form on the tenant/public branch so
        # the marketing-host `/signup/` template receives operator-configurable
        # copy. Defaults to enabled=True (front-door section); operators can
        # override individual fields (or disable wholesale) via
        # SiteSettings.cockpit_payload.signup_form.*.
        "signup_form": _signup_form_defaults(),
    }
    # v2 dashboard section defaults from cockpit_tenant_dashboard helper.
    tenant_cockpit.update(build_tenant_dashboard_cockpit())
    # v3.57.0: 10 NEW v3 100x tenant cockpit sections (all enabled=False).
    tenant_cockpit.update(build_tenant_v3_extended_cockpit())
    # v3.58.x Wave 9: sibling_compare operator-editable copy overlay.
    # Privacy-contract: this overlay carries copy + chrome only (title /
    # subtitle / CTA / consent banner / denied-state). `opt_in` /
    # `metrics` / `privacy_notice` flow from the helper module's
    # `_tenant_sibling_compare_defaults()` via _deep_merge — operator
    # admin UI cannot toggle `opt_in` to True. Parent consent record
    # (per-family, outside cockpit_payload) is the sole `opt_in` source.
    tenant_cockpit["sibling_compare"] = _deep_merge(
        tenant_cockpit.get("sibling_compare", {}),
        _sibling_compare_defaults(),
    )

    # v3.57.3: overlay the v3 100x tenant preview demo payload so the 10 new
    # tenant sections render out of the box matching the v3 100x preview HTML.
    # Sibling-compare honors its separate opt_in privacy gate inside the
    # section payload (no sibling data renders without parent consent).
    from django.conf import settings as _dj_settings
    if getattr(_dj_settings, "COCKPIT_100X_RENDER_PREVIEW_DEMO", True):
        tenant_cockpit = _deep_merge(
            tenant_cockpit, tenant_v3_extended_demo_payload()
        )

    # v3.58.x Wave 10 Agent Q (2026-05-22): tenant-scoped activity ticker
    # real-data overlay. Runs only when (a) the Django settings flag
    # `ATK_REALDATA_ENABLED` is True (default), AND (b) the operator
    # hasn't disabled realdata via cockpit_payload.activity_ticker.
    # realdata_enabled=False. Best-effort — any failure returns {} so
    # we cleanly fall back to operator-published seed cards.
    _atk_pre_payload = _resolve_cockpit_payload(request).get(
        "activity_ticker"
    ) or {}
    _atk_realdata_ok = (
        getattr(_dj_settings, "ATK_REALDATA_ENABLED", True)
        and _atk_pre_payload.get("realdata_enabled", True)
    )
    if _atk_realdata_ok:
        try:
            from .cockpit_activity_ticker_realdata import (
                merge_activity_ticker_sections,
                resolve_activity_ticker_cards,
            )
            ticker_real = resolve_activity_ticker_cards(request)
        except Exception:
            ticker_real = {}
        if ticker_real:
            tenant_cockpit = merge_activity_ticker_sections(tenant_cockpit, ticker_real)

    # Overlay operator-saved cockpit_payload LAST so per-site overrides win.
    payload = _resolve_cockpit_payload(request)
    raw_payload_tat = (
        (payload or {}).get("tenant_activity_ticker")
        if isinstance(payload, dict)
        else None
    )
    raw_tat_explicit_disabled = (
        isinstance(raw_payload_tat, dict) and raw_payload_tat.get("enabled") is False
    )
    if payload:
        tenant_cockpit = _deep_merge(tenant_cockpit, payload)

    # v4.01.27: tenant ticker default-on. Explicit opt-out ONLY when
    # tenant_activity_ticker.enabled=False is persisted in cockpit_payload.
    # Legacy activity_ticker.enabled_on_tenant=False (pre-batch-1599 form
    # default) no longer suppresses the ticker.
    tat_section = tenant_cockpit.get("tenant_activity_ticker") or {}
    if raw_tat_explicit_disabled:
        tat_section["enabled"] = False
    elif tat_section.get("cards"):
        tat_section["enabled"] = True
    if tat_section:
        tenant_cockpit["tenant_activity_ticker"] = tat_section

    try:
        from .cockpit_calendar_weather_runtime import resolve_calendar_weather_runtime

        cw_runtime = resolve_calendar_weather_runtime(request)
        tenant_cockpit["calendar_weather"] = _deep_merge(
            cw_runtime,
            tenant_cockpit.get("calendar_weather") or {},
        )
    except Exception:
        pass

    try:
        from apps.portal.tenant_cockpit_enrichment import enrich_tenant_cockpit_for_request

        tenant_cockpit = enrich_tenant_cockpit_for_request(request, tenant_cockpit)
    except Exception:
        pass

    return {
        "cockpit": tenant_cockpit,
        "rmc_page_help_on_copilot_rail": False,
        "tenant_incident_banner": _pick_tenant_incident_banner(tenant_cockpit, request),
    }
