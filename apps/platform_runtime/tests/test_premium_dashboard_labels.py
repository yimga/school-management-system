from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class PremiumDashboardLabelTests(SimpleTestCase):
    def test_role_dashboard_labels_are_operational_not_passive(self):
        expectations = {
            "templates/accounts/backend_dashboard.html": "Admin Home",
            "templates/parent/dashboard.html": "Family Home",
            # Money twin masthead title is Finance; sidebar still says Money Center.
            "templates/finance/dashboard.html": "Finance",
            "templates/analytics/dashboard.html": "Insights Center",
        }

        for rel_path, label in expectations.items():
            with self.subTest(label=label):
                body = (ROOT / rel_path).read_text(encoding="utf-8")
                self.assertIn(label, body)

    def test_fallback_navigation_uses_premium_labels(self):
        builder = (ROOT / "apps" / "siteconfig" / "portal_sidebar_items.py").read_text(
            encoding="utf-8"
        )
        for label in (
            "Family Home",
            "Money Center",
            "Admin Home",
            "Workflow Center",
        ):
            with self.subTest(label=label):
                self.assertIn(label, builder)
        self.assertIn("Workspace", builder)
