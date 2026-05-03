"""Event-scale analytics bundle — tenant isolation + governed snapshots ORM-only."""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.accounts.models import Permission
from apps.analytics.event_analytics_rollups import build_event_analytics_bundle
from apps.analytics.views_governed import event_analytics_bundle_api, event_analytics_dashboard
from apps.events.models import DomainEvent
from apps.platform_runtime.models import PlatformEventLog
from apps.schools.models import School

User = get_user_model()


class EventScaleAnalyticsTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school_a = School.objects.create(
            name="Evt A",
            slug=f"evt-a-{uuid.uuid4().hex[:6]}",
            subdomain=f"evt-a-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        cls.school_b = School.objects.create(
            name="Evt B",
            slug=f"evt-b-{uuid.uuid4().hex[:6]}",
            subdomain=f"evt-b-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        cls.perm_reports, _ = Permission.objects.get_or_create(
            code="reports.manage",
            defaults={"name": "Reports manage"},
        )

    def _user_reports(self):
        u = User.objects.create_user(username="esa_" + uuid.uuid4().hex[:8], password="pw")
        u.feature_permissions.add(self.perm_reports)
        return u

    def test_domain_event_volume_is_tenant_scoped(self):
        user = self._user_reports()
        DomainEvent.objects.create(
            event_type="test.slice",
            school_id=self.school_a.pk,
            status=DomainEvent.Status.PENDING,
            payload={"k": 1},
        )
        DomainEvent.objects.create(
            event_type="test.other",
            school_id=self.school_b.pk,
            status=DomainEvent.Status.PENDING,
            payload={"k": 2},
        )
        b_a = build_event_analytics_bundle(user=user, school_id=str(self.school_a.pk), days=14)
        self.assertTrue(b_a.get("ok"))
        vol_sum_a = sum(row["count"] for row in b_a["domain_event_volume"])
        self.assertGreaterEqual(vol_sum_a, 1)

        DomainEvent.objects.create(
            event_type="test.extra_b",
            school_id=self.school_b.pk,
            status=DomainEvent.Status.PROCESSED,
            payload={},
        )
        b_a2 = build_event_analytics_bundle(user=user, school_id=str(self.school_a.pk), days=14)
        vol_sum_a2 = sum(row["count"] for row in b_a2["domain_event_volume"])
        self.assertEqual(vol_sum_a2, vol_sum_a)

    def test_bundle_contains_expected_sections(self):
        user = self._user_reports()
        PlatformEventLog.objects.create(event_type="slice.boot", school_id=str(self.school_a.pk))
        bundle = build_event_analytics_bundle(user=user, school_id=str(self.school_a.pk), days=14)
        self.assertTrue(bundle.get("ok"))
        for key in (
            "domain_event_volume",
            "platform_event_volume",
            "offline_sync_volume",
            "payment_event_volume",
            "marketplace_event_volume",
            "funnel_event_volume",
            "workflow_event_volume",
            "snapshots",
        ):
            self.assertIn(key, bundle)
        self.assertIn("domain_events_by_type", bundle["snapshots"])

    def test_event_bundle_api_requires_tenant_request(self):
        user = self._user_reports()
        rf = RequestFactory()
        req = rf.get("/analytics/governed/events/bundle.json")
        req.user = user
        resp = event_analytics_bundle_api(req)
        self.assertEqual(resp.status_code, 400)

        req.school = self.school_a
        resp2 = event_analytics_bundle_api(req)
        self.assertEqual(resp2.status_code, 200)

    def test_event_dashboard_get(self):
        user = self._user_reports()
        rf = RequestFactory()
        req = rf.get("/analytics/governed/events/")
        req.user = user
        req.school = self.school_a
        resp = event_analytics_dashboard(req)
        self.assertEqual(resp.status_code, 200)
