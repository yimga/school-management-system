"""Control-plane copilot rail must render as grid column 3 chrome, not a bottom band."""

from __future__ import annotations

import os
import re
from pathlib import Path
from unittest import mock

from django.test import Client, SimpleTestCase, TestCase, override_settings

from apps.accounts.models import User, UserPasskey
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig
from apps.schools.tests.manager_client import login_manager_control_plane

REPO_ROOT = Path(__file__).resolve().parents[3]

# Representative manager routes — all must share control_plane_skeleton chrome
# (copilot rail is mounted in the skeleton, not per-page).
MANAGER_COPILOT_SHELL_ROUTE_SAMPLES = (
    ("/super/", "command-center landing (was visually broken)"),
    ("/super/schools/", "schools list"),
    ("/help-center/", "help center (user reference — correct layout)"),
    ("/super/team/", "operator team roster"),
    ("/super/compliance/", "compliance overview"),
)


def assert_manager_copilot_shell_contract(test_case, html: str, path: str) -> None:
    """HTML contract shared by every control_plane_base page on manager host."""
    test_case.assertIn(
        'data-rmc-isomorphic-template="operator-control-plane"',
        html,
        f"{path}: missing operator isomorphic template on <html>",
    )
    test_case.assertIn(
        'data-rmc-app-shell-copilot="1"',
        html,
        f"{path}: copilot shell flag missing on .rmc-app-shell",
    )
    test_case.assertIn(
        'class="rmc-app-shell__copilot"',
        html,
        f"{path}: copilot rail aside missing",
    )
    test_case.assertIn(
        "data-rmc-copilot-rail",
        html,
        f"{path}: copilot rail marker missing",
    )
    test_case.assertIn(
        "rmc-cp-copilot-grid-lock.css",
        html,
        f"{path}: terminal copilot grid-lock stylesheet not loaded",
    )
    test_case.assertIn(
        'id="rmc-cp-copilot-grid-critical"',
        html,
        f"{path}: inline copilot grid critical style missing (stale CSS cache defense)",
    )
    copilot_idx = html.find('class="rmc-app-shell__copilot"')
    pulse_idx = html.find('id="rmcCpPulseDrillSheet"')
    footer_idx = html.find('class="rmc-app-shell__footer')
    test_case.assertGreater(copilot_idx, 0, f"{path}: copilot aside not in DOM")
    test_case.assertGreater(pulse_idx, 0, f"{path}: pulse sheet not in DOM")
    test_case.assertGreater(footer_idx, 0, f"{path}: shell footer not in DOM")
    test_case.assertLess(
        copilot_idx,
        pulse_idx,
        f"{path}: copilot must precede pulse drill sheet inside .rmc-app-shell",
    )
    test_case.assertLess(
        copilot_idx,
        footer_idx,
        f"{path}: copilot must precede footer inside .rmc-app-shell",
    )


