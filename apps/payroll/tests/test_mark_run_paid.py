"""PayrollRun/Payslip PAID producer + the now-live regeneration lock.

Before this, ``PayrollRun.Status.PAID`` / ``Payslip.Status.PAID`` and both
``paid_at`` columns had NO writer: ``generate_payslips`` only ever set PROCESSED /
ISSUED. So ``generate_run``'s ``if run.status == PAID`` guard was dead code and a
disbursed run's payslips could be silently regenerated/overwritten. ``mark_payroll
_run_paid`` is the producer; marking a run paid now freezes it.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.finance.models import ComplianceProfile
from apps.payroll.models import PayrollEmployee, PayrollRun, Payslip
from apps.payroll.services import mark_payroll_run_paid


class _PayrollGraphMixin:
    def _graph(self, *, run_status=PayrollRun.Status.PROCESSED, slip_status=Payslip.Status.ISSUED):
        uid = uuid.uuid4().hex[:8]
        profile = ComplianceProfile.objects.create(
            name=f"Pay {uid}", country_code="CM", currency_code="XAF", is_active=True
        )
        user = User.objects.create_user(username=f"emp_{uid}", password="pw")
        employee = PayrollEmployee.objects.create(user=user, employee_code=f"E{uid}")
        run = PayrollRun.objects.create(
            profile=profile,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            status=run_status,
            created_by=user,
        )
        slip = Payslip.objects.create(
            payroll_run=run,
            employee=employee,
            gross_pay=Decimal("100000.00"),
            net_pay=Decimal("85000.00"),
            tax_amount=Decimal("15000.00"),
            status=slip_status,
        )
        return profile, user, employee, run, slip


class MarkPayrollRunPaidServiceTests(_PayrollGraphMixin, TestCase):
    def test_marks_run_and_payslips_paid_with_timestamps(self):
        _, _, _, run, slip = self._graph()
        self.assertIsNone(run.paid_at)
        self.assertIsNone(slip.paid_at)

        mark_payroll_run_paid(run)

        run.refresh_from_db()
        slip.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.PAID)
        self.assertIsNotNone(run.paid_at)
        self.assertEqual(slip.status, Payslip.Status.PAID)
        self.assertIsNotNone(slip.paid_at)

    def test_idempotent(self):
        _, _, _, run, _ = self._graph()
        mark_payroll_run_paid(run)
        first_paid_at = PayrollRun.objects.get(pk=run.pk).paid_at
        # A second call on the fresh-from-db PAID run is a no-op.
        again = PayrollRun.objects.get(pk=run.pk)
        mark_payroll_run_paid(again)
        self.assertEqual(PayrollRun.objects.get(pk=run.pk).paid_at, first_paid_at)
        self.assertEqual(PayrollRun.objects.get(pk=run.pk).status, PayrollRun.Status.PAID)

    def test_refuses_draft_run(self):
        _, _, _, run, _ = self._graph(run_status=PayrollRun.Status.DRAFT)
        with self.assertRaises(ValueError):
            mark_payroll_run_paid(run)
        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.DRAFT)

    def test_preserves_earlier_paid_at_on_already_paid_slip(self):
        # A slip already PAID (with its own paid_at) is not re-stamped.
        _, _, _, run, slip = self._graph(slip_status=Payslip.Status.PAID)
        earlier = timezone.now() - timezone.timedelta(days=2)
        Payslip.objects.filter(pk=slip.pk).update(paid_at=earlier)
        mark_payroll_run_paid(run)
        slip.refresh_from_db()
        self.assertEqual(slip.status, Payslip.Status.PAID)
        self.assertEqual(slip.paid_at, earlier)


class GenerateRunLockAfterPaidTests(_PayrollGraphMixin, TestCase):
    def test_generate_run_refuses_to_regenerate_a_paid_run(self):
        # The decisive integrity win: once a run is PAID, the previously-dead
        # guard in generate_run blocks regeneration, so figures can't be
        # overwritten after disbursement.
        from apps.payroll.views import generate_run

        _, _, _, run, slip = self._graph()
        mark_payroll_run_paid(run)
        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.PAID)

        superuser = User.objects.create_superuser(
            username=f"su_{uuid.uuid4().hex[:6]}", email="su@example.com", password="pw"
        )
        req = RequestFactory().get(f"/payroll/runs/{run.id}/generate/")
        req.user = superuser
        req.session = {}
        setattr(req, "_messages", FallbackStorage(req))

        resp = generate_run(req, run.id)
        self.assertEqual(resp.status_code, 302)  # redirected, not regenerated
        run.refresh_from_db()
        slip.refresh_from_db()
        # Blocked: run stays PAID (generate_payslips would have set it PROCESSED)
        # and the payslip stays PAID (would have been reset to ISSUED).
        self.assertEqual(run.status, PayrollRun.Status.PAID)
        self.assertEqual(slip.status, Payslip.Status.PAID)
