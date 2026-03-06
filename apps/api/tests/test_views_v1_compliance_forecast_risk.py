"""
Tests for API v1: ComplianceExportSchoolView, EnrollmentForecastView, RiskThresholdsConfigView,
and (indirectly) intervention action center risk_band using get_risk_band_for_school.
"""
import json
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.analytics.models import RiskThresholds, InterventionLog, RiskFactor
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import SiteSettings


def _tenant_v1_url(school_slug: str, name: str, **kwargs) -> str:
    del school_slug
    return reverse(f"api_v1:{name}", **kwargs)


def _tenant_host(school_slug: str) -> dict[str, str]:
    return {"HTTP_HOST": f"{school_slug}.runmycampus.com"}


class ComplianceExportSchoolViewTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Export School",
            slug="export-school",
            subdomain="export-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="admin@export.test",
            email="admin@export.test",
            password="testpass",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role="ADMIN",
            is_primary=True,
        )

    def test_export_school_requires_auth(self):
        url = _tenant_v1_url(self.school.slug, "compliance-export-school")
        response = self.client.post(url, content_type="application/json", **_tenant_host(self.school.slug))
        self.assertEqual(response.status_code, 401)

    def test_export_school_returns_summary(self):
        self.client.force_login(self.user)
        url = _tenant_v1_url(self.school.slug, "compliance-export-school")
        response = self.client.post(url, content_type="application/json", **_tenant_host(self.school.slug))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("school_id"), str(self.school.id))
        self.assertIn("summary", data)
        self.assertIn("students", data["summary"])
        self.assertIn("invoices", data["summary"])
        self.assertIn("payments", data["summary"])


class EnrollmentForecastViewTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Forecast School",
            slug="forecast-school",
            subdomain="forecast-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="admin@forecast.test",
            password="testpass",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role="ADMIN",
            is_primary=True,
        )

    def _enable_forecast(self):
        site = SiteSettings.get_solo()
        flags = dict(site.backend_feature_flags or {})
        flags["enable_enrollment_forecast_api"] = True
        site.backend_feature_flags = flags
        site.save(update_fields=["backend_feature_flags", "updated_at"])

    def test_forecast_disabled_returns_404(self):
        url = _tenant_v1_url(self.school.slug, "enrollment-forecast")
        response = self.client.get(url, **_tenant_host(self.school.slug))
        self.assertEqual(response.status_code, 404)

    def test_forecast_requires_auth_when_enabled(self):
        self._enable_forecast()
        url = _tenant_v1_url(self.school.slug, "enrollment-forecast")
        response = self.client.get(url, **_tenant_host(self.school.slug))
        self.assertEqual(response.status_code, 401)

    def test_forecast_returns_current_enrollment(self):
        self._enable_forecast()
        self.client.force_login(self.user)
        url = _tenant_v1_url(self.school.slug, "enrollment-forecast")
        response = self.client.get(url, **_tenant_host(self.school.slug))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("current_enrollment", data)
        self.assertIn("forecasts", data)
        self.assertEqual(data["current_enrollment"], 0)


class RiskThresholdsConfigViewTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Risk School",
            slug="risk-school",
            subdomain="risk-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="admin@risk.test",
            password="testpass",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role="ADMIN",
            is_primary=True,
        )

    def test_get_requires_auth(self):
        url = _tenant_v1_url(self.school.slug, "config-risk-thresholds")
        response = self.client.get(url, **_tenant_host(self.school.slug))
        self.assertEqual(response.status_code, 401)

    def test_get_returns_defaults_when_no_thresholds(self):
        self.client.force_login(self.user)
        url = _tenant_v1_url(self.school.slug, "config-risk-thresholds")
        response = self.client.get(url, **_tenant_host(self.school.slug))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["amber_min"], 50.0)
        self.assertEqual(data["red_min"], 80.0)

    def test_get_returns_saved_thresholds(self):
        RiskThresholds.objects.create(
            school=self.school,
            amber_min=Decimal("40"),
            red_min=Decimal("70"),
        )
        self.client.force_login(self.user)
        url = _tenant_v1_url(self.school.slug, "config-risk-thresholds")
        response = self.client.get(url, **_tenant_host(self.school.slug))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["amber_min"], 40.0)
        self.assertEqual(data["red_min"], 70.0)

    def test_patch_updates_thresholds(self):
        self.client.force_login(self.user)
        url = _tenant_v1_url(self.school.slug, "config-risk-thresholds")
        response = self.client.patch(
            url,
            data=json.dumps({"amber_min": 45, "red_min": 75}),
            content_type="application/json",
            **_tenant_host(self.school.slug),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["amber_min"], 45.0)
        self.assertEqual(data["red_min"], 75.0)
        th = RiskThresholds.objects.get(school=self.school)
        self.assertEqual(float(th.amber_min), 45.0)
        self.assertEqual(float(th.red_min), 75.0)


class InterventionActionCenterRiskBandTests(TestCase):
    """Action center uses get_risk_band_for_school for risk_band; test that band is returned."""

    def setUp(self):
        self.school = School.objects.create(
            name="Action School",
            slug="action-school",
            subdomain="action-school",
            is_active=True,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="At",
            last_name="Risk",
            student_code="RISK001",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="admin@action.test",
            password="testpass",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role="ADMIN",
            is_primary=True,
        )
        self.intervention = InterventionLog.objects.create(
            school=self.school,
            student=self.student,
            trigger_reason="Low attendance",
            action_taken="Email",
            status=InterventionLog.Status.ONGOING,
        )
        self.risk_factor = RiskFactor.objects.create(
            school=self.school,
            student=self.student,
            score=Decimal("85.00"),
            reason_summary="Absent 5/10 days",
        )

    def test_action_center_includes_risk_band(self):
        self.client.force_login(self.user)
        url = _tenant_v1_url(self.school.slug, "intervention-action-center")
        response = self.client.get(url, **_tenant_host(self.school.slug))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("interventions", data)
        self.assertGreaterEqual(len(data["interventions"]), 1)
        item = data["interventions"][0]
        self.assertIn("risk_band", item)
        self.assertEqual(item["risk_band"], "red")
        self.assertEqual(item["risk_score"], 85.0)

    def test_action_center_uses_custom_thresholds_when_set(self):
        RiskThresholds.objects.create(
            school=self.school,
            amber_min=Decimal("60"),
            red_min=Decimal("90"),
        )
        self.client.force_login(self.user)
        url = _tenant_v1_url(self.school.slug, "intervention-action-center")
        response = self.client.get(url, **_tenant_host(self.school.slug))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(len(data["interventions"]), 1)
        item = data["interventions"][0]
        self.assertEqual(item["risk_band"], "amber")
        self.assertEqual(item["risk_score"], 85.0)
