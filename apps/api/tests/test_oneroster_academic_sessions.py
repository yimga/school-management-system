"""OneRoster academicSessions (Phase J / district-class roster)."""

import json
from datetime import date

from django.test import RequestFactory, TestCase

from apps.academics.models import AcademicYear, Term
from apps.api.oneroster_views import academic_sessions
from apps.integrations_marketplace.models import ServiceIntegration
from apps.schools.models import School


class OneRosterAcademicSessionsTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="OR School",
            slug="or-school",
            subdomain="or-school",
            is_active=True,
        )
        year = AcademicYear.objects.create(
            name="2025/26",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
            school=self.school,
        )
        Term.objects.create(
            school=self.school,
            academic_year=year,
            name="FIRST",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 20),
        )
        ServiceIntegration.objects.create(
            school=self.school,
            service_name="oneroster",
            service_type=ServiceIntegration.ServiceType.OAUTH,
            is_active=True,
            config={"bearer_token": "test-secret-token-or"},
        )

    def test_academic_sessions_403_without_bearer(self):
        req = self.factory.get(
            f"/api/oneroster/v1p1/academicSessions?school_slug={self.school.slug}"
        )
        resp = academic_sessions(req)
        self.assertEqual(resp.status_code, 403)

    def test_academic_sessions_returns_sessions(self):
        req = self.factory.get(
            f"/api/oneroster/v1p1/academicSessions?school_slug={self.school.slug}",
            HTTP_AUTHORIZATION="Bearer test-secret-token-or",
        )
        resp = academic_sessions(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode())
        self.assertEqual(data.get("imsx_codeMajor"), "success")
        sessions = data.get("academicSessions") or []
        self.assertGreaterEqual(len(sessions), 1)
        self.assertIn("startDate", sessions[0])
