"""``generate_payslips`` must actually reach the database.

Nothing in this app executed it. The three modules that mention it all avoid
running it:

* ``test_payslip_line_schema_match`` reads ``services.py`` as TEXT and asserts on
  substrings -- it never imports or calls the function;
* ``test_mark_run_paid`` builds ``Payslip.objects.create(...)`` by hand;
* ``test_run_payroll_cycle_command`` decorates with
  ``@patch("...run_payroll_cycle.generate_payslips")`` -- the real function is
  mocked away.

So the whole payroll producer was unexercised, and a genuine crash sat there
undetected: ``calculate_payroll`` builds ``details`` out of model fields, so it
always carries Decimals (base_pay, overtime_pay, every adjustments[].amount and
contributions[].employee_amount / employer_amount) and a ``datetime.date``
(adjustments[].effective_date). ``Payslip.details`` was a plain JSONField with no
``encoder``, and ``JSONField.get_db_prep_save`` routes through
``connection.ops.adapt_json_value(value, self.encoder)`` -> ``json.dumps``, which
raises ``TypeError: Object of type Decimal is not JSON serializable``.

This test calls the real function against the real database.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.finance.models import ComplianceProfile
from apps.payroll.models import PayrollEmployee, PayrollRun, Payslip
from apps.payroll.services import generate_payslips


class GeneratePayslipsPersistsTests(TestCase):
    def setUp(self) -> None:
        uid = uuid.uuid4().hex[:8]
        self.profile = ComplianceProfile.objects.create(
            name=f"Pay {uid}", country_code="CM", currency_code="XAF", is_active=True
        )
        self.user = User.objects.create_user(username=f"emp_{uid}", password="pw")
        self.employee = PayrollEmployee.objects.create(
            user=self.user,
            employee_code=f"E{uid}",
            base_salary=Decimal("100000.00"),
            is_active=True,
        )
        self.run = PayrollRun.objects.create(
            profile=self.profile,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            created_by=self.user,
        )

    def test_generate_payslips_writes_a_row(self) -> None:
        # Before the encoder fix this raised TypeError on the INSERT.
        slips = generate_payslips(self.run, [self.employee])
        self.assertEqual(len(slips), 1)
        self.assertTrue(
            Payslip.objects.filter(
                payroll_run=self.run, employee=self.employee
            ).exists()
        )

    def test_details_survives_a_round_trip_through_the_database(self) -> None:
        generate_payslips(self.run, [self.employee])
        stored = Payslip.objects.get(
            payroll_run=self.run, employee=self.employee
        ).details
        # DjangoJSONEncoder renders Decimal as a string; the point is that the
        # value PERSISTS at all and keeps its magnitude.
        self.assertIn("base_pay", stored)
        self.assertEqual(Decimal(str(stored["base_pay"])), Decimal("100000.00"))
