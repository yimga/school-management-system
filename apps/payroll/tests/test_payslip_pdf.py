"""Payslip PDF download: access control + graceful WeasyPrint-missing degradation.

The actual PDF binary is produced by WeasyPrint (proven where its system libs are
installed — the reports PDF CI lane); those libs are absent here, so these tests mock
the render helper and focus on the view contract: own-employee OR payroll.manage may
download, others get 403, and a missing-WeasyPrint RuntimeError degrades to a redirect
instead of a 500.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.finance.models import ComplianceProfile
from apps.payroll.models import PayrollEmployee, PayrollRun, Payslip
from apps.payroll.views import payslip_pdf


class PayslipPdfViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        uid = uuid.uuid4().hex[:8]
        self.profile = ComplianceProfile.objects.create(
            name=f"Emp {uid}", country_code="CM", currency_code="XAF", is_active=True
        )
        self.run = PayrollRun.objects.create(
            profile=self.profile,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            status=PayrollRun.Status.PAID,
        )
        self.user_a = User.objects.create_user(username=f"a_{uid}", password="pw")
        self.emp_a = PayrollEmployee.objects.create(user=self.user_a, employee_code=f"A{uid}")
        self.slip = Payslip.objects.create(
            payroll_run=self.run,
            employee=self.emp_a,
            gross_pay=Decimal("100000.00"),
            net_pay=Decimal("85000.00"),
            tax_amount=Decimal("15000.00"),
            status=Payslip.Status.PAID,
        )
        self.user_b = User.objects.create_user(username=f"b_{uid}", password="pw")
        PayrollEmployee.objects.create(user=self.user_b, employee_code=f"B{uid}")

    def _req(self, user):
        req = self.factory.get(f"/payroll/payslips/{self.slip.id}/pdf/")
        req.user = user
        req.school = None
        req.session = {}
        setattr(req, "_messages", FallbackStorage(req))
        return req

    def _fake_pdf(self, *a, **k):
        resp = HttpResponse(b"%PDF-1.4 fake", content_type="application/pdf")
        resp["Content-Disposition"] = 'inline; filename="payslip.pdf"'
        return resp

    def test_owner_downloads_own_payslip_as_pdf(self):
        with mock.patch("apps.reports.weasy.render_pdf", side_effect=self._fake_pdf):
            resp = payslip_pdf(self._req(self.user_a), self.slip.id)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_other_employee_forbidden(self):
        # user_b is an employee but not this payslip's owner and has no payroll.manage.
        resp = payslip_pdf(self._req(self.user_b), self.slip.id)
        self.assertEqual(resp.status_code, 403)

    def test_manage_user_can_download_any_payslip(self):
        boss = User.objects.create_superuser(
            username=f"boss_{uuid.uuid4().hex[:6]}", email="boss@x.test", password="pw"
        )
        with mock.patch("apps.reports.weasy.render_pdf", side_effect=self._fake_pdf):
            resp = payslip_pdf(self._req(boss), self.slip.id)
        self.assertEqual(resp.status_code, 200)

    def test_weasyprint_missing_degrades_to_redirect_not_500(self):
        with mock.patch(
            "apps.reports.weasy.render_pdf",
            side_effect=RuntimeError("WeasyPrint dependencies are missing."),
        ):
            resp = payslip_pdf(self._req(self.user_a), self.slip.id)
        self.assertEqual(resp.status_code, 302)  # graceful redirect, not a crash
