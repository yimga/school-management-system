"""1072: Read-only report template catalog (ReportTemplate rows) — no export on page."""

from __future__ import annotations

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission, User
from apps.siteconfig.models import Plan, ReportTemplate
from apps.schools.models import School

_T_HOST = "rtcat.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class ReportTemplatesCatalogEvidenceTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls) -> None:
        cls.plan = Plan.objects.create(
            name="RtPlan",
            slug="rt-plan",
            included_features=[],
            is_active=True,
        )
        cls.school = School.objects.create(
            name="Rt School",
            slug="rtcat",
            subdomain="rtcat",
            is_active=True,
            plan=cls.plan,
        )
        cls.perm_settings, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        ReportTemplate.objects.create(
            slug="rtcat-smoke",
            name="RT Cat Smoke",
            is_active=True,
            template_family="",
        )

    def test_settings_manager_sees_200_with_markers(self) -> None:
        u = User.objects.create_user(
            username="rt_cat_adm",
            password="p" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm_settings)
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username="rt_cat_adm", password="p" * 8)
        path = reverse(
            "siteconfig:report_templates_catalog_evidence", urlconf="config.tenant_urls"
        )
        self.assertIn("/siteconfig/reports/report-templates-catalog/", path)
        resp = c.get(path)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:500])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-shell-surface="report-templates-catalog-evidence"', body)
        self.assertIn('data-cp-evidence-surface="report-templates-catalog"', body)
        self.assertIn("data-rmc-operator-evidence-summary", body)
        self.assertIn("data-rmc-evidence-related-links", body)
        self.assertIn("data-rmc-report-bulk-evidence", body)
        self.assertIn("RT Cat Smoke", body)
        self.assertIn("rtcat-smoke", body)

    def test_superuser_cp_before_admin(self) -> None:
        User.objects.create_user(
            username="rt_cat_su",
            password="p" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username="rt_cat_su", password="p" * 8)
        path = reverse(
            "siteconfig:report_templates_catalog_evidence", urlconf="config.tenant_urls"
        )
        body = c.get(path).content.decode("utf-8", errors="replace")
        p = body.find("Scheduled report delivery")
        a = body.find("Advanced/Admin: report template rows")
        self.assertNotEqual(p, -1)
        self.assertNotEqual(a, -1)
        self.assertLess(p, a)
