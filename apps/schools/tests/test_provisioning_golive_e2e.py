"""End-to-end provisioning → go-live Django tests (batch 1731)."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.customersuccess.views_tenant import execute_launch_view
from apps.registries.models import CountryRegistry
from apps.schools.models import School
from apps.schools.school_readiness import build_school_readiness
from apps.setup_studio.models import SetupProgress
from apps.setup_studio.services import _build_data_path_choices
from apps.siteconfig.models_platform_catalog import RegionConfig


@override_settings(ALLOWED_HOSTS=["*"])
class ExecuteLaunchViewE2ETests(TestCase):
    def setUp(self):
        self.region = RegionConfig.objects.create(
            code="GLV",
            name="Go-Live Region",
            default_currency="USD",
            grading_scale="0-100",
        )
        CountryRegistry.objects.get_or_create(
            code="US",
            defaults={"name": "United States", "is_active": True},
        )
        self.school = School.objects.create(
            name="Go-Live School",
            slug="golive-school",
            subdomain="golive-school",
            country_code="US",
            timezone="UTC",
            default_region=self.region,
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="golive_admin",
            password="Test1234!",
            is_staff=True,
            role=User.Role.ADMIN,
        )
        self.factory = RequestFactory()

    def _post_launch(self):
        req = self.factory.post(reverse("siteconfig:execute_launch"))
        req.user = self.user
        req.school = self.school
        middleware = SessionMiddleware(lambda r: None)
        middleware.process_request(req)
        req.session.save()
        setattr(req, "_messages", FallbackStorage(req))
        return req, execute_launch_view(req)

    @patch("apps.customersuccess.views_tenant.execute_launch")
    def test_success_redirects_to_backend_with_launched_query(self, mock_launch):
        mock_launch.return_value = {
            "ok": True,
            "school_id": self.school.pk,
            "errors": [],
            "launched_at": "2026-06-17T12:00:00+00:00",
        }
        _req, resp = self._post_launch()
        self.assertEqual(resp.status_code, 302)
        self.assertIn("launched=1", resp.url)
        self.assertIn("authentication/backend", resp.url)

    @patch("apps.customersuccess.views_tenant.execute_launch")
    def test_success_sets_session_ceremony_flag(self, mock_launch):
        mock_launch.return_value = {"ok": True, "school_id": self.school.pk, "errors": []}
        req, _resp = self._post_launch()
        self.assertTrue(req.session.get("rmc_launch_ceremony_show"))

    @patch("apps.customersuccess.views_tenant.execute_launch")
    def test_failure_redirects_to_guided_onboarding(self, mock_launch):
        mock_launch.return_value = {
            "ok": False,
            "school_id": self.school.pk,
            "errors": ["Launch readiness not met"],
        }
        _req, resp = self._post_launch()
        self.assertEqual(resp.status_code, 302)
        self.assertIn("guided-onboarding", resp.url)


class DataPathMigrationChoiceTests(TestCase):
    def test_build_data_path_includes_migrate_from_sis(self):
        step_state = {
            "data_path": {"done": False, "link": "/import/"},
            "plan_choice": {"done": True},
        }
        choices = _build_data_path_choices(school=None, step_state=step_state)
        keys = [c["key"] for c in choices]
        self.assertIn("migrate_from_sis", keys)
        migrate = next(c for c in choices if c["key"] == "migrate_from_sis")
        self.assertIn("Migration Cloud", migrate["detail"])


class SchoolReadinessLaunchedTests(TestCase):
    def setUp(self):
        self.region = RegionConfig.objects.create(
            code="LAU",
            name="Launched Region",
            default_currency="USD",
            grading_scale="0-100",
        )
        CountryRegistry.objects.get_or_create(
            code="US",
            defaults={"name": "United States", "is_active": True},
        )
        self.school = School.objects.create(
            name="Launched School",
            slug="launched-school",
            subdomain="launched-school",
            country_code="US",
            timezone="UTC",
            default_region=self.region,
            is_active=True,
        )

    def test_has_launched_true_when_progress_has_launched_at(self):
        SetupProgress.objects.create(
            school=self.school,
            launched_at=timezone.now(),
        )
        payload = build_school_readiness(self.school)
        self.assertTrue(payload.get("has_launched"))
        operate = next(p for p in payload["phases"] if p["key"] == "operate")
        self.assertTrue(operate["done"])
