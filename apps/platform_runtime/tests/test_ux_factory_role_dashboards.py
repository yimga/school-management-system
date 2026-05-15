"""
UX factory: role dashboards expose command-center structure, one primary above the fold in strict mode
(where applicable), and honest blocker copy — see docs/generated/role_dashboard_ux_reset_audit.md.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import Permission as FeaturePermission, User
from apps.academics.models import AcademicYear, Term
from apps.finance.models import ComplianceProfile
from apps.people.models import TeacherProfile
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import Plan

ROOT = Path(__file__).resolve().parents[3]
_FOLD_END_COMMENT_RE = re.compile(r"<!--\s*rmc-ux-above-fold-end\s*-->", re.I)
_SURFACE_ROLE_DASHBOARD_OPEN_RE = re.compile(
    r'data-rmc-ux-role-dashboard\s*=\s*["\'](?P<slug>[^"\']+)["\']',
    re.I,
)


def _tenant_host(school: School) -> str:
    return f"{school.subdomain}.runmycampus.com"


def _above_fold(html: str) -> str:
    m = _FOLD_END_COMMENT_RE.search(html)
    if m:
        return html[: m.start()]
    return html


def _surface_above_fold(html: str, role_dashboard_slug: str) -> str:
    """Above-fold slice scoped to the role dashboard surface (excludes shell chrome primaries)."""
    start = -1
    for m in _SURFACE_ROLE_DASHBOARD_OPEN_RE.finditer(html):
        if m.group("slug").lower() == role_dashboard_slug.lower():
            start = m.start()
            break
    if start < 0:
        return _above_fold(html)
    m = _FOLD_END_COMMENT_RE.search(html, pos=start)
    if not m:
        return html[start:]
    return html[start : m.start()]


def _no_bare_hash_href(html: str) -> bool:
    return not re.search(r"""href\s*=\s*['"]#['"]""", html, re.I)


def _teacher_hero_chunk(html: str) -> str:
    start = html.find('data-rmc-teacher-hero-actions="1"')
    if start < 0:
        return html
    end = html.find("tdm-hero__profile", start)
    if end < 0:
        return html[start : start + 4000]
    return html[start:end]


