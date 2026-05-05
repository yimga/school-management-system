from __future__ import annotations

import re
from pathlib import Path

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User


ROOT = Path(__file__).resolve().parents[3]
_MGR_HOST = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _MGR_HOST],
    ROOT_URLCONF="config.urls",
)
class ManagerPremiumDensityTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST=_MGR_HOST, raise_request_exception=False)
        User.objects.create_user(
            username="manager_density_super",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.client.login(username="manager_density_super", password="x" * 8)

    def test_super_dashboard_uses_progressive_disclosure_for_dense_board(self):
        response = self.client.get(reverse("super:dashboard"))
        self.assertEqual(response.status_code, 200, msg=response.content[:500])

        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("data-rmc-premium-shell=", body)
        self.assertIn("data-rmc-primary-action-slot", body)
        self.assertIn('data-rmc-manager-progressive-disclosure="1"', body)
        self.assertIn("Open detailed operating board", body)

        dashboard = body.split('id="super-dashboard-main"', 1)[1]
        above_fold = dashboard.split('data-rmc-manager-progressive-disclosure="1"', 1)[0]
        self.assertLess(
            above_fold.count("<a "),
            60,
            msg="Manager above-fold link count should stay command-center sized.",
        )
        self.assertLess(
            above_fold.count("<button "),
            40,
            msg="Manager above-fold button count should stay command-center sized.",
        )
        panel_count = len(
            re.findall(r'class="[^"]*(?:\bcard\b|cp-(?:panel|overview-card|health-card))', above_fold)
        )
        self.assertLess(
            panel_count,
            35,
            msg="Manager above-fold panel/card count should remain reduced.",
        )

    def test_control_plane_sidebar_collapses_secondary_groups_by_default(self):
        response = self.client.get(reverse("super:dashboard"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")

        self.assertLessEqual(
            body.count("collapse show"),
            2,
            msg="Only the first control-plane navigation group per shell mount should be expanded.",
        )
        self.assertIn("Billing", body)
        self.assertIn("Marketplace", body)
        self.assertIn("Migration", body)

    def test_inter_css_does_not_reference_broken_local_font_files(self):
        css = (ROOT / "static" / "css" / "vendor" / "inter.css").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("@font-face", css)
        self.assertNotIn(".woff2", css)
        self.assertIn("--rmc-font-sans", css)
