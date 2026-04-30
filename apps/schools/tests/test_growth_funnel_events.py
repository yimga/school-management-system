"""Growth funnel event ordering and idempotency (payment processor ref)."""

from __future__ import annotations

from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.schools.funnel_events import (
    record_payment_outcome_signal,
    record_school_funnel_once,
)
from apps.schools.models import MarketingFunnelEvent, School


class GrowthFunnelPaymentIdempotencyTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.school = School.objects.create(
            name="Funnel School",
            slug="funnel-school",
            subdomain="funnel-school",
            is_active=True,
        )

    def test_duplicate_payment_success_same_source_ref_deduped(self):
        record_payment_outcome_signal(
            self.school,
            success=True,
            metadata={"processor_source_ref": "evt_dup_1"},
        )
        record_payment_outcome_signal(
            self.school,
            success=True,
            metadata={"processor_source_ref": "evt_dup_1"},
        )
        n = MarketingFunnelEvent.objects.filter(
            school=self.school,
            event_type="payment_success",
            metadata__processor_source_ref="evt_dup_1",
        ).count()
        self.assertEqual(n, 1)


class GrowthFunnelOnboardingOnceTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Onb School",
            slug="onb-school",
            subdomain="onb-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="onb_u",
            email="onb@example.edu",
            password="x" * 8,
        )

    def test_onboarding_start_deduped_per_school(self):
        req = self.factory.get("/demo/flow/attendance/")
        sess = SessionStore()
        sess.create()
        req.session = sess
        req.user = self.user
        ok1 = record_school_funnel_once(
            "onboarding_start",
            self.school,
            req,
            user=self.user,
            metadata={"t": 1},
        )
        ok2 = record_school_funnel_once(
            "onboarding_start",
            self.school,
            req,
            user=self.user,
            metadata={"t": 2},
        )
        self.assertTrue(ok1)
        self.assertFalse(ok2)
        self.assertEqual(
            MarketingFunnelEvent.objects.filter(
                school=self.school, event_type="onboarding_start"
            ).count(),
            1,
        )
