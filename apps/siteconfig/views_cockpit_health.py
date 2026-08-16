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
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.utils.translation import gettext_lazy as _
from django.urls import NoReverseMatch, reverse
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
    (1, "Passkeys and trusted devices", "accounts:security_trust_hub"),
    (2, "Returning-user entrance", "accounts:login"),
    (3, "Role-aware sign-in methods", "accounts:login"),
    (4, "Offline continuity", "portal:device_registrations_index"),
    (5, "School-day information", "communication:announcement_list_pending"),
    (6, "Tenant front-door publisher", "communication:announcement_create"),
    (7, "Governed local partners", "siteconfig:cockpit_configure"),
    (8, "Guided recovery", "accounts:password_reset"),
    (9, "Verified-school protection", "/school/configuration/?focus=school-profile#configuration-school-profile"),
    (10, "Accessible authentication", "accounts:login"),
    (11, "Public-data access assistant", "accounts:login"),
    (12, "Front-door health and diagnostics", "siteconfig:cockpit_health"),
)

_LOGIN_FRONT_DOOR_MARKERS: dict[int, tuple[tuple[str, str], ...]] = {
    1: (("apps/accounts/views_passkey.py", "passkey_login_verify"),),
    2: (("static/js/rmc-auth-login-immersive.js", "roleMemoryKey"),),
    3: (("templates/auth/login.html", "data-rmc-auth-role"),),
    4: (("static/js/rmc-offline-login-unlock.js", "rmc_offline_active_capability"), ("static/js/rmc-offline-auth-enrollment.js", "sealCapability")),
    5: (("apps/accounts/login_immersive_canvas.py", "dash_feed"), ("templates/auth/partials/login_immersive_dash_panels.html", "LOGIN_IMMERSIVE.dash_feed")),
    6: (
        ("apps/communication/forms_announcements.py", '"scheduled_at"'),
        ("templates/communication/announcement_create.html", "form.scheduled_at"),
        ("apps/communication/models.py", "AnnouncementAuditLog"),
    ),
    7: (("apps/siteconfig/forms_cockpit.py", "lic_sponsored_lines"),),
    8: (("apps/accounts/views_magic_link.py", "magic_link_request"), ("apps/accounts/password_reset.py", "PortalPasswordResetForm")),
    9: (("apps/accounts/views_passkey.py", "tenant mismatch"),),
    10: (
        ("templates/auth/login.html", "data-rmc-auth-contrast"),
        ("templates/auth/login.html", "data-rmc-auth-motion"),
        ("static/css/auth-login-canvas.css", "data-rmc-auth-reduce-motion"),
    ),
    11: (("templates/auth/login.html", "data-rmc-access-assistant"),),
    12: (("templates/siteconfig/super/cockpit_health.html", "data-rmc-login-front-door-health"),),
}


def _build_login_front_door_health() -> tuple[list[dict[str, Any]], int]:
    """Verify shipped wiring without reading or exposing tenant/user content."""
    base = Path(settings.BASE_DIR)
    rows: list[dict[str, Any]] = []
    for number, label, action_target in _LOGIN_FRONT_DOOR_CAPABILITIES:
        checks = _LOGIN_FRONT_DOOR_MARKERS.get(number, ())
        ready = bool(checks)
        for relative_path, marker in checks:
            try:
                ready = ready and marker in (base / relative_path).read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                ready = False
        try:
            action_url = reverse(action_target) if ":" in action_target else action_target
        except NoReverseMatch:
            action_url = ""
            ready = False
        rows.append({"number": number, "label": label, "status": "ready" if ready else "attention", "action_url": action_url})
    ready_count = sum(row["status"] == "ready" for row in rows)
    return rows, round((ready_count / len(rows)) * 100) if rows else 0


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
        capabilities, score = _build_login_front_door_health()
        ctx["login_front_door_capabilities"] = capabilities
        ctx["login_front_door_score"] = score
        ctx["page_title"] = _("Cockpit health")
        return ctx
