"""North Star SLICE 14 — regional locale, RTL hints, shell context."""

import uuid

from django.test import Client, TestCase, override_settings, RequestFactory
from django.urls import reverse, set_urlconf
from django.utils import translation

from apps.accounts.models import Permission, User
from apps.siteconfig.context_processors import region_settings
from apps.siteconfig.models import Plan
from apps.siteconfig.models_platform_catalog import RegionConfig
from apps.siteconfig.regional_ui import (
    augment_region_shell_context,
    get_effective_locale_for_school,
    get_text_direction_for_school,
    is_rtl_locale,
)
from apps.schools.models import School


_T_HOST = "r14.runmycampus.com"
_ALLOWED = ("testserver", "127.0.0.1", "localhost", _T_HOST)


@override_settings(ALLOWED_HOSTS=list(_ALLOWED))
class RegionalUiHelpersTests(TestCase):
    databases = {"default"}

    def test_default_school_none_effective_locale_en(self):
        self.assertEqual(get_effective_locale_for_school(None), "en")

    def test_ar_locale_implies_rtl_direction(self):
        translation.activate("ar")
        try:
            self.assertTrue(is_rtl_locale("ar"))
            self.assertEqual(get_text_direction_for_school(None), "rtl")
        finally:
            translation.deactivate()

    def test_ar_cm_and_eg_variants_rtl(self):
        for code in ("ar-CM", "ar_EG", "ar-SA"):
            self.assertTrue(
                is_rtl_locale(code),
                msg=code,
            )

    def test_augment_policy_rtl(self):
        ctx = augment_region_shell_context(
            {"is_rtl": True, "default_language": "en"},
            RequestFactory().get("/"),
        )
        self.assertEqual(ctx["rmc_text_direction"], "rtl")

    def test_augment_ltr_for_english(self):
        ctx = augment_region_shell_context(
            {"is_rtl": False, "default_language": "en-US"},
            RequestFactory().get("/"),
        )
        self.assertEqual(ctx["rmc_text_direction"], "ltr")


@override_settings(ALLOWED_HOSTS=list(_ALLOWED))
class RegionalUiShellMarkerTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="R14",
            slug="r14-p",
            included_features=["core"],
            is_active=True,
        )
        cls.region = RegionConfig.objects.create(
            code="R14",
            name="Reg14",
            timezone="UTC",
            default_currency="USD",
        )
        cls.school = School.objects.create(
            name="Regional High",
            slug="r14",
            subdomain="r14",
            is_active=True,
            plan=cls.plan,
            default_region=cls.region,
        )

    def test_portal_base_has_dir_attr_via_curriculum_page(self):
        u = User.objects.create_user(
            username=f"adm_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        c = Client(HTTP_HOST=_T_HOST)
        c.force_login(u)
        url = reverse("siteconfig:curriculum_templates", urlconf="config.tenant_urls")
        body = c.get(url).content.decode("utf-8", errors="replace")
        self.assertIn('dir="ltr"', body)
        self.assertIn('data-rmc-regional-ui="1"', body)
        self.assertIn('data-rmc-regional-ui-status="1"', body)

    def test_control_plane_skeleton_marker_via_runtime_hub_request(self):
        """Exercise ``region_settings`` merge path used by shells."""
        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        user = User.objects.create_user(
            username=f"rt_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            is_staff=False,
        )
        user.feature_permissions.add(manage_perm)
        factory = RequestFactory()
        request = factory.get("/siteconfig/configuration/runtime/")
        request.user = user
        request.school = self.school
        ctx = region_settings(request)
        self.assertEqual(ctx.get("rmc_text_direction"), "ltr")
        self.assertTrue(ctx.get("rmc_locale"))

    def test_runtime_hub_template_contains_regional_evidence_strip(self):
        from apps.siteconfig.views_tenant_runtime_hub import tenant_runtime_configuration_hub

        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        user = User.objects.create_user(
            username=f"rtc_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            is_staff=False,
        )
        user.feature_permissions.add(manage_perm)
        request = RequestFactory().get("/siteconfig/configuration/runtime/")
        request.user = user
        request.school = self.school
        set_urlconf("config.tenant_urls")
        try:
            resp = tenant_runtime_configuration_hub(request)
        finally:
            set_urlconf(None)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertEqual(resp.status_code, 200)
        self.assertIn('data-rmc-regional-ui-status="1"', body)
