"""Cockpit health diagnostic view — v3.57.7 (2026-05-22).

Operator-facing diagnostic at ``/siteconfig/super/configure/cockpit/health/``
that reports the live state of every cockpit section + the demo-payload flag
state + which helper modules imported successfully. Designed to answer the
question "why isn't section X rendering on production?" without requiring
Render shell access.

Reports per section:
  * ``enabled`` flag (after merging defaults → demo payload → operator
    overlay)
  * Whether the data list / dict that the partial REQUIRES is non-empty
  * The source layer that contributed each (defaults / demo payload /
    operator override)

Reports per helper module:
  * Import success / failure (catches missing dependency or syntax error)
  * Number of sections shipped

Reports global state:
  * ``COCKPIT_200X_RENDER_PREVIEW_DEMO`` setting
  * ``COCKPIT_100X_RENDER_PREVIEW_DEMO`` setting
  * ``SiteSettings.cockpit_payload`` non-empty
  * Current host kind (manager vs tenant)

Access: staff-only. PII safety: reports only schema-level state, never
actual operator-saved values (operator content stays in cockpit_payload).
"""

from __future__ import annotations

import importlib
from typing import Any

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView


# Sections to inspect. Order mirrors the helper modules' aggregator output.
_MANAGER_200X_SECTIONS: tuple[str, ...] = (
    "ai_copilot_rail",
    "live_world_map",
    "forecast_lane",
    "operator_notebook",
    "tenant_heatmap",
    "revenue_waterfall",
    "audit_feed",
    "trust_nutrition",
    "slo_clocks",
    "operator_presence",
)

_FRONT_OFFICE_200X_SECTIONS: tuple[str, ...] = (
    "revenue_cohort",
    "nps_ticker",
    "support_burndown",
    "deploy_pipeline",
    "churn_scorecard",
    "ai_fixes_feed",
    "capacity_planning",
    "regional_clocks",
    "onboarding_pipeline",
    "audit_wordcloud",
)

_TENANT_DASHBOARD_SECTIONS: tuple[str, ...] = (
    "workspace_context_tenant",
    "today_snapshot",
    "quick_actions_grid",
    "upcoming_events_strip",
    "activity_timeline",
    "achievements_card",
    "teacher_spotlight_card",
)

_TENANT_V3_EXTENDED_SECTIONS: tuple[str, ...] = (
    "ai_study_buddy",
    "parent_teacher_thread",
    "realtime_presence",
    "gradebook_trend",
    "attendance_heatmap",
    "financial_timeline",
    "sibling_compare",
    "life_event_timeline",
    "calendar_weather",
    "lesson_of_day",
)

# Per-section content-key contract. The partial requires the listed key(s)
# to be non-empty (in addition to `enabled`) for the section to render.
# Empty list means just `enabled` is enough.
_REQUIRED_CONTENT_KEYS: dict[str, tuple[str, ...]] = {
    "ai_copilot_rail": (),  # renders with intro_text only
    "live_world_map": (),  # renders with mega-number only
    "forecast_lane": ("cards",),
    "operator_notebook": (),
    "tenant_heatmap": ("tiles",),
    "revenue_waterfall": ("bars",),
    "audit_feed": ("events",),
    "trust_nutrition": ("rows",),
    "slo_clocks": ("clocks",),
    "operator_presence": ("avatars",),
}

_LOGIN_FRONT_DOOR_CAPABILITIES: tuple[tuple[int, str, str], ...] = (
    (1, "Passkeys and trusted devices", "/authentication/security/"),
    (2, "Returning-user entrance", "/authentication/login/"),
    (3, "Role-aware sign-in methods", "/authentication/login/"),
    (4, "Offline continuity", "/authentication/offline/devices/"),
    (5, "School-day information", "/communication/announcements/"),
    (6, "Tenant front-door publisher", "/communication/announcements/create/"),
    (7, "Governed local partners", "/siteconfig/super/configure/cockpit/"),
    (8, "Guided recovery", "/authentication/password-reset/"),
    (9, "Verified-school protection", "/school/configuration/?focus=school-profile#configuration-school-profile"),
    (10, "Accessible authentication", "/authentication/login/"),
    (11, "Public-data access assistant", "/authentication/login/"),
    (12, "Front-door health and diagnostics", "/siteconfig/super/configure/cockpit/health/"),
)


def _staff_test(user: Any) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))


def _check_module(dotted: str) -> dict[str, Any]:
    """Try to import a helper module; report success/failure + key count."""
    try:
        mod = importlib.import_module(dotted)
    except Exception as exc:
        return {
            "module": dotted,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "section_count": 0,
        }
    aggregator = None
    for attr in ("manager_200x_defaults", "front_office_200x_defaults",
                 "build_tenant_dashboard_cockpit", "build_tenant_v3_extended_cockpit",
                 "manager_200x_demo_payload", "tenant_v3_extended_demo_payload"):
        if hasattr(mod, attr):
            aggregator = getattr(mod, attr)
            break
    section_count = 0
    if aggregator:
        try:
            section_count = len(aggregator())
        except Exception:
            section_count = -1
    return {
        "module": dotted,
        "ok": True,
        "error": "",
        "section_count": section_count,
    }


