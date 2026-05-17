"""Wave 6 tests — portal AI surface views.

Covers: semantic search renders with/without query, hydration filters
cross-tenant results, risk-drivers view shows contributions or empty
state, grade-outlook view groups predictions by subject.
"""

from __future__ import annotations

import unittest.mock as mock

from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.analytics.models import GradePrediction, RiskFactor
from apps.people.models import StudentProfile
from apps.portal import views_ai_surfaces
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class _FixtureBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.region, _ = RegionConfig.objects.get_or_create(
            code=f"P6{abs(hash(cls.__name__)) % 9999}",
            defaults={
                "name": "P6 Region", "default_language": "en",
                "timezone": "UTC", "date_format": "DD/MM/YYYY",
            },
        )
        cls.school = School.objects.create(
            name="P6 School",
            slug=f"p6-{abs(hash(cls.__name__))}",
            subdomain=f"p6-{abs(hash(cls.__name__))}",
            is_active=True, default_region=cls.region,
        )
        cls.user = User.objects.create_user(
            username=f"p6_u_{abs(hash(cls.__name__))}",
            email="u@example.com", password="p",
        )
        cls.student_user = User.objects.create_user(
            username=f"p6_su_{abs(hash(cls.__name__))}",
            email="su@example.com", password="p",
        )
        cls.student = StudentProfile.objects.create(
            school=cls.school, user=cls.student_user,
            first_name="Pat", last_name="Sample",
            student_code=f"P6-{abs(hash(cls.__name__))}",
        )

    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, path):
        req = self.factory.get(path)
        req.user = self.user
        req.school = self.school
        return req


class SemanticSearchViewTests(_FixtureBase):
    def test_search_no_query_shows_prompt(self):
        req = self._request("/portal/students/search/")
        resp = views_ai_surfaces.semantic_student_search(req)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Type at least", resp.content)

    def test_search_with_query_renders_results(self):
        # Mock search_students to return a synthetic ranking.
        ranking = [{
            "student_id": str(self.student.pk),
            "score": 0.92,
            "summary": "Pat Sample, code P6-x.",
        }]
        with mock.patch(
            "apps.analytics.semantic_search.search_students",
            return_value=ranking,
        ):
            req = self._request("/portal/students/search/?q=patrick+sample")
            resp = views_ai_surfaces.semantic_student_search(req)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Pat", resp.content)
        self.assertIn(b"Sample", resp.content)
        self.assertIn(b"0.920", resp.content)

    def test_search_handles_failure_gracefully(self):
        with mock.patch(
            "apps.analytics.semantic_search.search_students",
            side_effect=ValueError("backend down"),
        ):
            req = self._request("/portal/students/search/?q=pat")
            resp = views_ai_surfaces.semantic_student_search(req)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"temporarily unavailable", resp.content)

    def test_search_no_tenant_400(self):
        req = self.factory.get("/portal/students/search/")
        req.user = self.user
        req.school = None
        resp = views_ai_surfaces.semantic_student_search(req)
        self.assertEqual(resp.status_code, 400)

    def test_hydration_drops_cross_tenant_ids(self):
        other_school = School.objects.create(
            name="Other P6",
            slug=f"p6-other-{id(self)}",
            subdomain=f"p6-other-{id(self)}",
            is_active=True, default_region=self.region,
        )
        u = User.objects.create_user(
            username=f"p6_other_{id(self)}",
            email="otheru@example.com", password="p",
        )
        cross = StudentProfile.objects.create(
            school=other_school, user=u,
            first_name="Cross", last_name="Tenant",
            student_code=f"X-{id(self)}",
        )
        ranking = [
            {"student_id": str(cross.pk), "score": 0.99, "summary": "Cross row"},
            {"student_id": str(self.student.pk), "score": 0.5, "summary": "ours"},
        ]
        with mock.patch(
            "apps.analytics.semantic_search.search_students",
            return_value=ranking,
        ):
            req = self._request("/portal/students/search/?q=anything")
            resp = views_ai_surfaces.semantic_student_search(req)
        # Cross-tenant row never reaches the template.
        self.assertNotIn(b"Cross", resp.content)
        self.assertIn(b"Pat", resp.content)


