"""v4.02.9 — Tenant workspace Tools edge-tray registry + shell wiring tests."""

from __future__ import annotations

from datetime import date

from django.template import Context, Template
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission as FeaturePermission, User
from apps.academics.models import AcademicYear, Term
from apps.assist_dock.registry import SURFACE_PORTAL, get_slots_for
from apps.people.models import TeacherProfile
from apps.schools.models import School, SchoolMembership
from django_otp.plugins.otp_totp.models import TOTPDevice


class TenantToolsSlotsTests(SimpleTestCase):
    EXPECTED_IDS = frozenset({"tenant-kb", "tenant-support", "tenant-command"})

    def test_portal_surface_includes_tenant_tools_slots(self) -> None:
        ids = {slot.id for slot in get_slots_for(surface=SURFACE_PORTAL, role="TEACHER")}
        missing = self.EXPECTED_IDS - ids
        self.assertFalse(missing, f"missing tenant tools slots: {sorted(missing)}")

    def test_tenant_slots_exclude_operator_notebook(self) -> None:
        ids = {slot.id for slot in get_slots_for(surface=SURFACE_PORTAL, role="TEACHER")}
        self.assertNotIn("operator-notebook", ids)
        self.assertNotIn("open-incidents", ids)


class TenantToolsCockpitDefaultsTests(SimpleTestCase):
    def test_tenant_tools_defaults_enabled_edge_tray(self) -> None:
        from apps.siteconfig.cockpit_tenant_tools import tenant_tools_defaults

        payload = tenant_tools_defaults()
        self.assertTrue(payload.get("enabled"))
        self.assertEqual(payload.get("layout"), "edge-tray")


class TenantToolsShellTemplateTests(SimpleTestCase):
    def test_tenant_partials_gate_on_non_manager_host(self) -> None:
        from django.template.loader import get_template

        scripts = get_template("partials/rmc_tenant_tools_scripts.html").template.source
        styles = get_template("partials/rmc_tenant_tools_styles.html").template.source
        for source in (scripts, styles):
            self.assertIn("request.public_host_kind != 'manager'", source)
            self.assertIn("cockpit.tenant_tools.enabled", source)

    def test_admin_base_site_includes_tenant_tools_when_enabled(self) -> None:
        from django.template.loader import get_template

        source = get_template("admin/base_site.html").template.source
        self.assertIn("rmc_tenant_tools_scripts.html", source)
        self.assertIn("cockpit.tenant_tools.enabled", source)