class ControlPlaneCopilotRailCssContractTests(SimpleTestCase):
    def test_copilot_grid_css_contract_present_in_tree(self):
        css_shell = (REPO_ROOT / "static" / "css" / "rmc-app-shell.css").read_text(
            encoding="utf-8", errors="replace"
        )
        css_200x = (REPO_ROOT / "static" / "css" / "rmc-cp-200x.css").read_text(
            encoding="utf-8", errors="replace"
        )
        css_iso = (REPO_ROOT / "static" / "css" / "rmc-isomorphic-grid.css").read_text(
            encoding="utf-8", errors="replace"
        )
        skeleton = (
            REPO_ROOT / "templates" / "control_plane_skeleton.html"
        ).read_text(encoding="utf-8", errors="replace")

        self.assertIn('.rmc-app-shell[data-rmc-app-shell-copilot="1"]', css_shell)
        self.assertIn("grid-column: 3", css_shell)
        self.assertIn('[data-rmc-shell-main="control-plane"] .rmc-app-shell__copilot', css_200x)
        self.assertIn("grid-column: 3", css_200x)
        self.assertIn("max-width: var(--rmc-app-shell-copilot-w, 44px)", css_200x)
        self.assertIn(
            '[data-rmc-isomorphic-template="operator-control-plane"] .rmc-app-shell[data-rmc-app-shell-copilot="1"] > .rmc-app-shell__copilot',
            css_iso,
        )
        self.assertRegex(
            css_iso,
            r'\[data-rmc-isomorphic-template="operator-control-plane"\] \.rmc-app-shell\[data-rmc-app-shell-copilot="1"\] > \.rmc-app-shell__copilot\s*\{[^}]*grid-area:\s*rmc-shell-cp[^}]*grid-row:\s*2[^}]*grid-column:\s*3',
            re.DOTALL,
        )
        grid_lock = (
            REPO_ROOT / "static" / "css" / "rmc-cp-copilot-grid-lock.css"
        ).read_text(encoding="utf-8", errors="replace")
        self.assertIn("grid-area: rmc-shell-cp", grid_lock)
        copilot_idx = skeleton.find("_ai_copilot_rail.html")
        pulse_idx = skeleton.find("_pulse_drill_sheet.html")
        self.assertGreater(copilot_idx, 0)
        self.assertGreater(pulse_idx, 0)
        self.assertLess(copilot_idx, pulse_idx)


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "manager.runmycampus.com"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SECURE_SSL_REDIRECT=False,
    ROOT_URLCONF="config.manager_urls",
)
class ControlPlaneCopilotRailLayoutTests(TestCase):
    def setUp(self):
        self.password = "Test1234"
        self.user = User.objects.create_user(
            username="copilot-rail-qa",
            email="copilot-rail-qa@test.runmycampus.com",
            password=self.password,
            role=User.Role.SUPERADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client(HTTP_HOST="manager.runmycampus.com")
        UserPasskey.objects.create(
            user=self.user,
            name="Copilot rail test passkey",
            credential_id="copilot-rail-test-passkey",
            public_key="test-public-key",
        )
        login_manager_control_plane(self.client, self.user, password=self.password)

    @mock.patch.dict(os.environ, {"CONTROL_PLANE_OPERATOR_ROLES": "SUPERADMIN"})
    def test_manager_routes_share_identical_copilot_shell_contract(self):
        """Copilot mounts in control_plane_skeleton — not duplicated per route."""
        for path, label in MANAGER_COPILOT_SHELL_ROUTE_SAMPLES:
            with self.subTest(path=path, label=label):
                response = self.client.get(path, follow=False)
                self.assertEqual(
                    response.status_code,
                    200,
                    f"{path} ({label}): {response.content[:300]!r}",
                )
                html = response.content.decode("utf-8", errors="replace")
                assert_manager_copilot_shell_contract(self, html, path)

    @mock.patch.dict(os.environ, {"CONTROL_PLANE_OPERATOR_ROLES": "SUPERADMIN"})
    def test_super_dashboard_landing_is_only_page_with_200x_cockpit_band(self):
        """Landing embeds 200x sections inside canvas — copilot mount stays in skeleton."""
        response = self.client.get("/super/", follow=False)
        self.assertEqual(response.status_code, 200, response.content[:500])
        html = response.content.decode("utf-8", errors="replace")
        self.assertEqual(html.count('class="rmc-app-shell__copilot"'), 1)
        self.assertIn('data-rmc-cp-200x-landing="1"', html)

    @mock.patch.dict(os.environ, {"CONTROL_PLANE_OPERATOR_ROLES": "SUPERADMIN"})
    def test_help_center_uses_same_shell_as_super_not_portal_bridge(self):
        response = self.client.get("/help-center/", follow=False)
        self.assertEqual(response.status_code, 200, response.content[:500])
        html = response.content.decode("utf-8", errors="replace")
        assert_manager_copilot_shell_contract(self, html, "/help-center/")
        self.assertNotIn("manager-portal-bridge", html)
        self.assertNotIn("rmc-manager-portal-copilot-mount", html)
        self.assertNotIn('data-rmc-cp-200x-landing="1"', html)

    @mock.patch.dict(os.environ, {"CONTROL_PLANE_OPERATOR_ROLES": "SUPERADMIN"})
    def test_super_schools_list_pins_copilot_shell_contract(self):
        response = self.client.get("/super/schools/", follow=False)
        self.assertEqual(response.status_code, 200, response.content[:500])
        html = response.content.decode("utf-8", errors="replace")
        assert_manager_copilot_shell_contract(self, html, "/super/schools/")
        self.assertIn('data-rmc-portal-row-detail-dismiss', html)
        self.assertIn("rmc-portal-row-detail-drawer.js", html)

    @mock.patch.dict(os.environ, {"CONTROL_PLANE_OPERATOR_ROLES": "SUPERADMIN"})
    def test_super_dashboard_emits_fleet_lens_contract(self):
        region = RegionConfig.get_default()
        School.objects.create(
            name="Fleet Lens School",
            slug="fleet-lens-school",
            subdomain="fleet-lens-school",
            is_active=True,
            is_approved=False,
            default_region=region,
        )
        response = self.client.get("/super/", follow=False)
        self.assertEqual(response.status_code, 200, response.content[:500])
        html = response.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-copilot-page-lens="operator-dashboard-fleet"', html)
        self.assertIn("data-rmc-row-lens-api", html)
        self.assertIn("data-rmc-row-requeue-api", html)
        self.assertIn("data-rmc-row-detail-cards", html)

    @mock.patch.dict(os.environ, {"CONTROL_PLANE_OPERATOR_ROLES": "SUPERADMIN"})
    def test_super_operator_team_roster_drawer_contract(self):
        response = self.client.get("/super/team/", follow=False)
        self.assertEqual(response.status_code, 200, response.content[:500])
        html = response.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-row-detail-table="1"', html)
        self.assertIn('data-rmc-row-lens-api', html)
        self.assertIn('data-rmc-portal-row-detail-dismiss', html)
        self.assertNotIn('include "partials/portal_row_detail_drawer_bundle.html"', html)