class RiskDriversViewTests(_FixtureBase):
    def test_no_risk_factor_shows_empty_state(self):
        req = self._request(f"/portal/student/{self.student.pk}/risk-drivers/")
        resp = views_ai_surfaces.student_risk_drivers(
            req, student_id=self.student.pk,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"No risk score has been computed", resp.content)

    def test_heuristic_only_shows_baseline_notice(self):
        RiskFactor.objects.create(
            school=self.school, student=self.student,
            score=55.0, reason_summary="heuristic test",
            feature_contributions=[],  # empty → heuristic served
        )
        req = self._request(f"/portal/student/{self.student.pk}/risk-drivers/")
        resp = views_ai_surfaces.student_risk_drivers(
            req, student_id=self.student.pk,
        )
        self.assertIn(b"heuristic baseline", resp.content)
        self.assertIn(b"heuristic test", resp.content)

    def test_ml_contributions_rendered(self):
        RiskFactor.objects.create(
            school=self.school, student=self.student,
            score=82.0, reason_summary="ml served",
            feature_contributions=[
                {"name": "attendance_rate", "value": 0.62,
                 "importance": 0.31, "direction": "elevates"},
                {"name": "avg_evaluation_score", "value": 54.0,
                 "importance": 0.22, "direction": "elevates"},
            ],
            model_version="test_model_v1",
        )
        req = self._request(f"/portal/student/{self.student.pk}/risk-drivers/")
        resp = views_ai_surfaces.student_risk_drivers(
            req, student_id=self.student.pk,
        )
        self.assertIn(b"attendance_rate", resp.content)
        self.assertIn(b"Elevates risk", resp.content)
        self.assertIn(b"test_model_v1", resp.content)

    def test_cross_tenant_student_404(self):
        from django.http import Http404
        other = School.objects.create(
            name="Other RD",
            slug=f"rd-other-{id(self)}",
            subdomain=f"rd-other-{id(self)}",
            is_active=True, default_region=self.region,
        )
        u = User.objects.create_user(
            username=f"rd_other_{id(self)}",
            email="rd_other@example.com", password="p",
        )
        cross = StudentProfile.objects.create(
            school=other, user=u,
            first_name="Cross", last_name="Y",
            student_code=f"CR-{id(self)}",
        )
        req = self._request(f"/portal/student/{cross.pk}/risk-drivers/")
        with self.assertRaises(Http404):
            views_ai_surfaces.student_risk_drivers(req, student_id=cross.pk)


class GradeOutlookViewTests(_FixtureBase):
    def test_no_predictions_shows_empty(self):
        req = self._request(f"/portal/student/{self.student.pk}/grade-outlook/")
        resp = views_ai_surfaces.student_grade_outlook(
            req, student_id=self.student.pk,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"No grade predictions", resp.content)

    def test_predictions_grouped_by_subject(self):
        from apps.academics.models import AcademicYear, Subject, Term
        year = AcademicYear.objects.create(
            name=f"P6Y-{id(self)}",
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=365)).date(),
        )
        term = Term.objects.create(
            name=f"P6T-{id(self)}", academic_year=year,
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=90)).date(),
        )
        math = Subject.objects.create(name=f"Math-{id(self)}")
        GradePrediction.objects.create(
            school=self.school, student=self.student,
            subject=math, academic_year=year, term=term,
            predicted_grade=72.5,
            confidence_low=65.0, confidence_high=80.0,
            reason_summary="mid-term avg 70",
            model_version="grade_v1",
        )
        req = self._request(f"/portal/student/{self.student.pk}/grade-outlook/")
        resp = views_ai_surfaces.student_grade_outlook(
            req, student_id=self.student.pk,
        )
        self.assertIn(b"72.5", resp.content)
        self.assertIn(b"65.0", resp.content)
        self.assertIn(b"grade_v1", resp.content)
