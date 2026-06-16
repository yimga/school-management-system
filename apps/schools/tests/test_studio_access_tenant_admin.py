"""Tenant admins can reach school-scoped Studio OS on the tenant host.

Regression for the "Complete setup → bounced back to dashboard" loop: Studio OS
on the tenant host gated on Django ``is_staff``, but tenant admins are role-based
(``role == ADMIN``) and never ``is_staff`` by platform design — so guided
onboarding → ``studio_os:launch`` → ``studio_shell`` bounced them to the
backend dashboard. The gate now matches the backend-dashboard admin tier.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase

from apps.schools.control_plane import user_can_access_studio_on_request

Role = get_user_model().Role


class _StubUser:
    def __init__(self, *, authenticated=True, is_staff=False, is_superuser=False, role=None):
        self.is_authenticated = authenticated
        self.is_staff = is_staff
        self.is_superuser = is_superuser
        self.role = role


class _StubRequest:
    def __init__(self, user, host_kind="tenant"):
        self.user = user
        self.public_host_kind = host_kind


class StudioAccessTenantAdminTests(SimpleTestCase):
    def test_tenant_admin_role_can_access_on_tenant_host(self):
        # THE FIX: role ADMIN, NOT is_staff — previously bounced.
        req = _StubRequest(_StubUser(role=Role.ADMIN, is_staff=False))
        self.assertTrue(user_can_access_studio_on_request(req))

    def test_django_staff_still_allowed(self):
        req = _StubRequest(_StubUser(is_staff=True, role=Role.TEACHER))
        self.assertTrue(user_can_access_studio_on_request(req))

    def test_superuser_allowed(self):
        req = _StubRequest(_StubUser(is_superuser=True, role=None))
        self.assertTrue(user_can_access_studio_on_request(req))

    def test_non_admin_tenant_user_denied(self):
        for role in (Role.TEACHER, Role.PARENT, Role.STUDENT):
            req = _StubRequest(_StubUser(role=role, is_staff=False))
            self.assertFalse(
                user_can_access_studio_on_request(req),
                msg=f"role {role} must NOT reach Studio",
            )

    def test_unauthenticated_denied(self):
        req = _StubRequest(_StubUser(authenticated=False, role=Role.ADMIN))
        self.assertFalse(user_can_access_studio_on_request(req))
