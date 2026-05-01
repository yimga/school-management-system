"""Strict conversion lock: role-wide dashboard blocks until first action."""

from __future__ import annotations

import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from apps.accounts.models import Permission as FeaturePermission, User
from apps.schools.models import School, SchoolMembership

UserModel = get_user_model()


@patch.dict(
    os.environ,
    {"MULTI_TENANT_BASE_DOMAIN": "example.com"},
    clear=False,
)
@override_settings(
    ALLOWED_HOSTS=["*"],
    SECURE_SSL_REDIRECT=False,
    DEBUG=True,
    ROOT_URLCONF="config.tenant_urls",
    MULTI_TENANT_BASE_DOMAIN="example.com",
    CONVERSION_LOCK_STRICT=True,
    CONVERSION_LOCK_ALL_SCHOOLS=True,
    CONVERSION_LOCK_USE_NARROW_WORKFLOW_PATHS=True,
)
class ConversionLockStrictRoleWideTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.school = School.objects.create(
            name="Lock School",
            slug="lock-school",
            subdomain="lock-school",
            is_active=True,
            settings={},
        )

    def _login_role(self, role: str, username: str):
        user = UserModel.objects.create_user(
            username=username,
            email=f"{username}@example.edu",
            password="Test1234!ab",
            role=role,
        )
        SchoolMembership.objects.get_or_create(
            user=user,
            school=self.school,
            defaults={"role": role, "is_primary": True},
        )
        self.client.login(username=username, password="Test1234!ab")
        return user

    def test_admin_backend_blocked_redirects_to_activation(self):
        self._login_role(User.Role.ADMIN, "lockadmin")
        r = self.client.get(
            "/authentication/backend/",
            HTTP_HOST="lock-school.example.com",
            follow=False,
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn("/activation/first-action/", r["Location"])

    def test_teacher_dashboard_blocked_teacher_attendance_allowed(self):
        self._login_role(User.Role.TEACHER, "lockteacher")
        r_dash = self.client.get(
            "/portal/teacher/",
            HTTP_HOST="lock-school.example.com",
            follow=False,
        )
        self.assertEqual(r_dash.status_code, 302)
        self.assertIn("/activation/first-action/", r_dash["Location"])
        r_ok = self.client.get(
            "/portal/teacher/attendance/",
            HTTP_HOST="lock-school.example.com",
            follow=False,
        )
        self.assertIn(r_ok.status_code, (200, 302))

    def test_parent_home_blocked(self):
        self._login_role(User.Role.PARENT, "lockparent")
        r = self.client.get(
            "/portal/parent/",
            HTTP_HOST="lock-school.example.com",
            follow=False,
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn("/activation/first-action/", r["Location"])

    def test_student_portal_blocked(self):
        self._login_role(User.Role.STUDENT, "lockstudent")
        r = self.client.get(
            "/portal/student-portal/grades/",
            HTTP_HOST="lock-school.example.com",
            follow=False,
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn("/activation/first-action/", r["Location"])

    def test_demo_flow_allowed_under_narrow_prefix(self):
        self._login_role(User.Role.FINANCE_STAFF, "lockfinance")
        r = self.client.get(
            "/demo/flow/attendance/",
            HTTP_HOST="lock-school.example.com",
            follow=False,
        )
        self.assertIn(r.status_code, (200, 302))

    def test_finance_staff_backend_blocked(self):
        self._login_role(User.Role.FINANCE_STAFF, "lockstaff2")
        r = self.client.get(
            "/authentication/backend/",
            HTTP_HOST="lock-school.example.com",
            follow=False,
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn("/activation/first-action/", r["Location"])

    def test_academics_staff_backend_blocked(self):
        self._login_role(User.Role.ACADEMICS_STAFF, "lockacad")
        r = self.client.get(
            "/authentication/backend/",
            HTTP_HOST="lock-school.example.com",
            follow=False,
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn("/activation/first-action/", r["Location"])

    def test_backend_allowed_after_first_action_recorded(self):
        self._login_role(User.Role.ADMIN, "unlockadm")
        perm, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        u = UserModel.objects.get(username="unlockadm")
        u.feature_permissions.add(perm)
        from apps.schools.conversion_lock_state import record_conversion_first_action

        record_conversion_first_action(self.school, source="proof_test", user=u)
        r = self.client.get(
            "/authentication/backend/",
            HTTP_HOST="lock-school.example.com",
            follow=False,
        )
        self.assertEqual(r.status_code, 200)
