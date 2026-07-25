"""1084: Academic years read-only setup evidence (tenant AcademicYear rows)."""

from django.test import Client, TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from apps.accounts.models import Permission, User
from apps.academics.models import AcademicYear
from apps.siteconfig.models import Plan
from apps.schools.models import School, SchoolMembership

_T_HOST = "ayears.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class AcademicYearsSetupEvidenceTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="AYPlan",
            slug="ay-plan",
            included_features=[],
            is_active=True,
        )
        cls.school = School.objects.create(
            name="AY School",
            slug="ayears",
            subdomain="ayears",
            is_active=True,
            plan=cls.plan,
        )
        cls.perm_settings, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
            is_active=True,
        )

    def _arm(self, user, client):
        """Arm a client so a tenant admin actually reaches this tenant-host page.

        Two guards gate the request. (1) OperatorTenantConfinementMiddleware
        (``apps/accounts/middleware.py``) redirects any user with control-plane
        access but no ``SchoolMembership`` to ``manager/super/``; a membership
        flips ``user_has_control_plane_access`` to False so a normal tenant admin
        passes (superusers use the break-glass bypass, so they skip the
        membership). (2) ``RequireMFAMiddleware`` walls the baseline-MFA ADMIN role
        without a confirmed TOTP device (enforce) or a verified session (re-verify).
        """
        from django_otp.plugins.otp_totp.models import TOTPDevice

        if not user.is_superuser:
            SchoolMembership.objects.get_or_create(
                user=user,
                school=self.school,
                defaults={"role": User.Role.ADMIN, "is_primary": True},
            )
        TOTPDevice.objects.get_or_create(user=user, name="ay-mfa", confirmed=True)
        session = client.session
        session["mfa_verified"] = True
        session.save()

    def test_settings_manage_gets_200_with_markers(self) -> None:
        u = User.objects.create_user(
            username="ay_ev",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm_settings)
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username="ay_ev", password="x" * 8)
        self._arm(u, c)
        path = reverse("siteconfig:academic_years_setup_evidence", urlconf="config.tenant_urls")
        self.assertIn("/siteconfig/reports/academic-years-setup/", path)
        resp = c.get(path)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:500])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-shell-surface="academic-years-setup-evidence"', body)
        self.assertIn('data-rmc-operator-evidence-summary="1"', body)
        self.assertIn("2025/2026", body)

    def test_superuser_sees_scheduled_hub_before_admin(self) -> None:
        u = User.objects.create_user(
            username="ay_su",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username="ay_su", password="x" * 8)
        self._arm(u, c)
        path = reverse("siteconfig:academic_years_setup_evidence", urlconf="config.tenant_urls")
        body = c.get(path).content.decode("utf-8", errors="replace")
        p = body.find("Scheduled report delivery")
        a = body.find("Advanced/Admin: academic year rows")
        self.assertNotEqual(p, -1)
        self.assertNotEqual(a, -1)
        self.assertLess(p, a)

    def test_superuser_sees_departments_before_admin(self) -> None:
        u = User.objects.create_user(
            username="ay_su2",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username="ay_su2", password="x" * 8)
        self._arm(u, c)
        path = reverse("siteconfig:academic_years_setup_evidence", urlconf="config.tenant_urls")
        body = c.get(path).content.decode("utf-8", errors="replace")
        d = body.find("Departments (setup)")
        a = body.find("Advanced/Admin: academic year rows")
        self.assertNotEqual(d, -1)
        self.assertNotEqual(a, -1)
        self.assertLess(d, a)

    def test_tenant_admin_academic_year_changelist_resolves_tenant_urlconf(self) -> None:
        try:
            u = reverse(
                "admin:academics_academicyear_changelist",
                urlconf="config.tenant_urls",
            )
        except NoReverseMatch as e:
            self.fail(f"Missing tenant admin route: {e}")
        self.assertIn("/admin/", u)
        self.assertIn("academicyear", u)

    def test_non_superuser_hides_admin_changelist(self) -> None:
        u = User.objects.create_user(
            username="ay_ns",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=False,
        )
        u.feature_permissions.add(self.perm_settings)
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username="ay_ns", password="x" * 8)
        self._arm(u, c)
        path = reverse("siteconfig:academic_years_setup_evidence", urlconf="config.tenant_urls")
        resp = c.get(path)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:300])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertNotIn("Advanced/Admin: academic year rows", body)
