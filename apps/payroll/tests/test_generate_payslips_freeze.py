"""The regeneration freeze belongs to the PRODUCER, not to one view.

``generate_run`` (views.py) refused a PAID run, but ``generate_payslips`` itself
had no status check at all and unconditionally rewound ``PayrollRun.status`` to
PROCESSED. Two doors bypassed the view entirely:

* ``manage.py run_payroll_cycle`` — ``get_or_create`` finds the disbursed run and
  calls ``generate_payslips`` on it, rewriting every Payslip and dropping PAID
  back to PROCESSED, so the figures no longer match what the bank paid.
* a REVIEWED/APPROVED run — the view only ever looked at PAID, so a second click
  on Generate recomputed an approved payroll while its ``PayrollRunApproval``
  row survived, still attesting to numbers that no longer exist.

These pin the guard where the writing happens.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.management import call_command
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.finance.models import ComplianceProfile
from apps.payroll.models import (
    PayrollEmployee,
    PayrollRun,
    PayrollRunApproval,
    Payslip,
)
from apps.payroll.services import generate_payslips


class _FreezeGraphMixin:
    def _graph(self, *, run_status=PayrollRun.Status.PAID, slip_status=Payslip.Status.PAID):
        uid = uuid.uuid4().hex[:8]
        profile = ComplianceProfile.objects.create(
            name=f"Freeze {uid}",
            country_code="CM",
            currency_code="XAF",
            min_wage=Decimal("60000.00"),
            default_hours_per_week=Decimal("40.00"),
            is_active=True,
        )
        user = User.objects.create_user(username=f"frz_{uid}", password="pw")
        employee = PayrollEmployee.objects.create(
            user=user,
            employee_code=f"E{uid}",
            pay_type=PayrollEmployee.PayType.MONTHLY,
            base_salary=Decimal("500000.00"),
            is_active=True,
        )
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


class GeneratePayslipsProducerFreezeTests(_FreezeGraphMixin, TestCase):
    def test_producer_actually_writes_when_the_run_is_open(self):
        # Anti-vacuous control: with the SAME graph at PROCESSED the producer
        # reaches the employee loop and rewrites the payslip. Every "refused"
        # assertion below is therefore measuring the guard, not an empty
        # employee queryset or a graph that never generates anything.
        _, _, employee, run, slip = self._graph(
            run_status=PayrollRun.Status.PROCESSED, slip_status=Payslip.Status.ISSUED
        )
        produced = generate_payslips(run)

        self.assertEqual([p.pk for p in produced], [slip.pk])
        slip.refresh_from_db()
        self.assertEqual(slip.gross_pay, Decimal("500000.00"))  # recomputed, not the seeded 100000

    def test_refuses_to_regenerate_a_paid_run(self):
        _, _, _, run, slip = self._graph()
        with self.assertRaises(ValueError):
            generate_payslips(run)

        run.refresh_from_db()
        slip.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.PAID)
        self.assertEqual(slip.status, Payslip.Status.PAID)
        self.assertEqual(slip.gross_pay, Decimal("100000.00"))

    def test_refuses_a_reviewed_run(self):
        _, _, _, run, slip = self._graph(
            run_status=PayrollRun.Status.REVIEWED, slip_status=Payslip.Status.ISSUED
        )
        with self.assertRaises(ValueError):
            generate_payslips(run)
        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.REVIEWED)

    def test_refuses_an_approved_run_and_leaves_the_approval_truthful(self):
        _, user, _, run, slip = self._graph(
            run_status=PayrollRun.Status.APPROVED, slip_status=Payslip.Status.ISSUED
        )
        PayrollRunApproval.objects.create(run=run, approver=user, notes="signed off")

        with self.assertRaises(ValueError):
            generate_payslips(run)

        run.refresh_from_db()
        slip.refresh_from_db()
        # The rewind is what made the approval row a lie: APPROVED -> PROCESSED
        # with recomputed figures under a surviving signature.
        self.assertEqual(run.status, PayrollRun.Status.APPROVED)
        self.assertEqual(slip.gross_pay, Decimal("100000.00"))
        self.assertEqual(PayrollRunApproval.objects.filter(run=run).count(), 1)


class GenerateRunViewSurfacesTheRefusalTests(_FreezeGraphMixin, TestCase):
    def _generate_run(self, run):
        from apps.payroll.views import generate_run

        superuser = User.objects.create_superuser(
            username=f"su_{uuid.uuid4().hex[:6]}", email="su@example.com", password="pw"
        )
        req = RequestFactory().get(f"/payroll/runs/{run.id}/generate/")
        req.user = superuser
        req.session = {}
        setattr(req, "_messages", FallbackStorage(req))
        return generate_run(req, run.id)

    def test_view_redirects_instead_of_raising_on_an_approved_run(self):
        _, user, _, run, slip = self._graph(
            run_status=PayrollRun.Status.APPROVED, slip_status=Payslip.Status.ISSUED
        )
        PayrollRunApproval.objects.create(run=run, approver=user)

        resp = self._generate_run(run)

        self.assertEqual(resp.status_code, 302)
        run.refresh_from_db()
        slip.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.APPROVED)
        self.assertEqual(slip.gross_pay, Decimal("100000.00"))

    def test_view_still_generates_for_a_draft_run(self):
        # Anti-vacuous control for the view leg: the redirect above is the guard
        # firing, not the view redirecting on every input.
        _, _, _, run, slip = self._graph(
            run_status=PayrollRun.Status.DRAFT, slip_status=Payslip.Status.DRAFT
        )
        resp = self._generate_run(run)
        self.assertEqual(resp.status_code, 302)
        run.refresh_from_db()
        slip.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.PROCESSED)
        self.assertEqual(slip.gross_pay, Decimal("500000.00"))


class RunPayrollCycleCommandFreezeTests(_FreezeGraphMixin, TestCase):
    def test_command_will_not_regenerate_a_paid_run_for_the_same_period(self):
        # get_or_create matches on (profile, period_start, period_end), so the
        # cron re-run lands straight on the disbursed June run.
        profile, _, _, run, slip = self._graph()
        # Only one profile may be active or get_active_payroll_profile picks a
        # different one and the command builds a *new* run instead.
        ComplianceProfile.objects.exclude(pk=profile.pk).update(is_active=False)

        with self.assertRaises(ValueError):
            call_command("run_payroll_cycle", year=2026, month=6)

        run.refresh_from_db()
        slip.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.PAID)
        self.assertEqual(slip.status, Payslip.Status.PAID)
        self.assertEqual(slip.gross_pay, Decimal("100000.00"))
        self.assertEqual(PayrollRun.objects.filter(profile=profile).count(), 1)
