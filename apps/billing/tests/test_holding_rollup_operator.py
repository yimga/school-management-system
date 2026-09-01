"""Operator + beat wiring for holding currency rollups (B4 follow-up)."""
from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase
from django.urls import reverse

from apps.siteconfig.tests._template_nodes import assert_markup, assert_wires

ROOT = Path(__file__).resolve().parents[3]

ROLLUP_TPL = ROOT / "templates/schools/holding_currency_rollup_dashboard.html"
BILLING_DASHBOARD = ROOT / "templates/schools/billing_dashboard.html"


class HoldingRollupOperatorWiringTests(SimpleTestCase):
    def test_super_url_resolves(self):
        url = reverse("super:holding_currency_rollup_dashboard")
        self.assertIn("holding-currency-rollups", url)

    def test_operator_template_exists(self):
        tpl = ROOT / "templates/schools/holding_currency_rollup_dashboard.html"
        self.assertTrue(tpl.is_file())
        text = tpl.read_text(encoding="utf-8")
        # currency_buckets is the context VARIABLE the page loops over: template
        # code, which only a source read can see.
        self.assertIn("currency_buckets", text)
        # The table class is emitted markup, and the page must still be a live
        # operator page -- extending the control plane, wiring its empty state.
        assert_markup(self, ROLLUP_TPL, "rmc-data-table")
        assert_wires(
            self,
            ROLLUP_TPL,
            "control_plane_base.html",
            "components/rmc_empty_state.html",
        )

    def test_billing_dashboard_links_rollups(self):
        billing = (ROOT / "templates/schools/billing_dashboard.html").read_text(
            encoding="utf-8"
        )
        # The link is <a href="{% url 'super:holding_currency_rollup_dashboard' %}">
        # carrying a {% trans %} label, so the route NAME is a tag argument and
        # the label is translation output. Neither a parse nor a render of this
        # file (it extends control_plane_base and needs SITE) can see the link,
        # so this half stays a source read. The anchor has no stable hook of its
        # own; a data-* marker on it would make this assertion real.
        self.assertIn("holding_currency_rollup_dashboard", billing)
        # What the ENGINE can confirm: the billing dashboard is still a live
        # operator page that extends the control plane and wires its masthead,
        # and it still emits its data table.
        assert_wires(
            self,
            BILLING_DASHBOARD,
            "control_plane_base.html",
            "rmc_page_masthead.html",
        )
        assert_markup(self, BILLING_DASHBOARD, "rmc-data-table")

    def test_beat_schedule_has_daily_entry(self):
        beat = (ROOT / "apps/billing/beat_schedule.py").read_text(encoding="utf-8")
        self.assertIn("holding-currency-rollup-daily", beat)
        self.assertIn("apps.billing.materialize_holding_currency_rollups", beat)

    def test_materialize_all_helper_present(self):
        body = (ROOT / "apps/billing/holding_rollup.py").read_text(encoding="utf-8")
        self.assertIn("def materialize_all_holding_currency_rollups", body)
