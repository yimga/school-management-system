"""Operator + beat wiring for holding currency rollups (B4 follow-up)."""
from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase
from django.urls import reverse

ROOT = Path(__file__).resolve().parents[3]


class HoldingRollupOperatorWiringTests(SimpleTestCase):
    def test_super_url_resolves(self):
        url = reverse("super:holding_currency_rollup_dashboard")
        self.assertIn("holding-currency-rollups", url)

    def test_operator_template_exists(self):
        tpl = ROOT / "templates/schools/holding_currency_rollup_dashboard.html"
        self.assertTrue(tpl.is_file())
        text = tpl.read_text(encoding="utf-8")
        self.assertIn("currency_buckets", text)
        self.assertIn("rmc-data-table", text)

    def test_billing_dashboard_links_rollups(self):
        billing = (ROOT / "templates/schools/billing_dashboard.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("holding_currency_rollup_dashboard", billing)

    def test_beat_schedule_has_daily_entry(self):
        beat = (ROOT / "apps/billing/beat_schedule.py").read_text(encoding="utf-8")
        self.assertIn("holding-currency-rollup-daily", beat)
        self.assertIn("apps.billing.materialize_holding_currency_rollups", beat)

    def test_materialize_all_helper_present(self):
        body = (ROOT / "apps/billing/holding_rollup.py").read_text(encoding="utf-8")
        self.assertIn("def materialize_all_holding_currency_rollups", body)
