"""Tenant role-home parity (batch 1484 — teacher/backend hero + legacy gates)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase

from apps.siteconfig.tests._template_nodes import assert_markup, assert_wires

from apps.portal.tenant_experience_command import build_tenant_experience_command
from apps.portal.context_processors import tenant_experience_command
from apps.portal.tenant_role_home import (
    build_tp_hero_context,
    build_tp_hero_contextual_line,
    is_tenant_role_home_landing_request,
    is_tp_v3_role_home_request,
    is_tp_v3_tenant_shell_request,
    role_home_show_legacy,
    tp_hero_ai_tier_line,
    tp_v3_role_home_shell_context,
)
from apps.accounts.models import User

ROOT = Path(__file__).resolve().parents[3]

PORTAL_BASE = ROOT / "templates/portal_base.html"
HERO_GREETING = ROOT / "templates/partials/tenant/hero_greeting.html"
COMMAND_STRIP = (
    ROOT / "templates/partials/tenant/experience_command_strip.html"
)
PROFILE_PAGE = ROOT / "templates/accounts/profile.html"
TEACHER_DASHBOARD = ROOT / "templates/teacher/dashboard.html"
NEXT_ACTION_STRIP = ROOT / "templates/components/next_action_strip.html"


class TenantRoleHomeHelperTests(TestCase):
    def test_legacy_flag_simple_query(self):
        class _Req:
            GET = {"simple": "1"}

        self.assertTrue(role_home_show_legacy(_Req()))

    @patch(
        "apps.portal.tenant_role_home.get_effective_config",
        # The shell resolves the academic-year badge through the config
        # resolver, which reads the RuntimeDefaults singleton from the DB.
        # get_effective_site_settings is fail-soft against a real outage
        # (it catches DatabaseError), but SimpleTestCase raises
        # DatabaseOperationForbidden, which subclasses AssertionError
        # precisely so that guard cannot absorb it. Stub the seam so the
        # shell flags below stay the subject of this test.
        side_effect=lambda key="", **kw: (
            "2025/2026" if key == "active_academic_year_name" else None
        ),
    )
    def test_v3_role_home_shell_context(self, _cfg):
        class _Match:
            url_name = "backend_dashboard"

        class _Req:
            GET = {}
            public_host_kind = "tenant"
            resolver_match = _Match()
            # Session + request-cached hat flags so the role getter
            # (portal_roles.get_effective_portal_role) resolves without a DB hit
            # under SimpleTestCase.
            session = {}
            _portal_teacher_hat = False
            _portal_parent_hat = False

            class user:
                is_authenticated = True
                role = "TEACHER"

        ctx = tp_v3_role_home_shell_context(_Req())
        self.assertTrue(ctx["tp_v3_role_home"])
        self.assertTrue(ctx["tp_v3_tenant_shell"])
        self.assertTrue(ctx["page_provides_own_h1"])
        self.assertIn("tp_brand_surface_pill", ctx)
        self.assertIn("tp_brand_tagline", ctx)
        # tp_header_brand.html renders this as the year badge.
        self.assertEqual(ctx["tp_brand_year_label"], "2025/2026")
        _Req.GET = {"simple": "legacy"}
        self.assertFalse(is_tp_v3_role_home_request(_Req()))
        ctx_legacy = tp_v3_role_home_shell_context(_Req())
        self.assertFalse(ctx_legacy["tp_v3_role_home"])
        self.assertTrue(ctx_legacy["tenant_role_home_landing"])
        self.assertTrue(is_tenant_role_home_landing_request(_Req()))

    def test_ai_tier_line_has_no_urls(self):
        line = tp_hero_ai_tier_line()
        self.assertIn("Assist tier:", line)
        self.assertNotIn("http", line.lower())
        self.assertNotIn("@", line)

    @patch(
        # Same DB seam as above: the hero reads portal_quick_actions through
        # the config resolver. An empty list keeps filter_portal_items honest
        # while the assertions below stay about the context shape.
        "apps.portal.tenant_role_home.get_effective_config",
        return_value=[],
    )
    def test_build_tp_hero_context_keys(self, _cfg):
        class _Req:
            GET = {}

        ctx = build_tp_hero_context(_Req(), role="TEACHER")
        self.assertEqual(ctx["tp_greeting_role"], "TEACHER")
        self.assertIn("portal_quick_actions", ctx)
        self.assertIn("tp_hero_ai_tier_line", ctx)
        self.assertIn("tenant_experience_command", ctx)

    def test_teacher_contextual_line_pending_marks(self):
        line = build_tp_hero_contextual_line(
            role=User.Role.TEACHER,
            pending_evaluations=3,
        )
        self.assertIn("3", line)
        self.assertIn("mark", line.lower())

    def test_admin_contextual_line_access_requests(self):
        line = build_tp_hero_contextual_line(
            role=User.Role.ADMIN,
            pending_access_requests=2,
        )
        self.assertIn("2", line)
        self.assertIn("access", line.lower())


class TenantExperienceCommandTests(SimpleTestCase):
    @patch(
        "apps.portal.tenant_experience_command._safe_reverse",
        side_effect=lambda name: f"/resolved/{name.replace(':', '/')}/",
    )
    def test_teacher_command_covers_profile_local_workflow_and_tools(self, _mock_reverse):
        req = MagicMock()
        req.user.email = "teacher@example.com"
        req.user.get_full_name.return_value = "Teacher One"
        req.school.country_code = "CM"
        req.school.name = "Example Academy"
        req.school.primary_color = "#14532d"
        req.site_settings.active_academic_year_name = "2026"

        command = build_tenant_experience_command(req, User.Role.TEACHER)

        self.assertTrue(command["enabled"])
        self.assertGreaterEqual(command["score"], 75)
        self.assertTrue(command["local_global"]["configured"])
        self.assertEqual(command["local_global"]["currency"], "XAF")
        labels = {action["label"] for action in command["actions"]}
        self.assertIn("Take attendance", labels)
        self.assertIn("Enter marks", labels)
        self.assertIn("Syllabus", labels)

    @patch(
        "apps.portal.tenant_experience_command._safe_reverse",
        side_effect=lambda name: f"/resolved/{name.replace(':', '/')}/",
    )
    def test_admin_command_prioritizes_studio_imports_and_marketplace(self, _mock_reverse):
        req = MagicMock()
        req.user.email = "admin@example.com"
        req.user.get_full_name.return_value = "Admin One"
        req.school.country_code = "NG"
        req.school.name = "Run Academy"
        req.school.logo_url = "https://cdn.example/logo.png"
        req.site_settings.active_academic_year_name = "2026"

        command = build_tenant_experience_command(req, User.Role.ADMIN)

        labels = [action["label"] for action in command["actions"]]
        self.assertEqual(labels[0], "School Studio")
        self.assertIn("Import setup", labels)
        self.assertIn("Template marketplace", labels)
        self.assertEqual(command["local_global"]["currency"], "NGN")

    @patch(
        "apps.portal.tenant_experience_command._safe_reverse",
        side_effect=lambda name: f"/resolved/{name.replace(':', '/')}/",
    )
    def test_school_operator_roles_do_not_fall_into_parent_toolbelt(self, _mock_reverse):
        req = MagicMock()
        req.user.email = "principal@example.com"
        req.user.get_full_name.return_value = "Principal One"
        req.school.country_code = "GH"
        req.school.name = "Accra Campus"
        req.school.logo_url = "https://cdn.example/logo.png"
        req.site_settings.active_academic_year_name = "2026"

        command = build_tenant_experience_command(req, User.Role.PRINCIPAL)

        labels = [action["label"] for action in command["actions"]]
        self.assertIn("School Studio", labels)
        self.assertNotIn("Family workflow", labels)

    @patch(
        "apps.portal.tenant_experience_command._safe_reverse",
        side_effect=lambda name: f"/resolved/{name.replace(':', '/')}/",
    )
    def test_context_processor_supplies_inner_page_command(self, _mock_reverse):
        req = MagicMock()
        req.user.is_authenticated = True
        req.user.role = User.Role.PARENT
        req.user.email = "parent@example.com"
        req.user.get_full_name.return_value = "Parent One"
        req.school.country_code = "CM"
        req.school.name = "Example Academy"
        req.school.primary_color = "#14532d"
        req.site_settings.active_academic_year_name = "2026"

        ctx = tenant_experience_command(req)

        self.assertTrue(ctx["tenant_experience_command"]["enabled"])
        self.assertEqual(ctx["tenant_experience_command"]["role"], User.Role.PARENT)


class TenantRoleHomeTemplateTests(SimpleTestCase):
    def test_teacher_dashboard_renders_v3_home_partial(self):
        # Teacher-100x retired the legacy hero_greeting + tdm-bg stack in favour of
        # the v3 role-home partial (_rmc_dh_teacher_home); the hero/chrome now comes
        # from portal_base via the tp_v3 shell, so the page just composes the partial.
        text = (ROOT / "templates/teacher/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("teacher/_rmc_dh_teacher_home.html", text)
        self.assertIn('extends "portal_base.html"', text)
        assert_wires(
            self, TEACHER_DASHBOARD, "_rmc_dh_teacher_home.html", "portal_base.html"
        )

    def test_backend_dashboard_has_hero_and_legacy_gate(self):
        text = (ROOT / "templates/accounts/backend_dashboard.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("hero_greeting.html", text)
        self.assertIn("backend_show_legacy_dashboard", text)
        gate_idx = text.find("backend_show_legacy_dashboard")
        legacy_idx = text.find("backend-dashboard-content")
        self.assertGreater(legacy_idx, 0)
        self.assertGreater(gate_idx, 0)
        self.assertLess(gate_idx, legacy_idx)

    def test_portal_base_wires_v3_role_home_contract(self):
        text = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
        self.assertIn("data-rmc-tp-v3-role-home", text)
        self.assertIn("data-rmc-tp-v3-shell", text)
        self.assertIn("tp_v3_tenant_shell", text)
        self.assertIn("rmc-tenant-v3-100x-role-home.css", text)
        self.assertIn("not tp_v3_tenant_shell", text)
        self.assertIn("rmc-tp-pulse-sheet.js", text)
        self.assertNotIn('class="portal-chathead"', text)
        self.assertIn('include "components/rmc_tenant_header_utilities.html"', text)
        assert_markup(
            self, PORTAL_BASE, "data-rmc-tp-v3-role-home", "data-rmc-tp-v3-shell"
        )
        assert_wires(self, PORTAL_BASE, "rmc_tenant_header_utilities.html")

    def test_tenant_shell_covers_inner_portal_route(self):
        class _Match:
            url_name = "cahier_list"
            namespace = "portal"

        class _Req:
            GET = {}
            public_host_kind = "tenant"
            resolver_match = _Match()

            class user:
                is_authenticated = True

        self.assertTrue(is_tp_v3_tenant_shell_request(_Req()))
        self.assertFalse(is_tp_v3_role_home_request(_Req()))

    def test_studio_os_inherits_tp_v3_tenant_shell(self):
        class _Match:
            url_name = "launch"
            namespace = "studio_os"

        class _Req:
            GET = {}
            public_host_kind = "tenant"
            resolver_match = _Match()

            class user:
                is_authenticated = True

        self.assertTrue(is_tp_v3_tenant_shell_request(_Req()))

    def test_portal_base_wires_tp_mission_strip(self):
        text = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
        self.assertIn("tp_mission_strip.html", text)
        self.assertIn("namespace != 'studio_os'", text)
        assert_wires(self, PORTAL_BASE, "tp_mission_strip.html")

    def test_tp_v3_includes_page_explain_strip(self):
        """v3 shells keep the compact page-explain bar (Core vs Context education)."""
        text = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
        self.assertIn("rmc_page_explain_strip.html", text)
        # Strip is no longer gated behind `not tp_v3_tenant_shell`.
        idx = text.find("rmc_page_explain_strip.html")
        window = text[max(0, idx - 180) : idx]
        self.assertNotIn("not tp_v3_tenant_shell", window)
        assert_wires(self, PORTAL_BASE, "rmc_page_explain_strip.html")

    def test_tp_v3_suppresses_global_next_action_strip(self):
        text = (ROOT / "templates/components/next_action_strip.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("not tp_v3_tenant_shell", text)
        # The gate above is template CODE and no render can see it; what
        # IS checkable is that the strip still emits its own surface.
        assert_markup(
            self, NEXT_ACTION_STRIP, 'data-rmc-next-action-strip="1"'
        )

    def test_tp_v3_suppresses_legacy_chrome_bands(self):
        text = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
        for partial in (
            "shell_chrome_security_posture_banner.html",
            "rmc_mfa_nudge.html",
            "_community_band.html",
            "_newsletter_band.html",
        ):
            idx = text.find(partial)
            self.assertGreater(idx, 0, partial)
            window = text[max(0, idx - 500) : idx]
            self.assertIn("not tp_v3_tenant_shell", window, partial)

    def test_hero_wires_tenant_experience_command_strip(self):
        text = (ROOT / "templates/partials/tenant/hero_greeting.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("experience_command_strip.html", text)
        strip = (
            ROOT / "templates/partials/tenant/experience_command_strip.html"
        ).read_text(encoding="utf-8")
        self.assertIn("data-rmc-tenant-experience-command", strip)
        self.assertIn("data-rmc-tenant-toolbelt", strip)
        # Bound to the STRIP, so the sound assertion has to be about the
        # strip -- one about hero_greeting would leave this vacuous.
        assert_wires(self, HERO_GREETING, "experience_command_strip.html")
        assert_markup(
            self,
            COMMAND_STRIP,
            "data-rmc-tenant-experience-command",
            "data-rmc-tenant-toolbelt",
        )

    def test_profile_page_wires_tenant_experience_command_strip(self):
        text = (ROOT / "templates/accounts/profile.html").read_text(encoding="utf-8")
        self.assertIn("experience_command_strip.html", text)
        assert_wires(self, PROFILE_PAGE, "experience_command_strip.html")

    def test_mission_strip_lives_in_dashboard_surface_not_header(self):
        portal = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
        self.assertIn('data-rmc-tp-mission-surface="1"', portal)
        header_chunk = portal.split('id="portalHeader"', 1)[1].split(
            "portal_shell_header_ticker_tenant", 1
        )[0]
        self.assertNotIn("tp_mission_strip.html", header_chunk)
        canvas_css = (
            ROOT / "static/css/rmc-tenant-workspace-canvas.css"
        ).read_text(encoding="utf-8")
        # v4.05.88: the main canvas is capped to a MEASURED workspace height
        # (--rmc-tenant-main-h, calc() fallback) so it always scrolls. This
        # replaced the prior `max-height: 100% !important`, whose percentage base
        # could resolve to `auto` and fail to constrain the flex main col (the
        # "body not scrollable" bug). Keep both the height:100% and the measured
        # cap pinned so a regression that drops the cap is caught.
        self.assertIn("height: 100% !important", canvas_css)
        self.assertIn("--rmc-tenant-main-h", canvas_css)
        self.assertIn("overflow-y: auto !important", canvas_css)
