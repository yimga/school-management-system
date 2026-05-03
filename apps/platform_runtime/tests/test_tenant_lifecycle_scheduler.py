"""Lifecycle retention scheduler scan + isolation."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.billing.models import BillingAccount, TenantSubscription
from apps.platform_runtime.models import (
    TenantLifecycleSchedulerRun,
    TenantRetentionPlaybookAction,
)
from apps.platform_runtime.tenant_lifecycle_scheduler import run_lifecycle_retention_scan
from apps.platform_runtime.tenant_retention_playbooks import PLAYBOOK_PAYMENT_FAILED_FOLLOW_UP
from apps.schools.models import MarketingFunnelEvent, School


class TenantLifecycleSchedulerTests(TestCase):
    databases = {"default"}

    def _risk_school(self, slug_suffix: str) -> School:
        s = School.objects.create(
            name=f"Sched {slug_suffix}",
            slug=f"sch-{slug_suffix}",
            subdomain=f"sch-{slug_suffix}",
            is_active=True,
            last_activity=timezone.now(),
            billing_type=School.BillingType.REGULAR,
        )
        ba, _ = BillingAccount.objects.get_or_create(
            school=s,
            defaults={"status": BillingAccount.Status.ACTIVE},
        )
        TenantSubscription.objects.create(
            billing_account=ba,
            school=s,
            status=TenantSubscription.Status.ACTIVE,
            billed_amount=Decimal("40.00"),
        )
        MarketingFunnelEvent.objects.create(
            event_type="subscription_started", school=s, session_key="", metadata={}
        )
        MarketingFunnelEvent.objects.create(
            event_type="payment_success", school=s, session_key="", metadata={}
        )
        MarketingFunnelEvent.objects.create(
            event_type="payment_failed", school=s, session_key="", metadata={}
        )
        return s

    def test_scheduler_run_logged(self):
        s = self._risk_school("log-a")
        run = run_lifecycle_retention_scan(
            schools=School.objects.filter(pk=s.pk),
        )
        run.refresh_from_db()
        self.assertEqual(run.tenants_scanned, 1)
        self.assertEqual(run.status, TenantLifecycleSchedulerRun.Status.SUCCESS)
        self.assertIsNotNone(run.finished_at)

    def test_duplicate_actions_avoided_across_runs(self):
        s = self._risk_school("dedupe-run")
        qs = School.objects.filter(pk=s.pk)
        run_lifecycle_retention_scan(schools=qs)
        run_lifecycle_retention_scan(schools=qs)
        self.assertEqual(
            TenantRetentionPlaybookAction.objects.filter(
                playbook_code=PLAYBOOK_PAYMENT_FAILED_FOLLOW_UP,
                school=s,
            ).count(),
            1,
        )

    def test_tenant_isolation_only_scoped_school(self):
        a = self._risk_school("iso-a")
        b = self._risk_school("iso-b")
        run_lifecycle_retention_scan(schools=School.objects.filter(pk=a.pk))
        self.assertTrue(
            TenantRetentionPlaybookAction.objects.filter(school=a).exists()
        )
        self.assertFalse(
            TenantRetentionPlaybookAction.objects.filter(school=b).exists()
        )
