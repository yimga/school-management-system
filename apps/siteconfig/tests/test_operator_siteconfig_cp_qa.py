"""SEO, responsive, and shell QA for manager-host siteconfig operator pages."""

from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission
from apps.siteconfig.models import Plan
from apps.siteconfig.models_dashboard import (
    DashboardPack,
    DashboardTemplate,
    TenantLayoutAssignment,
)
from apps.schools.models import School, SchoolMembership

_MGR = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _MGR],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class OperatorSiteconfigCpQaTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(name="Free", slug="basic", is_active=True)
        cls.school = School.objects.create(
            name="CP QA School",
            slug="cpqa",
            subdomain="cpqa",
            is_active=True,
            plan=cls.plan,
        )
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="cp_qa_op",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )
        perm, _ = Permission.objects.get_or_create(
            code="settings.feature_control",
            defaults={"name": "Feature control"},
        )
        cls.user.feature_permissions.add(perm)
        SchoolMembership.objects.create(
            user=cls.user,
            school=cls.school,
            role="ADMIN",
            is_primary=True,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_MGR)
        self.client.login(username=self.user.username, password="x" * 8)

    def _get(self, name: str, **kwargs):
        path = reverse(name, urlconf="config.manager_urls", **kwargs)
        return self.client.get(path)

    def _assert_cp_page_quality(self, resp, *, expect_title_fragment: str):
        self.assertEqual(resp.status_code, 200, msg=resp.content[:300])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-os-shell="control-plane"', body)
        self.assertIn('id="cp-main-content"', body)
        self.assertIn('name="viewport"', body)
        self.assertIn("viewport-fit=cover", body)
        self.assertIn('name="robots" content="noindex, nofollow"', body)
        self.assertIn('aria-label="Breadcrumb"', body)
        self.assertIn("operator-siteconfig-cp-body", body)
        self.assertIn(expect_title_fragment, body)
        # No duplicate workspace strip from control_plane_base default header.
        self.assertNotIn('data-rmc-os-center="manager_workspace"', body)
        # hreflang leak regression (multi-line django comment rendered as text).
        self.assertNotRegex(body, r"\{#\s*hreflang")
        self.assertNotIn("{# hreflang", body)

    def test_ai_center_seo_and_shell(self):
        resp = self._get("siteconfig:ai_center")
        self._assert_cp_page_quality(resp, expect_title_fragment="AI Center")
        self.assertIn('meta name="description"', resp.content.decode())

    def test_feature_control_panel_no_duplicate_h1_strip(self):
        resp = self._get("siteconfig:feature_control_panel")
        self._assert_cp_page_quality(resp, expect_title_fragment="Feature control")
        body = resp.content.decode("utf-8", errors="replace")
        self.assertLessEqual(len(re.findall(r"<h1\b", body, flags=re.I)), 3)

    def test_dashboard_configuration_without_school_redirects_to_super(self):
        resp = self._get("siteconfig:dashboard_configuration_hub")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/super/", resp["Location"])

    def test_dashboard_configuration_responsive_table_wrapper(self):
        DashboardTemplate.objects.create(name="QA default layout", is_active=True)
        session = self.client.session
        session["school_id"] = str(self.school.id)
        session.save()
        resp = self._get("siteconfig:dashboard_configuration_hub")
        self._assert_cp_page_quality(resp, expect_title_fragment="Dashboard configuration")
        self.assertIn("table-responsive", resp.content.decode())

    def test_dashboard_configuration_live_preview_sidecar_is_non_mutating(self):
        pack = DashboardPack.objects.create(
            code="qa-preview-pack",
            name="QA Preview Pack",
            family="admin",
            is_active=True,
        )
        DashboardTemplate.objects.create(
            dashboard_pack=pack,
            name="QA Preview Layout",
            description="Previewable dashboard layout",
            is_active=True,
            config_schema={
                "chrome": {"header_variant": "wide"},
                "role_home": {
                    "purpose": "Preview the dashboard before assigning it.",
                    "focus_areas": ["Operations", "Approvals"],
                },
                "modules": {"ops_watch": True, "outstanding_fees": False},
                "kpis": ["attendance_today", "weekly_presence"],
                "theme": {"visual_preset": "crisp-professional"},
                "sections": {"admin__legacy_panel": False},
            },
        )
        session = self.client.session
        session["school_id"] = str(self.school.id)
        session.save()

        before_count = TenantLayoutAssignment.objects.filter(school=self.school).count()
        resp = self._get("siteconfig:dashboard_configuration_hub")
        after_count = TenantLayoutAssignment.objects.filter(school=self.school).count()

        self.assertEqual(before_count, after_count)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("data-rmc-dashboard-role-preview", body)
        self.assertIn("rmc-dashboard-role-preview-data", body)
        self.assertIn("rmc-dashboard-template-preview-data", body)
        self.assertIn("Live preview sidecar", body)
        self.assertIn("QA Preview Layout", body)
        self.assertIn("/portal/preview?role=ADMIN", body)

    def test_theme_colors_standalone_meta(self):
        resp = self.client.get(
            reverse("siteconfig:theme_colors", urlconf="config.manager_urls")
            + "?standalone=1"
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("Theme", body)
        self.assertIn('data-rmc-os-shell="control-plane"', body)

    def test_customizer_redirect_seo_safe(self):
        resp = self.client.get(
            "/siteconfig/customizer/",
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/siteconfig/theme-colors/", resp["Location"])
        self.assertIn("standalone=1", resp["Location"])

    def test_region_validation_stem_cp_shell(self):
        resp = self._get("siteconfig:region_validation")
        self._assert_cp_page_quality(resp, expect_title_fragment="Region validation")
        self.assertIn("region-validation-dashboard", resp.content.decode())

    def test_region_comparison_stem_cp_shell(self):
        resp = self._get("siteconfig:region_comparison")
        self._assert_cp_page_quality(resp, expect_title_fragment="Region comparison")
        self.assertIn("region-comparison-matrix", resp.content.decode())

    def test_region_grading_matrix_stem_cp_shell(self):
        resp = self._get("siteconfig:region_grading_scales")
        self._assert_cp_page_quality(
            resp, expect_title_fragment="Region grading scales matrix"
        )
        self.assertIn("region-grading-matrix", resp.content.decode())

    def test_maintenance_preview_stem_cp_shell(self):
        resp = self._get("siteconfig:maintenance")
        self._assert_cp_page_quality(resp, expect_title_fragment="Maintenance preview")
        self.assertIn("maintenance-preview", resp.content.decode())
