"""Payroll monetary paths must stay Decimal end-to-end (no float drift)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.finance.models import ComplianceProfile, ContributionRule, TaxBracket
from apps.payroll.models import PayrollEmployee
from apps.payroll.services import calculate_contributions, calculate_payroll, calculate_tax

User = get_user_model()


class PayrollDecimalIntegrityTests(TestCase):
    def setUp(self):
        self.profile = ComplianceProfile.objects.create(
            name="Payroll Decimal Profile",
            country_code="CM",
            currency_code="XAF",
            min_wage=Decimal("60000.00"),
            default_hours_per_week=Decimal("40.00"),
            overtime_multiplier=Decimal("1.50"),
            is_active=True,
        )
        TaxBracket.objects.create(
            profile=self.profile,
            lower_bound=Decimal("0.00"),
            upper_bound=Decimal("200000.00"),
            rate=Decimal("0.10"),
        )
        TaxBracket.objects.create(
            profile=self.profile,
            lower_bound=Decimal("200000.00"),
            upper_bound=None,
            rate=Decimal("0.15"),
        )
        ContributionRule.objects.create(
            profile=self.profile,
            code="CNPS",
            name="Social",
            employee_rate=Decimal("0.04"),
            employer_rate=Decimal("0.06"),
        )
        user = User.objects.create_user(
            username="payroll-decimal-user",
            password="Test1234!",
            first_name="Pay",
            last_name="Roll",
        )
        self.employee = PayrollEmployee.objects.create(
            user=user,
            pay_type=PayrollEmployee.PayType.MONTHLY,
            base_salary=Decimal("250000.00"),
            is_active=True,
        )

    def test_calculate_tax_returns_decimal_with_fractional_brackets(self):
        gross = Decimal("250000.00")
        tax = calculate_tax(self.profile, gross)
        self.assertIsInstance(tax, Decimal)
        expected = (Decimal("200000.00") - Decimal("0.00")) * Decimal("0.10") + (
            gross - Decimal("200000.00")
        ) * Decimal("0.15")
        self.assertEqual(tax, expected)

    def test_calculate_contributions_returns_decimal_totals(self):
        gross = Decimal("100000.00")
        _rows, employee_total, employer_total = calculate_contributions(self.profile, gross)
        self.assertIsInstance(employee_total, Decimal)
        self.assertIsInstance(employer_total, Decimal)
        self.assertEqual(employee_total, gross * Decimal("0.04"))
        self.assertEqual(employer_total, gross * Decimal("0.06"))

    def test_calculate_payroll_amounts_are_decimal(self):
        period_start = date(2026, 1, 1)
        period_end = date(2026, 1, 31)
        result = calculate_payroll(
            self.employee, self.profile, period_start, period_end
        )
        for key in (
            "gross_pay",
            "net_pay",
            "tax_amount",
            "employee_contributions",
            "employer_contributions",
            "overtime_pay",
            "total_hours",
        ):
            self.assertIsInstance(result[key], Decimal, msg=key)
        self.assertGreaterEqual(result["gross_pay"], self.profile.min_wage)
