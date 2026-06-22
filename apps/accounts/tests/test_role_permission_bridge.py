"""RolePermissionBackend — admin-like roles get the people/academics perms the
@permission_required backend views require, non-admins get nothing.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.accounts.auth_backends_role_perms import (
    RolePermissionBackend,
    bridge_eligible,
)


def _user(**kw):
    base = dict(
        is_active=True, is_authenticated=True, is_superuser=False, is_staff=False, role=""
    )
    base.update(kw)
    return SimpleNamespace(**base)


class BridgeEligibilityTests(SimpleTestCase):
    """Pure, DB-free gating logic — the security-critical part."""

    def test_admin_role_is_eligible(self):
        self.assertTrue(bridge_eligible(_user(role="ADMIN")))

    def test_admin_like_roles_are_eligible(self):
        for role in ("SUPERADMIN", "PROPRIETOR", "PRINCIPAL", "IT_ADMIN", "DEAN"):
            self.assertTrue(bridge_eligible(_user(role=role)), role)

    def test_django_staff_is_eligible(self):
        self.assertTrue(bridge_eligible(_user(is_staff=True, role="")))

    def test_parent_and_student_and_teacher_are_not_eligible(self):
        for role in ("PARENT", "STUDENT", "TEACHER", ""):
            self.assertFalse(bridge_eligible(_user(role=role)), role or "<blank>")

    def test_superuser_excluded_already_has_all(self):
        self.assertFalse(bridge_eligible(_user(is_superuser=True, role="ADMIN")))

    def test_anonymous_and_inactive_excluded(self):
        self.assertFalse(bridge_eligible(_user(is_authenticated=False, role="ADMIN")))
        self.assertFalse(bridge_eligible(_user(is_active=False, role="ADMIN")))
        self.assertFalse(bridge_eligible(None))

    def test_non_eligible_user_gets_empty_perms_without_db(self):
        # A non-eligible user short-circuits before any DB query.
        self.assertEqual(RolePermissionBackend().get_all_permissions(_user(role="PARENT")), set())

    def test_object_level_perms_out_of_scope(self):
        self.assertEqual(
            RolePermissionBackend().get_all_permissions(_user(role="ADMIN"), obj=object()),
            set(),
        )
