# -*- coding: utf-8 -*-
"""
Next-realm Launch readiness cockpit tests (v3.54.0, 2026-05-21).

Owns: Agent 5 (Launch). Covers:
- Launch page renders for operator + tenant
- Readiness panels render (or empty-state when context absent)
- Role-preview pane honors launch_role_previews (empty state when absent)
- "Apply" buttons require confirmation pattern (data-rmc-confirm)
- Operator-only items hidden on tenant host
- No float() literals on rendered money values
"""

from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import Permission

User = get_user_model()


def _render(template_path: str, ctx: dict) -> str:
    """Render a partial in isolation using {% include %}."""
    tpl = Template("{% load i18n %}{% include '" + template_path + "' %}")
    return tpl.render(Context(ctx))


class LaunchOverviewBodyPartialTests(SimpleTestCase):
    """launch_studio_overview_body.html must not require step.title (payload uses label only)."""

    PARTIAL = "studio_os/partials/launch_studio_overview_body.html"

    def test_checklist_renders_steps_with_label_only(self):
        """Regression: default:step.title always resolves and raised VariableDoesNotExist."""
        html = _render(
            self.PARTIAL,
            {
                "launch_payload": {
                    "health_score": 42,
                    "launch_ready": False,
                    "launch_blockers": ["staff"],
                    "steps": [
                        {
                            "key": "institution_basics",
                            "order": 1,
                            "label": "Create school profile",
                            "description": "Confirm institution identity.",
                            "done": True,
                            "status": "Ready",
                            "group": "foundation",
                            "link": "/authentication/backend/",
                            "recommended_choice": "Verify legal name.",
                            "evidence": "Institution identity is set.",
                        }
                    ],
                },
                "launch_role_previews": [],
            },
        )
        self.assertIn("Create school profile", html)
        self.assertNotIn("step.title", html)


class LaunchReadinessPreviewPanePartialTests(SimpleTestCase):
    """launch_readiness_preview_pane.html honors launch_role_previews + empty state."""

    PARTIAL = "studio_os/partials/launch_readiness_preview_pane.html"

    def test_empty_role_previews_renders_honest_empty_state(self):
        html = _render(self.PARTIAL, {"launch_role_previews": []})
        self.assertIn("rmc-launch-empty", html)
        self.assertIn("Role previews coming online", html)

    def test_role_previews_render_card_grid(self):
        html = _render(
            self.PARTIAL,
            {
                "launch_role_previews": [
                    {"role": "admin", "label": "Admin", "url": "/portal/admin/", "detail": "Day-1 admin view."},
                    {"role": "teacher", "label": "Teacher", "url": "/portal/teacher/", "detail": "Class flow."},
                ]
            },
        )
        self.assertIn("rmc-launch-role-grid", html)
        self.assertIn("rmc-launch-role-card", html)
        self.assertIn("Admin", html)
        self.assertIn("Teacher", html)
        self.assertIn('target="_blank"', html)
        self.assertIn('rel="noopener noreferrer"', html)


class LaunchSelectPlanBodyPartialTests(SimpleTestCase):
    """launch_select_plan_body.html honest empty state + no float money."""

    PARTIAL = "studio_os/partials/launch_select_plan_body.html"

    def test_renders_coming_soon_state(self):
        html = _render(self.PARTIAL, {})
        self.assertIn("Coming soon", html)
        self.assertIn("rmc-launch-plan-card", html)

    def test_no_floating_money_literal_rendered(self):
        """Guard: no $NN.NN-style float literals shipped in placeholder."""
        html = _render(self.PARTIAL, {})
        # Catch $1.23, USD 1.23, etc. — none should appear before plans ship.
        self.assertNotRegex(html, r"\$\s*\d+\.\d{2}")
        self.assertNotRegex(html, r"\bUSD\s+\d+\.\d{2}")
        self.assertNotRegex(html, r"\bfloat\(")


class LaunchSchoolInfrastructureBodyPartialTests(SimpleTestCase):
    """launch_school_infrastructure_body.html confirm pattern + operator gating."""

    PARTIAL = "studio_os/partials/launch_school_infrastructure_body.html"

    def setUp(self):
        self.tenant_request = RequestFactory().get("/studio/launch/?pane=infrastructure")
        self.tenant_request.public_host_kind = "tenant"
        self.operator_request = RequestFactory().get("/studio/launch/?pane=infrastructure")
        self.operator_request.public_host_kind = "manager"
        self.base_ctx = {
            "school_template_summaries": [
                {"template_key": "private_school", "display_name": "Private", "school_type": "K-12", "version": "1.0"}
            ],
            "platform_catalog_valid": True,
            "current_blueprint_reference": None,
        }

    def test_tenant_does_not_see_request_apply_button(self):
        ctx = dict(self.base_ctx, request=self.tenant_request)
        html = _render(self.PARTIAL, ctx)
        self.assertNotIn('id="studio-infra-request-apply"', html)
        # Honest tenant fallback string is present
        self.assertIn("Share the preview with your platform administrator", html)

    def test_operator_sees_request_apply_with_confirm_data_attr(self):
        ctx = dict(self.base_ctx, request=self.operator_request)
        html = _render(self.PARTIAL, ctx)
        self.assertIn('id="studio-infra-request-apply"', html)
        # Confirmation pattern: must show what it's about to do
        self.assertIn("data-rmc-confirm", html)
        # Operator badge present
        self.assertIn("Operator", html)

    def test_preview_button_and_js_hooks_preserved(self):
        ctx = dict(self.base_ctx, request=self.tenant_request)
        html = _render(self.PARTIAL, ctx)
        # JS file consumes these IDs — must not regress
        for marker in (
            'id="studio-infra-template"',
            'id="studio-infra-preview-btn"',
            'id="studio-infra-status"',
            'id="studio-infra-result"',
            'id="studio-infra-summary"',
            'id="studio-infra-diff"',
            'id="studio-infra-rollback-note"',
            'id="studio-infra-apply-note"',
            'id="page-data-studio_os__partials__launch_school_infrastructure_body-1"',
        ):
            self.assertIn(marker, html, f"missing JS hook: {marker}")


