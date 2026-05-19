"""Analytics viz overview JSON API."""

import json
import uuid

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.api.analytics_viz_api import AnalyticsVizOverviewAPIView
from apps.schools.models import School, SchoolMembership


class AnalyticsVizOverviewAPIViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Viz API School",
            slug="viz-api-school",
            subdomain="viz-api-school",
            is_active=True,
        )
        self.user = User.objects.create_user(username="viz_api_u", password="x")

    def test_anonymous_not_200(self):
        req = self.factory.get("/api/internal/analytics-viz/overview/?tenant=demo")
        req.user = AnonymousUser()
        resp = AnalyticsVizOverviewAPIView.as_view()(req)
        self.assertNotEqual(resp.status_code, 200)

    def test_authenticated_returns_bundle(self):
        req = self.factory.get(
            "/api/internal/analytics-viz/overview/?tenant=marketing-demo"
        )
        req.user = self.user
        req.school = self.school
        resp = AnalyticsVizOverviewAPIView.as_view()(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode())
        self.assertIn("bundle", data)
        bundle = data["bundle"]
        self.assertEqual(bundle["tenantId"], "marketing-demo")
        self.assertIn("kpis", bundle)
        self.assertIn("timeseries", bundle)
        self.assertGreater(len(bundle["timeseries"]), 0)

    def test_missing_tenant_400(self):
        req = self.factory.get("/api/internal/analytics-viz/overview/")
        req.user = self.user
        resp = AnalyticsVizOverviewAPIView.as_view()(req)
        self.assertEqual(resp.status_code, 400)

    def test_foreign_tenant_slug_denied(self):
        uid = uuid.uuid4().hex[:8]
        school_b = School.objects.create(
            name=f"Viz Foreign B {uid}",
            slug=f"viz-foreign-b-{uid}",
            subdomain=f"vizfb{uid}",
            is_active=True,
        )
        req = self.factory.get(
            f"/api/internal/analytics-viz/overview/?tenant={school_b.slug}"
        )
        req.user = self.user
        req.school = self.school
        resp = AnalyticsVizOverviewAPIView.as_view()(req)
        self.assertEqual(resp.status_code, 403)
        data = json.loads(resp.content.decode())
        self.assertEqual(data.get("error"), "Forbidden")

    def test_own_tenant_slug_allowed_with_membership(self):
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        req = self.factory.get(
            f"/api/internal/analytics-viz/overview/?tenant={self.school.slug}"
        )
        req.user = self.user
        req.school = self.school
        resp = AnalyticsVizOverviewAPIView.as_view()(req)
        self.assertEqual(resp.status_code, 200)
