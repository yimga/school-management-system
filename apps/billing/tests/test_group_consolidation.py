"""Phase 4C — group billing consolidation tests."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.billing.group_consolidation import (
    build_consolidated_ar_report,
    resolve_org_billing_mode,
)
from apps.finance.org_fx_rollup import SchoolCurrencyBalance


class OrgBillingModeTests(SimpleTestCase):
    @patch("apps.schools.models.School")
    def test_reads_mode_from_member_school_settings(self, mock_school):
        org = SimpleNamespace(pk="org-1")
        school = SimpleNamespace(
            settings={"org_billing": {"billing_mode": "consolidated"}},
        )
        mock_school.objects.filter.return_value.only.return_value = [school]
        self.assertEqual(resolve_org_billing_mode(org), "consolidated")

    def test_defaults_to_per_school(self):
        self.assertEqual(resolve_org_billing_mode(None), "per_school")


class ConsolidatedARReportTests(SimpleTestCase):
    @patch("apps.billing.group_consolidation.consolidated_org_balances")
    @patch("apps.billing.group_consolidation.resolve_org_billing_mode", return_value="hybrid")
    def test_builds_exposure_totals(self, _mode, mock_rollup):
        org = SimpleNamespace(pk="org-9")
        mock_rollup.return_value = [
            SchoolCurrencyBalance(
                school_id="a",
                school_name="A",
                currency_code="USD",
                open_balance=Decimal("10.00"),
                open_invoice_count=1,
            ),
            SchoolCurrencyBalance(
                school_id="b",
                school_name="B",
                currency_code="USD",
                open_balance=Decimal("5.00"),
                open_invoice_count=2,
            ),
        ]
        report = build_consolidated_ar_report(org)
        self.assertEqual(report.billing_mode, "hybrid")
        self.assertEqual(report.total_open_invoices, 3)
        self.assertEqual(report.currency_exposure["USD"], Decimal("15.00"))
