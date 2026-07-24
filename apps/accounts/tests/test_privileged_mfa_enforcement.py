"""Platform superadmins and active school owners may never soft-skip MFA."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.mfa_defaults import (
    effective_required_roles,
    principal_requires_strict_mfa,
)
from apps.accounts.post_login_mfa import resolve_post_login_mfa_redirect
from apps.schools.models import School, SchoolMembership

User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["*", "manager.runmycampus.com", "strict-school.runmycampus.com"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class PrivilegedMfaEnforcementTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Strict School",
            slug="strict-school",
            subdomain="strict-school",
            is_active=True,
        )

    def _request(self, user, *, host, school=None):
        request = self.factory.post(
            "/authentication/login/",
            HTTP_HOST=host,
        )
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        request.user = user
        request.school = school
        return request

    def test_canonical_superadmin_role_is_in_mfa_floor(self):
        self.assertIn("SUPERADMIN", effective_required_roles([]))

    def test_platform_superadmin_without_device_is_forced_to_setup(self):
        user = User.objects.create_user(
            username="strict-operator@example.com",
            email="strict-operator@example.com",
            password="MfaStrict123!",
            role=User.Role.SUPERADMIN,
            is_staff=True,
            is_superuser=True,
        )
        request = self._request(
            user, host="manager.runmycampus.com", school=None
        )
        response = resolve_post_login_mfa_redirect(request, user)
        self.assertIsNotNone(response)
        self.assertIn("/mfa/setup", response.url)

    def test_active_school_owner_without_device_is_forced_to_setup(self):
        user = User.objects.create_user(
            username="strict-owner@example.com",
            email="strict-owner@example.com",
            password="MfaStrict123!",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=user,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
            is_school_owner=True,
        )
        self.assertTrue(principal_requires_strict_mfa(user, self.school))
        request = self._request(
            user,
            host="strict-school.runmycampus.com",
            school=self.school,
        )
        response = resolve_post_login_mfa_redirect(request, user)
        self.assertIsNotNone(response)
        self.assertIn("/mfa/setup", response.url)

    def test_suspended_owner_does_not_keep_owner_strictness(self):
        user = User.objects.create_user(
            username="suspended-owner@example.com",
            email="suspended-owner@example.com",
            password="MfaStrict123!",
            role=User.Role.ADMIN,
        )
        from django.utils import timezone

        SchoolMembership.objects.create(
            user=user,
            school=self.school,
            role=User.Role.ADMIN,
            is_school_owner=True,
            suspended_at=timezone.now(),
        )
        self.assertFalse(principal_requires_strict_mfa(user, self.school))
