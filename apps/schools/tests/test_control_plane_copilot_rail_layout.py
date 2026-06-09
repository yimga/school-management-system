"""Control-plane copilot rail must render as grid column 3 chrome, not a bottom band."""

from __future__ import annotations

import os
import re
from pathlib import Path
from unittest import mock

from django.test import Client, SimpleTestCase, TestCase, override_settings

from apps.accounts.models import User

REPO_ROOT = Path(__file__).resolve().parents[3]


class ControlPlaneCopilotRailCssContractTests(SimpleTestCase):
    def test_copilot_grid_css_contract_present_in_tree(self):
        css_200x = (REPO_ROOT / "static" / "css" / "rmc-cp-200x.css").read_text(
            encoding="utf-8", errors="replace"
        )
        css_iso = (REPO_ROOT / "static" / "css" / "rmc-isomorphic-grid.css").read_text(
            encoding="utf-8", errors="replace"
        )
        skeleton = (
            REPO_ROOT / "templates" / "control_plane_skeleton.html"
        ).read_text(encoding="utf-8", errors="replace")

        self.assertIn('[data-rmc-shell-main="control-plane"] .rmc-app-shell__copilot', css_200x)
        self.assertIn("grid-column: 3", css_200x)
        self.assertIn("max-width: var(--rmc-app-shell-copilot-w, 44px)", css_200x)
        self.assertIn(
            '[data-rmc-isomorphic-template="operator-control-plane"] .rmc-app-shell__copilot',
            css_iso,
        )
        self.assertRegex(
            css_iso,
            r'\[data-rmc-isomorphic-template="operator-control-plane"\] \.rmc-app-shell__copilot\s*\{[^}]*grid-row:\s*2[^}]*grid-column:\s*3',
            re.DOTALL,
        )
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
        self.user = User.objects.create_user(
            username="copilot-rail-qa",
            email="copilot-rail-qa@test.runmycampus.com",
            password="unused",
            role=User.Role.SUPERADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])
        self.client = Client(HTTP_HOST="manager.runmycampus.com")

    @mock.patch.dict(os.environ, {"CONTROL_PLANE_OPERATOR_ROLES": "SUPERADMIN"})
    def test_super_dashboard_html_mounts_copilot_before_pulse_sheet(self):
        self.client.force_login(self.user)
        response = self.client.get("/super/", follow=False)
        self.assertEqual(response.status_code, 200, response.content[:500])
        html = response.content.decode("utf-8", errors="replace")

        self.assertIn('class="rmc-app-shell__copilot"', html)
        self.assertIn("data-rmc-copilot-rail", html)
        self.assertIn('data-rmc-shell-main="control-plane"', html)
        self.assertIn('data-rmc-isomorphic-template="operator-control-plane"', html)
        self.assertIn("rmc-cp-200x.css", html)

        copilot_idx = html.find('class="rmc-app-shell__copilot"')
        pulse_idx = html.find('id="rmcCpPulseDrillSheet"')
        self.assertGreater(copilot_idx, 0)
        self.assertGreater(pulse_idx, 0)
        self.assertLess(
            copilot_idx,
            pulse_idx,
            "copilot rail must precede pulse drill sheet inside .rmc-app-shell",
        )

        shell_open = html.find('class="rmc-app-shell"')
        footer_idx = html.find('class="rmc-app-shell__footer')
        self.assertGreater(shell_open, 0)
        self.assertGreater(footer_idx, 0)
        self.assertLess(copilot_idx, footer_idx)
        self.assertLess(pulse_idx, footer_idx)
