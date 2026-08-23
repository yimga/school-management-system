"""A salaried employee's pay must not depend on whether a timesheet row exists.

``calculate_payroll`` prorated a non-HOURLY employee's base salary against the
full period's standard hours whenever ANY hours were logged:

    base_pay = base_salary * min(total_hours, standard_hours) / standard_hours

There is no "this employee does not track time" concept, so one 8-hour
invigilation entry (enterable straight from ``TimeEntryInline`` on the employee
admin) cut a 500,000 XAF monthly teacher to 23,333 — floored back up to the
compliance profile's min_wage — while the same teacher with no TimeEntry row at
all was paid in full. Salary is salary; deductions belong in SalaryAdjustment
and extra hours still earn overtime.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.finance.models import ComplianceProfile
from apps.payroll.models import PayrollEmployee, TimeEntry
from apps.payroll.services import calculate_payroll

User = get_user_model()

PERIOD_START = date(2026, 6, 1)
PERIOD_END = date(2026, 6, 30)


class MonthlySalaryTimesheetProrationTests(TestCase):
    def setUp(self):
        self.profile = ComplianceProfile.objects.create(
            name="Proration Profile",
            country_code="CM",
            currency_code="XAF",
            min_wage=Decimal("60000.00"),
            default_hours_per_week=Decimal("40.00"),
            overtime_multiplier=Decimal("1.50"),
            is_active=True,
        )
        # No TaxBracket / ContributionRule rows: gross_pay is then base_pay
        # untouched, so the assertions below read the proration directly.
        user = User.objects.create_user(username="proration-teacher", password="pw")
        self.employee = PayrollEmployee.objects.create(
            user=user,
            pay_type=PayrollEmployee.PayType.MONTHLY,
            base_salary=Decimal("500000.00"),
            is_active=True,
        )

    def _calc(self):
        return calculate_payroll(
            self.employee, self.profile, PERIOD_START, PERIOD_END
        )

    def test_full_salary_with_no_time_entries(self):
        # Baseline: the untouched behaviour this must not change.
        self.assertEqual(self._calc()["gross_pay"], Decimal("500000.00"))

    def test_one_invigilation_entry_does_not_cut_the_salary(self):
        TimeEntry.objects.create(
            employee=self.employee,
            entry_date=date(2026, 6, 13),
            hours_worked=Decimal("8.00"),
            notes="Saturday exam invigilation",
        )
        result = self._calc()

        # Anti-vacuous: _sum_hours really saw the row, so the proration branch
        # was genuinely entered rather than skipped on an empty timesheet.
        self.assertEqual(result["total_hours"], Decimal("8.00"))
        self.assertEqual(result["details"]["base_pay"], Decimal("500000.00"))
        self.assertEqual(result["gross_pay"], Decimal("500000.00"))
        # The old behaviour landed exactly on the min_wage floor.
        self.assertNotEqual(result["gross_pay"], self.profile.min_wage)

    def test_partial_month_of_entries_still_pays_full_salary(self):
        for day in range(1, 6):
            TimeEntry.objects.create(
                employee=self.employee,
                entry_date=date(2026, 6, day),
                hours_worked=Decimal("8.00"),
            )
        result = self._calc()
        self.assertEqual(result["total_hours"], Decimal("40.00"))
        self.assertEqual(result["gross_pay"], Decimal("500000.00"))

    def test_hours_above_standard_still_earn_overtime(self):
        # standard_hours for a 30-day period at 40h/week = 40 * 30/7 ≈ 171.43.
        for day in range(1, 25):
            TimeEntry.objects.create(
                employee=self.employee,
                entry_date=date(2026, 6, day),
                hours_worked=Decimal("8.00"),
            )
        result = self._calc()
        self.assertEqual(result["total_hours"], Decimal("192.00"))
        self.assertGreater(result["overtime_pay"], Decimal("0.00"))
        self.assertEqual(result["gross_pay"], Decimal("500000.00") + result["overtime_pay"])

    def test_hourly_employee_is_still_paid_by_the_hour(self):
        # The proration removal must not leak into the HOURLY branch.
        self.employee.pay_type = PayrollEmployee.PayType.HOURLY
        self.employee.hourly_rate = Decimal("2000.00")
        self.employee.save(update_fields=["pay_type", "hourly_rate"])
        TimeEntry.objects.create(
            employee=self.employee,
            entry_date=date(2026, 6, 13),
            hours_worked=Decimal("8.00"),
        )
        result = self._calc()
        self.assertEqual(result["details"]["base_pay"], Decimal("16000.00"))
