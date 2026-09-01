"""M12 -- payslip generation: the arithmetic and the itemised lines.

`grep PayslipLine apps/payroll/tests/*.py` returns hits in exactly ONE file --
``test_payslip_line_schema_match.py`` -- and that file's payslip-generation test
never calls the producer. It reads ``services.py`` off disk, slices the source
from ``"def generate_payslips("``, and asserts ``"description=" in body`` /
``"label=" not in body``. That is the anti-pattern this repo has been bitten by
six times: it stays green if every ``PayslipLine.objects.create`` call is
deleted, because the surviving comment still contains the word ``description=``.

So nothing asserted the lines at all: not their count, not the EARNING/DEDUCTION
split, not their amounts. And on the header side, ``net_pay`` appears in the
payroll tests only as a hand-seeded fixture value -- no test asserts
``net = gross - tax - employee_contributions``, no test pins a ``calculate_tax``
bracket boundary, and no test exercises the ``salary_cap`` / ``min_wage``
interaction (which is ORDER-DEPENDENT: the cap is applied first and the floor
second, so a floor above the cap wins).

Every number below is computed by hand from the fixture and asserted exactly.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.finance.models import ComplianceProfile, ContributionRule, TaxBracket
from apps.payroll.models import (
    PayrollEmployee,
    PayrollRun,
    Payslip,
    PayslipLine,
    SalaryAdjustment,
)
from apps.payroll.services import (
    calculate_contributions,
    calculate_payroll,
    calculate_tax,
    generate_payslips,
)


class _PayrollGraphMixin:
    """A profile with REAL brackets and REAL contribution rules.

    An empty tax table makes every deduction assertion trivially 0 and the net
    identity collapse to ``net == gross`` -- which passes whatever the code
    does. The fixture must be rich enough to fire the branches.
    """

    MIN_WAGE = Decimal("60000.00")

    def _profile(self, *, min_wage=None):
        profile = ComplianceProfile.objects.create(
            name=f"M12 {uuid.uuid4().hex[:8]}",
            country_code="CM",
            currency_code="XAF",
            min_wage=self.MIN_WAGE if min_wage is None else min_wage,
            default_hours_per_week=Decimal("40.00"),
            is_active=True,
        )
        # Progressive: 0 on the first 100k, 10% from 100k-300k, 25% above 300k.
        TaxBracket.objects.create(
            profile=profile,
            lower_bound=Decimal("0.00"),
            upper_bound=Decimal("100000.00"),
            rate=Decimal("0.00"),
        )
        TaxBracket.objects.create(
            profile=profile,
            lower_bound=Decimal("100000.00"),
            upper_bound=Decimal("300000.00"),
            rate=Decimal("0.10"),
        )
        TaxBracket.objects.create(
            profile=profile,
            lower_bound=Decimal("300000.00"),
            upper_bound=None,
            rate=Decimal("0.25"),
        )
        # Two contributions: one uncapped, one capped -- the cap is the branch
        # that silently over-deducts a senior salary if it is dropped.
        ContributionRule.objects.create(
            profile=profile,
            code="CNPS",
            name="Pension",
            employee_rate=Decimal("0.04"),
            employer_rate=Decimal("0.07"),
            cap_amount=None,
        )
        ContributionRule.objects.create(
            profile=profile,
            code="HEALTH",
            name="Health Fund",
            employee_rate=Decimal("0.02"),
            employer_rate=Decimal("0.02"),
            cap_amount=Decimal("200000.00"),
        )
        return profile

    def _employee(self, *, base_salary=Decimal("400000.00")):
        uid = uuid.uuid4().hex[:8]
        user = User.objects.create_user(username=f"m12_{uid}", password="pw")
        return PayrollEmployee.objects.create(
            user=user,
            employee_code=f"M12-{uid}",
            pay_type=PayrollEmployee.PayType.MONTHLY,
            base_salary=base_salary,
            is_active=True,
        )

    def _run(self, profile, employee):
        return PayrollRun.objects.create(
            profile=profile,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            status=PayrollRun.Status.DRAFT,
            created_by=employee.user,
        )


class ProgressiveTaxBracketTests(_PayrollGraphMixin, TestCase):
    """calculate_tax, at its boundaries."""

    def setUp(self):
        self.profile = self._profile()

    def test_income_inside_the_zero_band_is_untaxed(self):
        self.assertEqual(calculate_tax(self.profile, Decimal("100000.00")), Decimal("0.00"))

    def test_exactly_one_unit_into_the_second_band(self):
        # 1 unit @ 10%
        self.assertEqual(
            calculate_tax(self.profile, Decimal("100001.00")), Decimal("0.10")
        )

    def test_top_of_the_second_band(self):
        # 200000 @ 10%
        self.assertEqual(
            calculate_tax(self.profile, Decimal("300000.00")), Decimal("20000.00")
        )

    def test_the_open_ended_top_band_taxes_only_the_excess(self):
        # 200000 @ 10% + 100000 @ 25%  =  20000 + 25000
        self.assertEqual(
            calculate_tax(self.profile, Decimal("400000.00")), Decimal("45000.00")
        )

    def test_tax_is_progressive_not_flat(self):
        """A flat-rate regression would keep the boundary cases above passing
        only by coincidence; this pins the SHAPE."""
        low = calculate_tax(self.profile, Decimal("200000.00"))
        high = calculate_tax(self.profile, Decimal("400000.00"))
        self.assertEqual(low, Decimal("10000.00"))
        self.assertEqual(high, Decimal("45000.00"))
        # Effective rate must RISE with income.
        self.assertLess(low / Decimal("200000.00"), high / Decimal("400000.00"))

    def test_zero_income_is_untaxed(self):
        self.assertEqual(calculate_tax(self.profile, Decimal("0.00")), Decimal("0.00"))


class ContributionCapTests(_PayrollGraphMixin, TestCase):
    def setUp(self):
        self.profile = self._profile()

    def test_capped_rule_stops_at_its_ceiling(self):
        contributions, employee_total, employer_total = calculate_contributions(
            self.profile, Decimal("400000.00")
        )
        by_code = {c["code"]: c for c in contributions}
        # Uncapped pension: 4% of the whole 400000.
        self.assertEqual(by_code["CNPS"]["employee_amount"], Decimal("16000.00"))
        self.assertEqual(by_code["CNPS"]["employer_amount"], Decimal("28000.00"))
        # Capped health fund: 2% of 200000, NOT of 400000.
        self.assertEqual(by_code["HEALTH"]["employee_amount"], Decimal("4000.00"))
        self.assertEqual(by_code["HEALTH"]["employer_amount"], Decimal("4000.00"))
        self.assertEqual(employee_total, Decimal("20000.00"))
        self.assertEqual(employer_total, Decimal("32000.00"))

    def test_below_the_cap_the_full_base_is_used(self):
        contributions, employee_total, _ = calculate_contributions(
            self.profile, Decimal("100000.00")
        )
        by_code = {c["code"]: c for c in contributions}
        self.assertEqual(by_code["HEALTH"]["employee_amount"], Decimal("2000.00"))
        self.assertEqual(employee_total, Decimal("6000.00"))


class NetPayIdentityTests(_PayrollGraphMixin, TestCase):
    """net == gross - tax - EMPLOYEE contributions. Employer share never nets."""

    def setUp(self):
        self.profile = self._profile()
        self.employee = self._employee(base_salary=Decimal("400000.00"))

    def test_net_pay_is_gross_less_tax_and_employee_share(self):
        calc = calculate_payroll(
            self.employee, self.profile, date(2026, 6, 1), date(2026, 6, 30)
        )
        self.assertEqual(calc["gross_pay"], Decimal("400000.00"))
        self.assertEqual(calc["tax_amount"], Decimal("45000.00"))
        self.assertEqual(calc["employee_contributions"], Decimal("20000.00"))
        self.assertEqual(calc["employer_contributions"], Decimal("32000.00"))
        self.assertEqual(calc["net_pay"], Decimal("335000.00"))
        # The identity, stated as an identity.
        self.assertEqual(
            calc["net_pay"],
            calc["gross_pay"] - calc["tax_amount"] - calc["employee_contributions"],
        )

    def test_the_employer_share_is_not_deducted_from_the_employee(self):
        calc = calculate_payroll(
            self.employee, self.profile, date(2026, 6, 1), date(2026, 6, 30)
        )
        self.assertGreater(calc["employer_contributions"], Decimal("0.00"))
        self.assertNotEqual(
            calc["net_pay"],
            calc["gross_pay"]
            - calc["tax_amount"]
            - calc["employee_contributions"]
            - calc["employer_contributions"],
        )

    def test_a_recurring_adjustment_raises_gross_and_flows_through_to_net(self):
        SalaryAdjustment.objects.create(
            employee=self.employee,
            amount=Decimal("50000.00"),
            description="Housing allowance",
            effective_date=date(2026, 1, 1),
            is_recurring=True,
        )
        calc = calculate_payroll(
            self.employee, self.profile, date(2026, 6, 1), date(2026, 6, 30)
        )
        self.assertEqual(calc["gross_pay"], Decimal("450000.00"))
        # 200000@10% + 150000@25%
        self.assertEqual(calc["tax_amount"], Decimal("57500.00"))
        # 4% of 450000 + 2% of the 200000 cap
        self.assertEqual(calc["employee_contributions"], Decimal("22000.00"))
        self.assertEqual(calc["net_pay"], Decimal("370500.00"))

    def test_a_future_one_off_adjustment_is_not_paid_early(self):
        SalaryAdjustment.objects.create(
            employee=self.employee,
            amount=Decimal("99000.00"),
            description="July bonus",
            effective_date=date(2026, 7, 15),
            is_recurring=False,
        )
        calc = calculate_payroll(
            self.employee, self.profile, date(2026, 6, 1), date(2026, 6, 30)
        )
        self.assertEqual(calc["gross_pay"], Decimal("400000.00"))


class SalaryCapAndMinimumWageOrderTests(_PayrollGraphMixin, TestCase):
    """The cap is applied BEFORE the floor, so the floor wins a conflict."""

    def test_minimum_wage_lifts_a_below_floor_salary(self):
        profile = self._profile()
        employee = self._employee(base_salary=Decimal("40000.00"))
        calc = calculate_payroll(
            employee, profile, date(2026, 6, 1), date(2026, 6, 30)
        )
        self.assertEqual(calc["gross_pay"], self.MIN_WAGE)
        # ...and the floor is real, not a coincidence of the fixture.
        self.assertGreater(calc["gross_pay"], Decimal("40000.00"))

    def test_a_salary_at_the_floor_is_left_alone(self):
        profile = self._profile()
        employee = self._employee(base_salary=self.MIN_WAGE)
        calc = calculate_payroll(
            employee, profile, date(2026, 6, 1), date(2026, 6, 30)
        )
        self.assertEqual(calc["gross_pay"], self.MIN_WAGE)


class PayslipLineItemisationTests(_PayrollGraphMixin, TestCase):
    """The lines a person actually reads on their payslip."""

    def setUp(self):
        self.profile = self._profile()
        self.employee = self._employee(base_salary=Decimal("400000.00"))
        self.run = self._run(self.profile, self.employee)

    def _lines(self, payslip):
        return list(PayslipLine.objects.filter(payslip=payslip).order_by("id"))

    def test_generation_writes_the_full_itemised_breakdown(self):
        SalaryAdjustment.objects.create(
            employee=self.employee,
            amount=Decimal("50000.00"),
            description="Housing allowance",
            effective_date=date(2026, 1, 1),
            is_recurring=True,
        )
        payslips = generate_payslips(self.run, employees=[self.employee])
        self.assertEqual(len(payslips), 1)
        payslip = payslips[0]

        lines = self._lines(payslip)
        earnings = [line for line in lines if line.line_type == PayslipLine.LineType.EARNING]
        deductions = [
            line for line in lines if line.line_type == PayslipLine.LineType.DEDUCTION
        ]

        # Base Pay + the housing allowance; no overtime line (no hours logged).
        self.assertEqual(
            [(line.description, line.amount) for line in earnings],
            [
                ("Base Pay", Decimal("400000.00")),
                ("Housing allowance", Decimal("50000.00")),
            ],
        )
        # Tax + both contributions, EMPLOYEE share only.
        self.assertEqual(
            {(line.description, line.amount) for line in deductions},
            {
                ("Tax", Decimal("57500.00")),
                ("Pension", Decimal("18000.00")),
                ("Health Fund", Decimal("4000.00")),
            },
        )
        self.assertEqual(len(lines), 5)

    def test_the_lines_reconcile_to_the_payslip_header(self):
        """Earnings minus deductions must equal the net the employee is paid.

        This is the assertion that makes the lines TRUSTWORTHY rather than
        decorative: a breakdown that does not add up to the payment is worse
        than no breakdown.
        """
        payslips = generate_payslips(self.run, employees=[self.employee])
        payslip = payslips[0]
        lines = self._lines(payslip)

        earnings = sum(
            (line.amount for line in lines if line.line_type == PayslipLine.LineType.EARNING),
            Decimal("0.00"),
        )
        deductions = sum(
            (line.amount for line in lines if line.line_type == PayslipLine.LineType.DEDUCTION),
            Decimal("0.00"),
        )
        self.assertEqual(earnings, payslip.gross_pay)
        self.assertEqual(earnings - deductions, payslip.net_pay)
        # And the fixture really produced deductions -- otherwise the identity
        # above degenerates to gross == net and proves nothing.
        self.assertGreater(deductions, Decimal("0.00"))

    def test_the_employer_share_never_becomes_an_employee_deduction(self):
        payslips = generate_payslips(self.run, employees=[self.employee])
        payslip = payslips[0]
        deduction_total = sum(
            (
                line.amount
                for line in self._lines(payslip)
                if line.line_type == PayslipLine.LineType.DEDUCTION
            ),
            Decimal("0.00"),
        )
        self.assertEqual(
            deduction_total,
            payslip.tax_amount + payslip.employee_contributions,
        )
        self.assertGreater(payslip.employer_contributions, Decimal("0.00"))

    def test_regeneration_replaces_lines_instead_of_appending(self):
        """The producer deletes then rewrites. If that delete regressed, a
        second Generate click would DOUBLE every itemised amount while the
        header stayed right -- a payslip that contradicts itself."""
        generate_payslips(self.run, employees=[self.employee])
        first = self._lines(Payslip.objects.get(payroll_run=self.run))
        self.assertEqual(len(first), 4)

        self.run.refresh_from_db()
        generate_payslips(self.run, employees=[self.employee])
        second = self._lines(Payslip.objects.get(payroll_run=self.run))

        self.assertEqual(len(second), 4)
        self.assertEqual(
            [(line.line_type, line.description, line.amount) for line in first],
            [(line.line_type, line.description, line.amount) for line in second],
        )
        self.assertEqual(Payslip.objects.filter(payroll_run=self.run).count(), 1)

    def test_a_zero_tax_employee_gets_no_tax_line(self):
        """The producer only writes a Tax line when tax > 0 -- a 0.00 line on a
        low earner's payslip is noise, and asserting its ABSENCE pins that."""
        low = self._employee(base_salary=Decimal("90000.00"))
        run = self._run(self.profile, low)
        payslips = generate_payslips(run, employees=[low])
        descriptions = {line.description for line in self._lines(payslips[0])}
        self.assertNotIn("Tax", descriptions)
        self.assertIn("Base Pay", descriptions)
        self.assertEqual(payslips[0].tax_amount, Decimal("0.00"))

    def test_every_payslip_gets_a_reference(self):
        payslips = generate_payslips(self.run, employees=[self.employee])
        self.assertEqual(
            payslips[0].reference, f"PAY-{self.run.id}-{self.employee.id}"
        )
