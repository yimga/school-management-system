"""Phase 3C — organization FX rollup tests."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.finance.org_fx_rollup import (
    SchoolCurrencyBalance,
    _invoice_currency_code,
    consolidated_org_balances,
)


class InvoiceCurrencyCodeTests(SimpleTestCase):
    def test_prefers_currency_fk_code(self):
        invoice = SimpleNamespace(
            currency=SimpleNamespace(code="XAF", pk="XAF"),
            profile=SimpleNamespace(currency_code="USD"),
        )
        self.assertEqual(_invoice_currency_code(invoice), "XAF")

    def test_falls_back_to_profile_currency_code(self):
        invoice = SimpleNamespace(currency=None, profile=SimpleNamespace(currency_code="eur"))
        self.assertEqual(_invoice_currency_code(invoice), "EUR")


class ConsolidatedOrgBalancesTests(SimpleTestCase):
    def test_empty_when_organization_missing_pk(self):
        self.assertEqual(consolidated_org_balances(None), [])
        self.assertEqual(consolidated_org_balances(SimpleNamespace(pk=None)), [])

    @patch("apps.finance.models.Invoice")
    @patch("apps.schools.models.School")
    def test_aggregates_open_balances_per_school_currency(self, mock_school, mock_invoice):
        org = SimpleNamespace(pk="org-1")
        school_a = SimpleNamespace(pk="school-a", name="Alpha")
        school_b = SimpleNamespace(pk="school-b", name="Beta")
        mock_school.objects.filter.return_value.only.return_value = [school_a, school_b]

        inv_a = SimpleNamespace(
            school_id="school-a",
            balance_amount=Decimal("100.00"),
            currency=SimpleNamespace(code="USD", pk="USD"),
            profile=None,
        )
        inv_b = SimpleNamespace(
            school_id="school-b",
            balance_amount=Decimal("50.25"),
            currency=None,
            profile=SimpleNamespace(currency_code="XAF"),
        )
        mock_invoice.objects.filter.return_value.select_related.return_value = [inv_a, inv_b]

        rows = consolidated_org_balances(org)
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            rows[0],
            SchoolCurrencyBalance(
                school_id="school-a",
                school_name="Alpha",
                currency_code="USD",
                open_balance=Decimal("100.00"),
                open_invoice_count=1,
            ),
        )
        self.assertEqual(rows[1].currency_code, "XAF")
        self.assertEqual(rows[1].open_balance, Decimal("50.25"))

    @patch("apps.finance.models.Invoice")
    @patch("apps.schools.models.School")
    def test_skips_zero_balance_invoices(self, mock_school, mock_invoice):
        org = SimpleNamespace(pk="org-2")
        school = SimpleNamespace(pk="school-z", name="Zeta")
        mock_school.objects.filter.return_value.only.return_value = [school]
        inv = SimpleNamespace(
            school_id="school-z",
            balance_amount=Decimal("0"),
            currency=SimpleNamespace(code="USD", pk="USD"),
            profile=None,
        )
        mock_invoice.objects.filter.return_value.select_related.return_value = [inv]

        self.assertEqual(consolidated_org_balances(org), [])
