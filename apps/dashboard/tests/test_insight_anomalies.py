from django.test import RequestFactory, TestCase

from apps.dashboard.services.insight_anomalies import build_insight_anomaly_cards
from apps.schools.models import School


class InsightAnomaliesServiceTests(TestCase):
    def test_no_school_returns_empty(self):
        rf = RequestFactory()
        req = rf.get("/")
        req.school = None
        self.assertEqual(build_insight_anomaly_cards(req), [])

    def test_with_school_returns_list_not_crash(self):
        rf = RequestFactory()
        req = rf.get("/")
        req.school = School.objects.create(
            name="A",
            slug="a",
            subdomain="a",
            is_active=True,
        )
        out = build_insight_anomaly_cards(req, limit=3)
        self.assertIsInstance(out, list)
