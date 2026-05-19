"""Platform guided tour API, catalog, analytics, info tags, and role variants."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.schools.models import School
from apps.siteconfig.models import FeatureUsageEvent, TourStep
from apps.siteconfig.tour_catalog import CATALOGS, marketing_product_tour_steps
from apps.siteconfig.tour_context import resolve_backend_tour_context
from apps.siteconfig.ui_field_help import get_ui_field_help
from apps.siteconfig.views_tour import control_plane_default_tour_steps

User = get_user_model()

_TOUR_TEST_HOST = "tour-test.runmycampus.com"
_INFO_TEST_HOST = "info-school.runmycampus.com"
_ANALYTICS_TEST_HOST = "tour-analytics.runmycampus.com"
_TENANT_TEST_HOSTS = [
    "testserver",
    "127.0.0.1",
    "localhost",
    _TOUR_TEST_HOST,
    _INFO_TEST_HOST,
    _ANALYTICS_TEST_HOST,
]


def _tenant_api_url(name: str, query: str = "") -> str:
    return reverse(name, urlconf="config.tenant_urls") + query


def _tenant_login(client: Client, user, password: str = "Test1234!") -> None:
    TOTPDevice.objects.update_or_create(
        user=user, name="test-mfa", defaults={"confirmed": True}
    )
    client.login(username=user.username, password=password)
    session = client.session
    session["mfa_verified"] = True
    session.save()


class TourCatalogTests(TestCase):
    def test_backend_role_variants_exist(self):
        for ctx in (
            "backend_dashboard_admin",
            "backend_dashboard_leadership",
            "backend_dashboard_operations",
        ):
            self.assertIn(ctx, CATALOGS)
            self.assertGreater(len(CATALOGS[ctx]), 0)

    def test_portal_role_catalogs_exist(self):
        for ctx in ("teacher_portal", "parent_portal", "student_portal"):
            self.assertIn(ctx, CATALOGS)
            self.assertGreaterEqual(len(CATALOGS[ctx]), 2)

    def test_marketing_product_tour_from_json(self):
        steps = marketing_product_tour_steps()
        self.assertGreaterEqual(len(steps), 5)
        self.assertTrue(steps[0]["selector"].startswith("[data-tour='product-tour-"))

    def test_backend_catalog_selectors_match_data_tour_slugs(self):
        steps = CATALOGS["backend_dashboard_admin"]
        for step in steps:
            self.assertIn("data-tour=", step["selector"])


class TourContextTests(SimpleTestCase):
    def test_leadership_role_context(self):
        u = type("U", (), {"is_authenticated": True, "is_superuser": False, "role": "PRINCIPAL"})()
        self.assertEqual(resolve_backend_tour_context(u), "backend_dashboard_leadership")

    def test_teacher_gets_no_backend_autostart(self):
        u = type("U", (), {"is_authenticated": True, "is_superuser": False, "role": "TEACHER"})()
        self.assertEqual(resolve_backend_tour_context(u), "")


@override_settings(ALLOWED_HOSTS=_TENANT_TEST_HOSTS)
class TourStepsApiTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Tour Test School",
            slug="tour-test",
            subdomain="tour-test",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username="tour_admin",
            password="Test1234!",
            role="ADMIN",
        )
        self.principal = User.objects.create_user(
            username="tour_principal",
            password="Test1234!",
            role="PRINCIPAL",
        )
        self.client = Client(HTTP_HOST=_TOUR_TEST_HOST)

    def test_admin_backend_context_resolves(self):
        _tenant_login(self.client, self.admin)
        url = _tenant_api_url("siteconfig:tour_steps_api", "?context=backend_dashboard")
        data = self.client.get(url).json()
        self.assertEqual(data["context"], "backend_dashboard_admin")

    def test_principal_gets_leadership_steps(self):
        _tenant_login(self.client, self.principal)
        url = _tenant_api_url("siteconfig:tour_steps_api", "?context=backend_dashboard")
        data = self.client.get(url).json()
        self.assertEqual(data["context"], "backend_dashboard_leadership")
        codes = {s["code"] for s in data["steps"]}
        self.assertIn("backend-kpi-strip", codes)

    def test_teacher_portal_steps(self):
        _tenant_login(self.client, self.admin)
        url = _tenant_api_url("siteconfig:tour_steps_api", "?context=teacher_portal")
        data = self.client.get(url).json()
        self.assertGreaterEqual(len(data["steps"]), 3)
        self.assertIn("teacher-attention", {s["code"] for s in data["steps"]})

    def test_db_steps_use_stored_selector_and_context(self):
        TourStep.objects.create(
            school=self.school,
            context="backend_dashboard_admin",
            code="dashboard-main",
            title="Custom welcome",
            selector="[data-tour='dashboard-main']",
            sort_order=1,
        )
        _tenant_login(self.client, self.admin)
        url = _tenant_api_url("siteconfig:tour_steps_api", "?context=backend_dashboard_admin")
        data = self.client.get(url).json()
        self.assertEqual(len(data["steps"]), 1)
        self.assertEqual(data["steps"][0]["title"], "Custom welcome")


@override_settings(ROOT_URLCONF="config.public_urls", ALLOWED_HOSTS=["runmycampus.com", "testserver"])
class TourStepsPublicApiTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST="runmycampus.com")

    def test_marketing_product_tour_public(self):
        url = reverse("tour_steps_public_api") + "?context=marketing_product_tour"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(len(data["steps"]), 5)

    def test_forbidden_context(self):
        url = reverse("tour_steps_public_api") + "?context=backend_dashboard_admin"
        self.assertEqual(self.client.get(url).status_code, 403)


@override_settings(ALLOWED_HOSTS=_TENANT_TEST_HOSTS)
class TourInfoTagTests(TestCase):
    def setUp(self):
        School.objects.create(
            name="Info School",
            slug="info-school",
            subdomain="info-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="info_user",
            password="Test1234!",
            role="ADMIN",
        )
        self.client = Client(HTTP_HOST=_INFO_TEST_HOST)
        _tenant_login(self.client, self.user)

    def test_static_registry_lookup(self):
        help_data = get_ui_field_help("invoice", "status")
        self.assertTrue(help_data.get("title"))
        self.assertTrue(help_data.get("body"))

    def test_info_api(self):
        url = _tenant_api_url("siteconfig:tour_info_tag_api", "?entity=invoice&field=status")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("ok"))


@override_settings(ALLOWED_HOSTS=_TENANT_TEST_HOSTS)
class TourAnalyticsApiTests(TestCase):
    def setUp(self):
        School.objects.create(
            name="Tour Analytics School",
            slug="tour-analytics",
            subdomain="tour-analytics",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="tour_analytics_user",
            password="Test1234!",
            role="TEACHER",
        )
        self.client = Client(HTTP_HOST=_ANALYTICS_TEST_HOST)
        _tenant_login(self.client, self.user)

    def test_tour_start_event_recorded(self):
        url = _tenant_api_url("siteconfig:tour_analytics_api")
        resp = self.client.post(url, {"event": "start", "context": "teacher_portal"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            FeatureUsageEvent.objects.filter(feature_code="tour:teacher_portal:start").exists()
        )


class ControlPlaneTourCatalogTests(TestCase):
    def test_super_trust_requires_control_plane_access(self):
        user = User.objects.create_user(username="plain", password="x", role="TEACHER")
        self.assertEqual(control_plane_default_tour_steps("super_trust", user), [])

    def test_superuser_gets_trust_steps(self):
        user = User.objects.create_superuser(username="super", password="x", email="s@e.com")
        steps = control_plane_default_tour_steps("super_trust", user)
        self.assertGreaterEqual(len(steps), 2)