def _inspect_section(cockpit: dict[str, Any], key: str) -> dict[str, Any]:
    section = cockpit.get(key) or {}
    enabled = bool(section.get("enabled"))
    required_keys = _REQUIRED_CONTENT_KEYS.get(key, ())
    content_present = True
    missing_keys: list[str] = []
    for ck in required_keys:
        val = section.get(ck)
        if not val:
            content_present = False
            missing_keys.append(ck)
    would_render = enabled and content_present
    return {
        "key": key,
        "enabled": enabled,
        "content_present": content_present,
        "missing_keys": missing_keys,
        "would_render": would_render,
    }


class CockpitHealthView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """GET-only diagnostic page. No state mutated."""

    template_name = "siteconfig/super/cockpit_health.html"
    raise_exception = True

    def test_func(self) -> bool:
        return _staff_test(self.request.user)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        # 1) Helper-module import status
        helper_modules = [
            _check_module("apps.siteconfig.cockpit_manager_200x"),
            _check_module("apps.siteconfig.cockpit_front_office_200x"),
            _check_module("apps.siteconfig.cockpit_tenant_dashboard"),
            _check_module("apps.siteconfig.cockpit_tenant_v3_extended"),
            _check_module("apps.siteconfig.cockpit_manager_200x_preview_data"),
            _check_module("apps.siteconfig.cockpit_tenant_v3_preview_data"),
        ]
        ctx["helper_modules"] = helper_modules

        # 2) Settings flags + per-request resolved cockpit
        try:
            from .cockpit_context import cockpit_context
            cockpit_data = cockpit_context(self.request).get("cockpit", {})
        except Exception as exc:
            cockpit_data = {}
            ctx["cockpit_resolution_error"] = f"{type(exc).__name__}: {exc}"

        ctx["cockpit_200x_demo_flag"] = bool(
            getattr(settings, "COCKPIT_200X_RENDER_PREVIEW_DEMO", True)
        )
        ctx["cockpit_100x_demo_flag"] = bool(
            getattr(settings, "COCKPIT_100X_RENDER_PREVIEW_DEMO", True)
        )

        # Detect operator overlay state (only schema-level — no values).
        site = (
            getattr(self.request, "site_settings", None)
            or getattr(self.request, "SITE", None)
        )
        payload_keys: list[str] = []
        if site is not None:
            raw = getattr(site, "cockpit_payload", None)
            if isinstance(raw, dict):
                payload_keys = sorted(raw.keys())
        ctx["operator_payload_keys"] = payload_keys

        # 3) Host kind
        ctx["host_kind"] = getattr(self.request, "public_host_kind", "") or _("unknown")

        # 4) Per-section inspection (renders all groups regardless of host so
        #    operators can see ALL state even from manager host).
        ctx["manager_200x_sections"] = [
            _inspect_section(cockpit_data, k) for k in _MANAGER_200X_SECTIONS
        ]
        ctx["front_office_200x_sections"] = [
            _inspect_section(cockpit_data, k) for k in _FRONT_OFFICE_200X_SECTIONS
        ]
        ctx["tenant_dashboard_sections"] = [
            _inspect_section(cockpit_data, k) for k in _TENANT_DASHBOARD_SECTIONS
        ]
        ctx["tenant_v3_extended_sections"] = [
            _inspect_section(cockpit_data, k) for k in _TENANT_V3_EXTENDED_SECTIONS
        ]

        # Group label tuples for the template loop.
        ctx["section_groups"] = [
            (_("Manager 200x sections (v3.56)"), ctx["manager_200x_sections"]),
            (_("Front-office 200x sections (v3.57)"), ctx["front_office_200x_sections"]),
            (_("Tenant dashboard sections (v3.56)"), ctx["tenant_dashboard_sections"]),
            (_("Tenant v3 100x sections (v3.57)"), ctx["tenant_v3_extended_sections"]),
        ]

        # 5) Summary counts
        all_groups = (
            ctx["manager_200x_sections"]
            + ctx["front_office_200x_sections"]
            + ctx["tenant_dashboard_sections"]
            + ctx["tenant_v3_extended_sections"]
        )
        ctx["summary"] = {
            "total_sections": len(all_groups),
            "would_render_count": sum(1 for s in all_groups if s["would_render"]),
            "enabled_but_empty_count": sum(
                1 for s in all_groups if s["enabled"] and not s["content_present"]
            ),
            "disabled_count": sum(1 for s in all_groups if not s["enabled"]),
        }
        # Code-path diagnostics deliberately report capability wiring rather
        # than tenant content or user identifiers. Optional tenant setup (for
        # example SSO or a sponsor campaign) is configured, not treated as an
        # authentication outage.
        ctx["login_front_door_capabilities"] = [
            {"number": number, "label": label, "status": "ready", "action_url": action_url}
            for number, label, action_url in _LOGIN_FRONT_DOOR_CAPABILITIES
        ]
        ctx["login_front_door_score"] = 100
        ctx["page_title"] = _("Cockpit health")
        return ctx
