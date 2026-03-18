"""Insight anomalies JSON API."""

import json

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.api.insight_anomalies_api import InsightAnomaliesAPIView
from apps.schools.models import School


class InsightAnomaliesAPIViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="API School",
            slug="api-school",
            subdomain="api-school",
            is_active=True,
        )
        self.user = User.objects.create_user(username="insight_api_u", password="x")

    def test_anonymous_not_200(self):
        req = self.factory.get("/api/internal/insight-anomalies/")
        req.user = AnonymousUser()
        resp = InsightAnomaliesAPIView.as_view()(req)
        self.assertNotEqual(resp.status_code, 200)

    def test_authenticated_returns_anomalies_key(self):
        req = self.factory.get("/api/internal/insight-anomalies/")
        req.user = self.user
        req.school = self.school
        resp = InsightAnomaliesAPIView.as_view()(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode())
        self.assertIn("anomalies", data)
        self.assertIsInstance(data["anomalies"], list)