@override_settings(
    CONVERSION_SINGLE_ACTION_ENFORCED=True,
    LANGUAGE_CODE="en",
    ROOT_URLCONF="config.tenant_urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"],
)
class UxFactoryTenantDashboardTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        # Intelligence SKU: /analytics/* is gated (see schools.middleware.FEATURE_GATE_PATH_MAP).
        plan, _ = Plan.objects.update_or_create(
            slug="ux-factory-tenant-plan",
            defaults={
                "name": "UX Factory Tenant Plan",
                "included_features": ["library", "reports", "analytics"],
                "is_active": True,
            },
        )
        cls.school = School.objects.create(
            name="UX Factory School",
            slug="ux-factory",
            subdomain="ux-factory",
            is_active=True,
            plan=plan,
            addons=[],
            features={},
        )
        # Ensure get_active_year_and_term() resolves to this tenant's active pair (not migration seed rows).
        AcademicYear.objects.all().update(is_active=False)
        Term.objects.all().update(is_active=False)
        year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
            school=cls.school,
        )
        Term.objects.create(
            name=Term.Name.FIRST,
            academic_year=year,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 1),
            is_active=True,
        )
        ComplianceProfile.objects.create(
            name="UX Factory Profile",
            country_code="US",
            is_active=True,
        )

    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)

    def _attach(self, user: User, role: str):
        SchoolMembership.objects.get_or_create(
            user=user,
            school=self.school,
            defaults={"role": role, "is_primary": True},
        )

    def _force_login_verified(self, user: User) -> None:
        TOTPDevice.objects.get_or_create(
            user=user,
            name="test-device",
            defaults={"confirmed": True},
        )
        self.client.force_login(user)
        session = self.client.session
        session["mfa_verified"] = True
        session.save()

    def test_backend_school_command_center_markers_and_strict_fold(self):
        perm, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        u = User.objects.create_user(
            username="uxf_admin",
            password="Test1234!ab",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(perm)
        self._attach(u, User.Role.ADMIN)
        self._force_login_verified(u)
        url = reverse("accounts:backend_dashboard")
        resp = self.client.get(url, HTTP_HOST=_tenant_host(self.school))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-ux-role-dashboard="school-command-center"', body)
        self.assertIn("School Command Center", body)
        self.assertIn('data-rmc-ux-section="what-needs-attention"', body)
        self.assertIn('data-rmc-ux-section="school-readiness"', body)
        self.assertIn('data-rmc-next-action-strip="1"', body)
        fold = _surface_above_fold(body, "school-command-center")
        self.assertLessEqual(fold.count("btn-primary"), 1, msg=fold[:2500])

    def test_teacher_workspace_markers_and_hero_primary(self):
        u = User.objects.create_user(
            username="uxf_teacher",
            password="Test1234!ab",
            role=User.Role.TEACHER,
        )
        TeacherProfile.objects.create(user=u)
        self._attach(u, User.Role.TEACHER)
        self.client.login(username="uxf_teacher", password="Test1234!ab")
        host = _tenant_host(self.school)
        resp = self.client.get("/portal/teacher/", HTTP_HOST=host)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-ux-role-dashboard="teacher-workspace"', body)
        self.assertIn('data-rmc-ux-section="today-plan"', body)
        self.assertIn('data-rmc-ux-section="what-needs-attention"', body)
        chunk = _teacher_hero_chunk(body)
        self.assertEqual(chunk.count("btn-primary"), 1, msg=chunk[:1200])

    def test_family_home_markers(self):
        u = User.objects.create_user(
            username="uxf_parent",
            password="Test1234!ab",
            role=User.Role.PARENT,
        )
        self._attach(u, User.Role.PARENT)
        body = (ROOT / "templates" / "parent" / "dashboard.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('data-rmc-ux-role-dashboard="family-home"', body)
        self.assertIn("Family Home", body)
        self.assertIn('data-rmc-ux-section="family-summary"', body)
        self.assertIn('data-rmc-ux-section="what-needs-attention"', body)

    def test_finance_workspace_markers(self):
        u = User.objects.create_user(
            username="uxf_finance",
            password="Test1234!ab",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self._attach(u, User.Role.ADMIN)
        body = (ROOT / "templates" / "finance" / "dashboard.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('data-rmc-ux-role-dashboard="finance-workspace"', body)
        self.assertIn('data-rmc-ux-section="what-needs-attention"', body)
        self.assertIn("rmc_os_action_bar.html", body)
        self.assertIn("primary_label=_(\"Open invoices\")", body)
        fold = _surface_above_fold(body, "finance-workspace")
        self.assertLessEqual(fold.count("btn-primary"), 1, msg=fold[:2500])

    def test_analytics_insights_markers(self):
        u = User.objects.create_user(
            username="uxf_analytics",
            password="Test1234!ab",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self._attach(u, User.Role.ADMIN)
        year = AcademicYear.objects.filter(school=self.school, is_active=True).first()
        term = (
            Term.objects.filter(academic_year=year, is_active=True).first()
            if year
            else None
        )
        self.assertIsNotNone(year)
        self.assertIsNotNone(term)
        # Isolate from migration seed rows / DB ordering + optional tenant dashboard HTML cache.
        cache.clear()
        body = (ROOT / "templates" / "analytics" / "dashboard.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('data-rmc-ux-role-dashboard="analytics-insights"', body)
        self.assertIn('data-rmc-ux-section="what-needs-attention"', body)
        fold = _surface_above_fold(body, "analytics-insights")
        self.assertLessEqual(fold.count("btn-primary"), 1, msg=fold[:2500])


@override_settings(
    CONVERSION_SINGLE_ACTION_ENFORCED=True,
    LANGUAGE_CODE="en",
    ROOT_URLCONF="config.urls",
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"],
)
class UxFactoryManagerDashboardTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)

    def test_founder_platform_command_center_markers_and_strict_fold(self):
        u = User.objects.create_user(
            username="uxf_founder",
            password="Test1234!ab",
            is_superuser=True,
        )
        self.client.force_login(u)
        url = reverse("super:founder_dashboard")
        with mock.patch.dict(
            "os.environ",
            {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com", "MULTI_TENANT_LEGACY_BASE_DOMAINS": ""},
            clear=False,
        ):
            resp = self.client.get(url, HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-ux-role-dashboard="founder-command-center"', body)
        self.assertIn("Platform Command Center", body)
        self.assertIn('data-rmc-ux-section="system-pulse"', body)
        self.assertIn('data-rmc-ux-section="what-needs-attention"', body)
        self.assertIn('data-rmc-ux-section="one-next-action"', body)
        fold = _surface_above_fold(body, "founder-command-center")
        self.assertLessEqual(fold.count("btn-primary"), 1, msg=fold[:2500])
        self.assertTrue(_no_bare_hash_href(body), msg="Avoid dummy hash-only href on founder dashboard.")

    def test_tenant_lifecycle_portfolio_markers(self):
        u = User.objects.create_user(
            username="uxf_lifecycle",
            password="Test1234!ab",
            is_superuser=True,
        )
        self.client.force_login(u)
        url = reverse("platform_runtime:tenant_lifecycle_dashboard")
        with mock.patch.dict(
            "os.environ",
            {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com", "MULTI_TENANT_LEGACY_BASE_DOMAINS": ""},
            clear=False,
        ):
            resp = self.client.get(url, HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-ux-role-dashboard="tenant-lifecycle-portfolio"', body)
        self.assertIn('data-rmc-ux-section="system-pulse"', body)
        self.assertIn('data-rmc-ux-section="what-needs-attention"', body)
