"""Retention playbook matchers + deduplicated action creation."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.models import BillingAccount, TenantSubscription
from apps.platform_runtime.models import TenantRetentionPlaybookAction
from apps.platform_runtime.tenant_retention_playbooks import (
    PLAYBOOK_EXPANSION_READY_OUTREACH,
    PLAYBOOK_FIRST_ACTION_NOT_COMPLETED,
    PLAYBOOK_LOW_USAGE_RESCUE,
    PLAYBOOK_ONBOARDING_STALLED,
    PLAYBOOK_PAYMENT_FAILED_FOLLOW_UP,
    RETENTION_PLAYBOOKS,
    evaluate_playbooks_for_school,
)
from apps.platform_runtime.tenant_lifecycle_state_machine import STATE_EXPANSION_READY
from apps.schools.models import MarketingFunnelEvent, School


class TenantRetentionPlaybooksTests(TestCase):
    databases = {"default"}

    def _school(self, **kwargs):
        defaults = dict(
            name="PB School",
            slug=f"pb-{kwargs.get('slug_suffix', self.id())}",
            subdomain=f"pb-{kwargs.get('slug_suffix', self.id())}",
            is_active=True,
            last_activity=timezone.now(),
            billing_type=School.BillingType.REGULAR,
        )
        defaults.update(kwargs)
        defaults.pop("slug_suffix", None)
        return School.objects.create(**defaults)

    def test_named_playbook_catalog_has_seven_entries(self):
        self.assertEqual(len(RETENTION_PLAYBOOKS), 7)

    @override_settings(TENANT_LIFECYCLE_ONBOARDING_STALL_DAYS=3)
    def test_onboarding_stalled_creates_action(self):
        s = self._school(slug_suffix="onboard-stall")
        o = MarketingFunnelEvent.objects.create(
            event_type="onboarding_start",
            school=s,
            session_key="",
            utm_source="",
            utm_medium="",
            metadata={},
        )
        MarketingFunnelEvent.objects.filter(pk=o.pk).update(
            created_at=timezone.now() - timedelta(days=9)
        )
        # Omit signup_completed so lifecycle stays STATE_ONBOARDING (signup_completed maps to activated).
        n = evaluate_playbooks_for_school(s, scheduler_run=None)
        self.assertGreaterEqual(n, 1)
        self.assertTrue(
            TenantRetentionPlaybookAction.objects.filter(
                school=s,
                playbook_code=PLAYBOOK_ONBOARDING_STALLED,
                status=TenantRetentionPlaybookAction.Status.OPEN,
            ).exists()
        )

    @override_settings(TENANT_LIFECYCLE_FIRST_ACTION_STALL_DAYS=3)
    def test_first_action_not_completed_creates_action(self):
        s = self._school(slug_suffix="first-act")
        su = MarketingFunnelEvent.objects.create(
            event_type="signup_completed",
            school=s,
            session_key="",
            utm_source="",
            utm_medium="",
            metadata={},
        )
        MarketingFunnelEvent.objects.filter(pk=su.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )
        n = evaluate_playbooks_for_school(s)
        self.assertGreaterEqual(n, 1)
        self.assertTrue(
            TenantRetentionPlaybookAction.objects.filter(
                playbook_code=PLAYBOOK_FIRST_ACTION_NOT_COMPLETED,
                school=s,
            ).exists()
        )

    def test_payment_failed_follow_up_creates_action(self):
        s = self._school(slug_suffix="pay-fail")
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
        n = evaluate_playbooks_for_school(s)
        self.assertGreaterEqual(n, 1)
        self.assertTrue(
            TenantRetentionPlaybookAction.objects.filter(
                playbook_code=PLAYBOOK_PAYMENT_FAILED_FOLLOW_UP,
                school=s,
            ).exists()
        )

    @patch("apps.platform_runtime.tenant_retention_playbooks.calculate_school_health")
    def test_low_usage_rescue_creates_action(self, mock_health):
        s = self._school(slug_suffix="low-use")
        MarketingFunnelEvent.objects.create(
            event_type="signup_completed", school=s, session_key="", metadata={}
        )
        MarketingFunnelEvent.objects.create(
            event_type="first_action", school=s, session_key="", metadata={}
        )
        mock_health.return_value = {
            "score": 25,
            "student_count": 5,
            "teacher_count": 1,
            "has_report_schedules": False,
        }
        n = evaluate_playbooks_for_school(s)
        self.assertGreaterEqual(n, 1)
        self.assertTrue(
            TenantRetentionPlaybookAction.objects.filter(
                playbook_code=PLAYBOOK_LOW_USAGE_RESCUE,
                school=s,
            ).exists()
        )

    @patch(
        "apps.platform_runtime.tenant_retention_playbooks.resolve_tenant_lifecycle_state"
    )
    def test_expansion_ready_outreach_creates_action(self, mock_resolve):
        s = self._school(slug_suffix="expand")
        mock_resolve.return_value = {
            "state": STATE_EXPANSION_READY,
            "reasons": ["expansion_depth"],
            "event_hints": {},
        }
        n = evaluate_playbooks_for_school(s)
        self.assertGreaterEqual(n, 1)
        self.assertTrue(
            TenantRetentionPlaybookAction.objects.filter(
                playbook_code=PLAYBOOK_EXPANSION_READY_OUTREACH,
                school=s,
            ).exists()
        )

    def test_duplicate_actions_avoided_same_day(self):
        s = self._school(slug_suffix="dedupe")
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
        evaluate_playbooks_for_school(s)
        evaluate_playbooks_for_school(s)
        qs = TenantRetentionPlaybookAction.objects.filter(
            playbook_code=PLAYBOOK_PAYMENT_FAILED_FOLLOW_UP,
            school=s,
        )
        self.assertEqual(qs.count(), 1)
