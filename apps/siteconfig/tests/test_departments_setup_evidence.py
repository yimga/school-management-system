"""1090: Departments read-only setup evidence (tenant Department rows)."""

from __future__ import annotations

from django.test import Client, TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from apps.accounts.models import Permission, User
from apps.academics.models import Department
from apps.siteconfig.models import Plan
from apps.schools.models import School

_T_HOST = "deptev.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class DepartmentsSetupEvidenceTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="DPlan",
            slug="d-plan",
            included_features=[],
            is_active=True,
        )
        cls.school = School.objects.create(
            name="D School",
            slug="deptev",
            subdomain="deptev",
            is_active=True,
            plan=cls.plan,
        )
        cls.perm_settings, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        cls.dept = Department.objects.create(
            school=cls.school,
            name="Mathematics",
            code="dept-math-deptev",
        )

    def test_settings_manage_gets_200_with_markers(self) -> None:
        u = User.objects.create_user(
            username="d_ev",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm_settings)
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username="d_ev", password="x" * 8)
        path = reverse("siteconfig:departments_setup_evidence", urlconf="config.tenant_urls")
        self.assertIn("/siteconfig/reports/departments-setup/", path)
        resp = c.get(path)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:500])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-shell-surface="departments-setup-evidence"', body)
        self.assertIn('data-rmc-operator-evidence-summary="1"', body)
        self.assertIn("Mathematics", body)

    def test_superuser_sees_cp_links_before_admin(self) -> None:
        User.objects.create_user(
            username="d_su",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username="d_su", password="x" * 8)
        path = reverse("siteconfig:departments_setup_evidence", urlconf="config.tenant_urls")
        body = c.get(path).content.decode("utf-8", errors="replace")
        p = body.find("Scheduled report delivery")
        y = body.find("Academic years (setup)")
        a = body.find("Advanced/Admin: department rows")
        self.assertNotEqual(p, -1)
        self.assertNotEqual(y, -1)
        self.assertNotEqual(a, -1)
        self.assertLess(p, a)
        self.assertLess(y, a)

    def test_tenant_admin_department_changelist_resolves_tenant_urlconf(self) -> None:
        try:
            u = reverse(
                "admin:academics_department_changelist",
                urlconf="config.tenant_urls",
            )
        except NoReverseMatch as e:
            self.fail(f"Missing tenant admin route: {e}")
        self.assertIn("/admin/", u)
        self.assertIn("department", u)

    def test_non_superuser_hides_admin_changelist(self) -> None:
        u = User.objects.create_user(
            username="d_ns",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=False,
        )
        u.feature_permissions.add(self.perm_settings)
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username="d_ns", password="x" * 8)
        path = reverse("siteconfig:departments_setup_evidence", urlconf="config.tenant_urls")
        body = c.get(path).content.decode("utf-8", errors="replace")
        self.assertNotIn("Advanced/Admin: department rows", body)
