"""Payroll disbursement CSV export (batch 1511)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.finance.models import ComplianceProfile
from apps.payroll.disbursement_export import build_disbursement_csv
from apps.payroll.models import PayrollEmployee, PayrollRun, Payslip


class DisbursementExportTests(TestCase):
    def test_build_disbursement_csv_includes_net_pay(self):
        uid = uuid.uuid4().hex[:8]
        profile = ComplianceProfile.objects.create(
            name=f"Disp {uid}",
            country_code="CM",
            currency_code="XAF",
            is_active=True,
        )
        user = User.objects.create_user(username=f"disp_{uid}", password="pw")
        employee = PayrollEmployee.objects.create(
            user=user,
            employee_code="E001",
            bank_account="123456789",
            payment_method=PayrollEmployee.PaymentMethod.BANK_TRANSFER,
        )
        run = PayrollRun.objects.create(
            profile=profile,
            period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 31),
            status=PayrollRun.Status.APPROVED,
            created_by=user,
        )
        Payslip.objects.create(
            payroll_run=run,
            employee=employee,
            gross_pay=Decimal("100000.00"),
            net_pay=Decimal("85000.00"),
            tax_amount=Decimal("15000.00"),
            status=Payslip.Status.ISSUED,
        )
        csv_text = build_disbursement_csv(run)
        self.assertIn("employee_code", csv_text)
        self.assertIn("E001", csv_text)
        self.assertIn("85000.00", csv_text)
        self.assertIn("XAF", csv_text)
