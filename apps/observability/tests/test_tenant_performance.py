"""Tests for tenant performance trust dashboard (T1)."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.observability.tenant_performance import build_tenant_performance_snapshot
from apps.schools.models import School, SchoolMembership

User = get_user_model()

_T_HOST = "perf-trust.runmycampus.com"


class TenantPerformanceSnapshotTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Perf Snapshot School",
            slug="perf-snapshot-school",
            subdomain="perf-snapshot-school",
            is_active=True,
            is_approved=True,
        )

    def test_snapshot_has_timeline_and_commitments(self):
        snap = build_tenant_performance_snapshot(self.school)
        self.assertEqual(len(snap.timeline_days), 7)
        self.assertIn("availability_tier", snap.as_dict())
        self.assertTrue(snap.platform_commitments)
        self.assertTrue(snap.revision)

    def test_snapshot_without_school_degrades_safely(self):
        snap = build_tenant_performance_snapshot(None)
        self.assertEqual(snap.school_slug, "")
        self.assertEqual(len(snap.timeline_days), 7)


class TenantPerformanceUrlTests(SimpleTestCase):
    def test_named_routes_resolve_on_tenant_urlconf(self):
        dash = reverse("accounts:tenant_performance_dashboard", urlconf="config.tenant_urls")
        api = reverse("accounts:tenant_performance_json", urlconf="config.tenant_urls")
        self.assertIn("performance", dash)
        self.assertIn("performance.json", api)


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST],
    CONVERSION_LOCK_STRICT=False,
    CONVERSION_LOCK_ALL_SCHOOLS=False,
    DISABLE_SCHOOL_ACTIVATION_GATE=True,
)
class TenantPerformanceHttpTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Perf HTTP School",
            slug="perf-http",
            subdomain="perf-http",
            is_active=True,
            is_approved=True,
        )
        from apps.accounts.models import Permission as FeaturePermission

        cls.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_T_HOST, raise_request_exception=False)
        self.admin = User.objects.create_user(
            username="perf-admin",
            password="Test1234!",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.admin.feature_permissions.add(self.perm_settings)
        SchoolMembership.objects.create(
            user=self.admin,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )

    def _login(self):
        self.client.login(username="perf-admin", password="Test1234!")
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.update_or_create(
            user=self.admin,
            name="perf-trust-test",
            defaults={"confirmed": True},
        )
        session = self.client.session
        session["mfa_verified"] = True
        session["school_id"] = str(self.school.id)
        session.save()

    def test_dashboard_requires_login(self):
        url = reverse("accounts:tenant_performance_dashboard", urlconf="config.tenant_urls")
        self.assertEqual(self.client.get(url).status_code, 302)
        self._login()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rmc-tperf")
        self.assertContains(response, "Platform commitments")

    def test_json_endpoint_returns_snapshot(self):
        url = reverse("accounts:tenant_performance_json", urlconf="config.tenant_urls")
        self._login()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("timeline_days", payload)
        self.assertIn("experience_score_pct", payload)
