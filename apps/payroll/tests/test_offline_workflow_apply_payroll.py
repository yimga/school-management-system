"""Payroll offline workflow apply (batch 1511)."""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.accounts.models import User
from apps.finance.models import ComplianceProfile
from apps.payroll.models import PayrollEmployee, PayrollRun
from apps.payroll.models_offline_capture import PayrollOfflineCaptureRecord
from apps.payroll.offline_workflow_handlers import apply_payroll_workflow
from apps.schools.models import School, SchoolMembership


class PayrollOfflineWorkflowApplyTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"PayWF {uid}",
            slug=f"paywf-{uid}",
            subdomain=f"paywf{uid}",
            is_active=True,
        )
        self.profile = ComplianceProfile.objects.create(
            name=f"Profile {uid}",
            country_code="CM",
            currency_code="XAF",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username=f"paywf_a_{uid}",
            password="pw",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.get_or_create(
            user=self.admin,
            school=self.school,
            defaults={"role": self.admin.role, "is_primary": True},
        )
        self.employee = PayrollEmployee.objects.create(user=self.admin)

    def test_create_run_offline_apply(self):
        result = apply_payroll_workflow(
            self.school.pk,
            self.admin.pk,
            "payroll_create_run",
            {
                "period_start": "2026-05-01",
                "period_end": "2026-05-31",
            },
            {"client_offline_id": f"pr-{uuid.uuid4().hex[:8]}"},
        )
        self.assertTrue(result and result.get("ok"))
        self.assertEqual(PayrollRun.objects.filter(profile=self.profile).count(), 1)

    def test_create_run_idempotent_via_capture(self):
        key = f"pr-idem-{uuid.uuid4().hex[:8]}"
        payload = {"client_offline_id": key}
        fields = {"period_start": "2026-04-01", "period_end": "2026-04-30"}
        r1 = apply_payroll_workflow(
            self.school.pk, self.admin.pk, "payroll_create_run", fields, payload
        )
        r2 = apply_payroll_workflow(
            self.school.pk, self.admin.pk, "payroll_create_run", fields, payload
        )
        self.assertEqual(r1.get("run_id"), r2.get("run_id"))
        self.assertEqual(PayrollRun.objects.filter(profile=self.profile).count(), 1)
        self.assertEqual(
            PayrollOfflineCaptureRecord.objects.filter(
                school_id=self.school.pk, client_offline_id=key
            ).count(),
            1,
        )