class TenantToolsRenderContractTests(SimpleTestCase):
    databases = {"default"}

    def setUp(self) -> None:
        self.factory = RequestFactory()

    def _tenant_request(self):
        from apps.siteconfig.cockpit_context import cockpit_context
        from apps.siteconfig.models import SiteSettings

        request = self.factory.get(
            "/t/demo-school/authentication/backend/",
            HTTP_HOST="demo-school.runmycampus.com",
        )
        request.public_host_kind = "tenant"
        site = SiteSettings(pk=1)
        site.cockpit_payload = {}
        request.SITE = site
        request.site_settings = site
        request.user = type(
            "AuthenticatedTeacher",
            (),
            {"is_authenticated": True, "is_anonymous": False},
        )()
        ctx = cockpit_context(request)
        ctx["request"] = request
        ctx["csp_nonce"] = "test-nonce"
        return ctx

    def test_page_data_renders_when_tenant_tools_enabled(self) -> None:
        ctx = self._tenant_request()
        self.assertTrue((ctx.get("cockpit") or {}).get("tenant_tools", {}).get("enabled"))
        tpl = Template(
            "{% load static %}{% include 'partials/rmc_tenant_tools_page_data.html' %}"
        )
        rendered = tpl.render(Context(ctx))
        self.assertIn('id="page-data-rmc-tenant-tools"', rendered)
        self.assertIn('"surface": "tenant"', rendered)
        self.assertIn("tenant-kb", rendered)
        self.assertIn('"tenant-command"', rendered)
        self.assertIn('"ai-copilot"', rendered)

    def test_tenant_tools_page_data_includes_primary_group(self) -> None:
        ctx = self._tenant_request()
        tpl = Template(
            "{% load static %}{% include 'partials/rmc_tenant_tools_page_data.html' %}"
        )
        rendered = tpl.render(Context(ctx))
        self.assertIn('"primary"', rendered)
        self.assertIn("tenant-kb", rendered)

    def test_scripts_partial_renders_tray_js_on_tenant_host(self) -> None:
        ctx = self._tenant_request()
        tpl = Template("{% load static %}{% include 'partials/rmc_tenant_tools_scripts.html' %}")
        rendered = tpl.render(Context(ctx))
        self.assertIn("rmc-operator-tools-tray.js", rendered)
        self.assertIn("page-data-rmc-tenant-tools", rendered)

    def test_operator_page_data_absent_on_tenant_host(self) -> None:
        ctx = self._tenant_request()
        tpl = Template(
            "{% load static marketing_public_urls %}"
            "{% include 'partials/rmc_operator_tools_page_data.html' %}"
        )
        rendered = tpl.render(Context(ctx))
        self.assertNotIn('id="page-data-rmc-operator-tools"', rendered)


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", "tenant-tools.runmycampus.com"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    ROOT_URLCONF="config.tenant_urls",
    SESSION_PINNING_ENABLED=False,
    SECURE_SSL_REDIRECT=False,
    CONVERSION_LOCK_STRICT=False,
    CONVERSION_LOCK_ALL_SCHOOLS=False,
    DISABLE_SCHOOL_ACTIVATION_GATE=True,
)
class TenantToolsTenantHttpTests(TestCase):
    """Live HTML contract on tenant portal shells (portal_base chain)."""

    _TENANT_HOST = "tenant-tools.runmycampus.com"

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Tenant Tools School",
            slug="tenant-tools",
            subdomain="tenant-tools",
            is_active=True,
        )
        cls.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        Term.objects.create(
            name=Term.Name.FIRST,
            academic_year=year,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 1),
            is_active=True,
        )
        cls.teacher = User.objects.create_user(
            username="tenant_tools_teacher",
            password="Test1234",
            role=User.Role.TEACHER,
        )
        TeacherProfile.objects.create(user=cls.teacher)
        SchoolMembership.objects.create(
            user=cls.teacher,
            school=cls.school,
            role=User.Role.TEACHER,
            is_primary=True,
        )
        cls.admin = User.objects.create_user(
            username="tenant_tools_admin",
            password="Test1234",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        cls.admin.feature_permissions.add(cls.perm_settings)
        SchoolMembership.objects.create(
            user=cls.admin,
            school=cls.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=self._TENANT_HOST, raise_request_exception=False)

    def _mark_mfa_verified(self, user: User) -> None:
        TOTPDevice.objects.update_or_create(
            user=user,
            name="tenant-tools-tray-test",
            defaults={"confirmed": True},
        )
        session = self.client.session
        session["mfa_verified"] = True
        session.save()

    def _assert_tenant_tools_in_body(self, body: str) -> None:
        self.assertIn('id="page-data-rmc-tenant-tools"', body)
        self.assertIn("rmc-operator-tools-tray.js", body)
        self.assertIn("rmc-operator-tools-tray.css", body)
        self.assertNotIn('id="page-data-rmc-operator-tools"', body)
        self.assertNotIn('data-rmc-back-to-top-policy="always"', body)

    def test_teacher_portal_ships_tenant_tools_island(self) -> None:
        self.client.force_login(self.teacher)
        response = self.client.get("/portal/teacher/")
        self.assertEqual(response.status_code, 200, msg=response.get("Location", ""))
        self._assert_tenant_tools_in_body(response.content.decode("utf-8"))

    def test_backend_dashboard_ships_tenant_tools_island(self) -> None:
        self.client.force_login(self.admin)
        self._mark_mfa_verified(self.admin)
        url = reverse("accounts:backend_dashboard", urlconf="config.tenant_urls")
        response = self.client.get(url, HTTP_HOST=self._TENANT_HOST)
        self.assertEqual(response.status_code, 200, msg=response.get("Location", ""))
        self._assert_tenant_tools_in_body(response.content.decode("utf-8"))