class LaunchRailWorkspacePartialTests(SimpleTestCase):
    """workspace/launch_rail.html renders icons + aria-current."""

    PARTIAL = "studio_os/partials/workspace/launch_rail.html"

    def test_active_rail_link_carries_aria_current(self):
        html = _render(
            self.PARTIAL,
            {
                "launch_left_rail": [
                    {"label": "Overview", "url": "/studio/launch/?pane=overview", "pane": "overview"},
                    {"label": "Plan", "url": "/studio/launch/?pane=plan", "pane": "plan"},
                ],
                "launch_pane": "overview",
                "launch_payload": None,
            },
        )
        self.assertIn('aria-current="page"', html)
        self.assertIn("rmc-launch-rail-link", html)
        # Both pane icons should land
        self.assertIn("bi-grid-1x2", html)  # overview
        self.assertIn("bi-tag", html)  # plan


class LaunchWorkspaceCanvasPartialTests(SimpleTestCase):
    """workspace/launch_canvas.html dispatches panes correctly + min-width safety."""

    PARTIAL = "studio_os/partials/workspace/launch_canvas.html"

    def test_overview_empty_renders_empty_card(self):
        html = _render(
            self.PARTIAL,
            {"launch_pane": "overview", "launch_payload": None, "launch_studio_base_url": "/studio/launch/"},
        )
        self.assertIn("rmc-launch-canvas", html)
        self.assertIn("rmc-launch-empty", html)

    def test_plan_pane_includes_plan_body(self):
        html = _render(
            self.PARTIAL,
            {"launch_pane": "plan"},
        )
        self.assertIn("rmc-launch-plan-card", html)


class LaunchModeFullPageRenderTests(TestCase):
    """End-to-end: GET /studio/launch/ returns 200 for staff (operator + tenant hosts)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="launch-cockpit-user",
            email="launch-cockpit@example.com",
            password="password",
            role=User.Role.IT_ADMIN,
        )
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        self.user.feature_permissions.add(manage_perm)
        self.client.force_login(self.user)

    def test_launch_page_returns_200(self):
        response = self.client.get(reverse("studio_os:launch"))
        self.assertEqual(response.status_code, 200)

    def test_launch_links_new_cockpit_css(self):
        response = self.client.get(reverse("studio_os:launch"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "studio-launch-cockpit.css")

    def test_launch_role_preview_pane_renders(self):
        response = self.client.get(reverse("studio_os:launch") + "?pane=role_preview")
        self.assertEqual(response.status_code, 200)

    def test_launch_infrastructure_pane_renders(self):
        response = self.client.get(reverse("studio_os:launch") + "?pane=infrastructure")
        self.assertEqual(response.status_code, 200)
        # JS hooks preserved at full-page render
        self.assertContains(response, 'id="studio-infra-template"')

    def test_launch_plan_pane_renders(self):
        response = self.client.get(reverse("studio_os:launch") + "?pane=plan")
        self.assertEqual(response.status_code, 200)


class LaunchScannerHygieneTests(SimpleTestCase):
    """Defensive scanners over our partials — should be clean per CLAUDE.md gates."""

    PARTIALS = [
        "studio_os/partials/launch_readiness_preview_pane.html",
        "studio_os/partials/launch_school_infrastructure_body.html",
        "studio_os/partials/launch_select_plan_body.html",
        "studio_os/partials/workspace/launch_rail.html",
        "studio_os/partials/workspace/launch_canvas.html",
    ]

    def _read_template_source(self, path: str) -> str:
        from django.template.loader import get_template

        return get_template(path).template.source

    def test_partials_have_no_inline_hex_or_rgb_colors(self):
        # scan_inline_style_off_token gate
        rx_hex = re.compile(r'style="[^"]*#[0-9a-fA-F]{3,8}\b')
        rx_rgb = re.compile(r'style="[^"]*rgb[a]?\(')
        for path in self.PARTIALS:
            src = self._read_template_source(path)
            self.assertIsNone(rx_hex.search(src), f"inline hex in {path}")
            self.assertIsNone(rx_rgb.search(src), f"inline rgb in {path}")

    def test_partials_have_no_float_money_literals(self):
        # scan_money_float gate (template-side)
        rx_money = re.compile(r'\bfloat\(|\bUSD\s+\d+\.\d{2}\b')
        for path in self.PARTIALS:
            src = self._read_template_source(path)
            self.assertIsNone(rx_money.search(src), f"float money in {path}")

    def test_partials_use_trans_or_blocktrans(self):
        # i18n hygiene — every user-visible string should pass through trans
        for path in self.PARTIALS:
            src = self._read_template_source(path)
            self.assertIn("{% trans", src, f"no {{% trans %}} in {path}")
