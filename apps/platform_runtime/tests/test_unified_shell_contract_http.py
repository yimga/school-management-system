"""HTTP integration shell contract (full DB + migrations). Tag: shell_http — exclude for fast runs."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from django.test import Client, TestCase, override_settings, tag
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import Permission as FeaturePermission, User
from apps.academics.models import AcademicYear, Term
from apps.people.models import TeacherProfile
from apps.schools.models import School, SchoolMembership


_T_HOST = "unified-shell.runmycampus.com"
_MGR_HOST = "manager.runmycampus.com"


@tag("shell_http")
@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST, _MGR_HOST],
    ROOT_URLCONF="config.tenant_urls",
)
class UnifiedShellContractTenantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Unified Shell School",
            slug="unified-shell",
            subdomain="unified-shell",
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

    def setUp(self):
        self.client = Client(HTTP_HOST=_T_HOST, raise_request_exception=False)

    def _attach(self, user: User, role: str):
        SchoolMembership.objects.get_or_create(
            user=user,
            school=self.school,
            defaults={"role": role, "is_primary": True},
        )

    def _login_verified(self, username: str, password: str = "x" * 8):
        self.client.login(username=username, password=password)
        session = self.client.session
        session["mfa_verified"] = True
        session.save()

    def _assert_core_shell(self, body: str):
        self.assertIn("data-rmc-os-shell=", body)
        self.assertIn('data-rmc-os-page-header="1"', body)
        self.assertIn('data-rmc-os-status-strip="1"', body)
        self.assertIn('data-rmc-payment-readiness-slot="1"', body)
        self.assertIn('data-rmc-os-nav="1"', body)
        self.assertIn("data-rmc-os-nav-groups=", body)
        self.assertIn('data-rmc-next-action-strip="1"', body)
        self.assertIn('id="portalSidebar"', body)
        self.assertRegex(body, r'data-rmc-os-primary-action-slot="1"')
        self.assertRegex(body, r'data-rmc-context-rail="1"')

    def test_backend_dashboard_shell_contract(self):
        u = User.objects.create_user(
            username="unified_adm",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm_settings)
        TOTPDevice.objects.create(user=u, name="test-device", confirmed=True)
        self._attach(u, User.Role.ADMIN)
        self._login_verified("unified_adm")
        path = reverse("accounts:backend_dashboard", urlconf="config.tenant_urls")
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200, msg=getattr(resp, "content", b"")[:500])
        body = resp.content.decode("utf-8", errors="replace")
        self._assert_core_shell(body)
        self.assertIn('data-rmc-os-role="school_admin"', body)

    def test_teacher_and_parent_portal_shell_contract(self):
        for username, role, path in (("unified_teacher", User.Role.TEACHER, "/portal/teacher/"),):
            u = User.objects.create_user(username=username, password="x" * 8, role=role)
            if role == User.Role.TEACHER:
                TeacherProfile.objects.create(user=u)
            self._attach(u, role)
            self.client.login(username=username, password="x" * 8)
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 200, msg=path)
            body = resp.content.decode("utf-8", errors="replace")
            self._assert_core_shell(body)
            if role == User.Role.TEACHER:
                self.assertIn('data-rmc-os-role="teacher"', body)

        root = Path(__file__).resolve().parents[3]
        parent_template = (root / "templates" / "parent" / "dashboard.html").read_text(
            encoding="utf-8",
            errors="replace",
        )
        portal_base = (root / "templates" / "portal_base.html").read_text(
            encoding="utf-8",
            errors="replace",
        )
        shell_wrap = (
            root / "templates" / "partials" / "shell_portal_layout_wrap_open.html"
        ).read_text(encoding="utf-8", errors="replace")
        self.assertIn("portalSidebar", portal_base)
        self.assertIn("data-rmc-os-shell", shell_wrap)
        self.assertIn("data-rmc-os-role", shell_wrap)
        self.assertIn("data-rmc-parent-header-actions", parent_template)

    @override_settings(CONVERSION_SINGLE_ACTION_ENFORCED=True)
    def test_strict_next_action_single_primary_marker(self):
        u = User.objects.create_user(
            username="unified_strict",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm_settings)
        TOTPDevice.objects.create(user=u, name="test-device", confirmed=True)
        self._attach(u, User.Role.ADMIN)
        self._login_verified("unified_strict")
        resp = self.client.get(
            reverse("accounts:backend_dashboard", urlconf="config.tenant_urls")
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        m = re.search(
            r'<section class="rmc-next-action-strip[^"]*"[^>]*data-rmc-next-action-strict="1"[^>]*>',
            body,
        )
        self.assertIsNotNone(m, msg="Expected strict next-action strip")
        start = m.start()
        end = body.find("</section>", start)
        self.assertGreater(end, start)
        chunk = body[start:end]
        self.assertEqual(chunk.count("data-rmc-primary-action="), 1, msg=chunk[:400])


@tag("shell_http")
@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _MGR_HOST],
    ROOT_URLCONF="config.urls",
)
class UnifiedShellContractControlPlaneTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST=_MGR_HOST, raise_request_exception=False)

    def test_super_dashboard_includes_os_markers(self):
        u = User.objects.create_user(
            username="unified_super",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        TOTPDevice.objects.create(user=u, name="test-device", confirmed=True)
        self.client.login(username="unified_super", password="x" * 8)
        session = self.client.session
        session["mfa_verified"] = True
        session.save()
        url = reverse("super:dashboard")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, msg=getattr(resp, "content", b"")[:500])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-os-shell="control-plane"', body)
        self.assertIn('data-rmc-os-role="founder_operator"', body)
        self.assertIn('data-rmc-os-page-header="1"', body)
        self.assertIn('data-rmc-os-status-strip="1"', body)
        self.assertIn('data-rmc-os-nav="1"', body)
        self.assertIn('id="cpSidebarOffcanvas"', body)
