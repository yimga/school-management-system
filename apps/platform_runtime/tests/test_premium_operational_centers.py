from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class PremiumOperationalCenterTests(SimpleTestCase):
    def test_operational_centers_have_page_header_and_next_action_language(self):
        centers = {
            "templates/finance/dashboard.html": "Money Center",
            "templates/finance/payment_readiness_dashboard.html": "Payment Readiness Center",
            "templates/analytics/dashboard.html": "Insights Center",
            "templates/analytics/governed_report_builder.html": "Insights Center",
            "templates/portal/offline_sync_queue.html": "Offline Sync Center",
            "templates/portal/offline_sync_conflicts.html": "Offline Sync Center",
        }

        for rel_path, label in centers.items():
            with self.subTest(rel_path=rel_path):
                body = (ROOT / rel_path).read_text(encoding="utf-8")
                self.assertIn(label, body)
                self.assertIn("rmc_os_page_header.html", body)
                self.assertRegex(body, r"btn|dashboard_empty_state|next_action")

    def test_payment_readiness_preserves_external_blocker_truth(self):
        body = (ROOT / "templates" / "finance" / "payment_readiness_dashboard.html").read_text(
            encoding="utf-8"
        )
        lowered = body.lower()
        self.assertIn("missing", lowered)
        self.assertIn("manual", lowered)
        self.assertNotIn("psp is live", lowered)
        self.assertNotIn("fully live payments", lowered)
