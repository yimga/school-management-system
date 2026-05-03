"""Churn/recovered lifecycle automation + dashboard surfacing."""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.platform_runtime.models import TenantRetentionPlaybookAction
from apps.platform_runtime.tenant_lifecycle_operator import (
    build_lifecycle_dashboard_context,
)
from apps.platform_runtime.tenant_lifecycle_scheduler import run_lifecycle_retention_scan
from apps.platform_runtime.tenant_lifecycle_state_machine import (
    STATE_CHURNED,
    STATE_RECOVERED,
    resolve_tenant_lifecycle_state,
)
from apps.platform_runtime.tenant_retention_playbooks import PLAYBOOK_CHURNED_RECOVERY
from apps.schools.models import MarketingFunnelEvent, School


class TenantLifecycleFinalizationTests(TestCase):
    databases = {"default"}

    def _base_school(self, slug_suffix: str) -> School:
        return School.objects.create(
            name=f"Fin {slug_suffix}",
            slug=f"fin-{slug_suffix}",
            subdomain=f"fin-{slug_suffix}",
            is_active=True,
            last_activity=timezone.now(),
            billing_type=School.BillingType.REGULAR,
        )

    @override_settings(TENANT_LIFECYCLE_CHURN_PAYMENT_FAILED_DAYS=2)
    def test_churned_state_computed_prolonged_payment_failure(self):
        s = self._base_school("churn-pay")
        MarketingFunnelEvent.objects.create(
            event_type="subscription_started",
            school=s,
            session_key="",
            metadata={},
        )
        pf = MarketingFunnelEvent.objects.create(
            event_type="payment_failed",
            school=s,
            session_key="",
            metadata={},
        )
        MarketingFunnelEvent.objects.filter(pk=pf.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )
        out = resolve_tenant_lifecycle_state(s)
        self.assertEqual(out["state"], STATE_CHURNED)
        self.assertIn("prolonged_payment_failure", out["reasons"])

    @override_settings(TENANT_LIFECYCLE_CHURN_PAYMENT_FAILED_DAYS=2)
    def test_recovered_state_computed_after_prolonged_failure_window(self):
        s = self._base_school("rec-pay")
        MarketingFunnelEvent.objects.create(
            event_type="subscription_started",
            school=s,
            session_key="",
            metadata={},
        )
        pf = MarketingFunnelEvent.objects.create(
            event_type="payment_failed",
            school=s,
            session_key="",
            metadata={},
        )
        MarketingFunnelEvent.objects.filter(pk=pf.pk).update(
            created_at=timezone.now() - timedelta(days=20)
        )
        ps = MarketingFunnelEvent.objects.create(
            event_type="payment_success",
            school=s,
            session_key="",
            metadata={},
        )
        MarketingFunnelEvent.objects.filter(pk=ps.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )
        out = resolve_tenant_lifecycle_state(s)
        self.assertEqual(out["state"], STATE_RECOVERED)
        self.assertIn("billing_recovered_after_prolonged_failure", out["reasons"])

    @override_settings(TENANT_LIFECYCLE_CHURN_INACTIVITY_DAYS=5)
    def test_churned_dormant_monetized_low_activity(self):
        s = self._base_school("dormant")
        MarketingFunnelEvent.objects.create(
            event_type="payment_success", school=s, session_key="", metadata={}
        )
        School.objects.filter(pk=s.pk).update(
            last_activity=timezone.now() - timedelta(days=30)
        )
        s.refresh_from_db()
        out = resolve_tenant_lifecycle_state(s)
        self.assertEqual(out["state"], STATE_CHURNED)

    def test_recovery_playbook_action_generated_for_recovered(self):
        s = self._base_school("recovery-act")
        MarketingFunnelEvent.objects.create(
            event_type="tenant_recovered",
            school=s,
            session_key="",
            metadata={},
        )
        run_lifecycle_retention_scan(schools=School.objects.filter(pk=s.pk))
        self.assertTrue(
            TenantRetentionPlaybookAction.objects.filter(
                school=s,
                playbook_code=PLAYBOOK_CHURNED_RECOVERY,
                payload__phase="followthrough",
            ).exists()
        )

    def test_dashboard_reflects_retention_counts_and_states(self):
        s = self._base_school("dash")
        MarketingFunnelEvent.objects.create(
            event_type="tenant_recovered",
            school=s,
            session_key="",
            metadata={},
        )
        run_lifecycle_retention_scan(schools=School.objects.filter(pk=s.pk))
        ctx = build_lifecycle_dashboard_context([s], viewer_scope="tenant")
        row = ctx["rows"][0]
        self.assertEqual(row["state_key"], STATE_RECOVERED)
        self.assertGreaterEqual(row.get("open_retention_actions", 0), 1)
