"""Tests for temporary role grants: permission and role checks include active grants."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import AccessRole, User, TemporaryRoleGrant
from apps.accounts.permissions import has_role


class TemporaryRoleGrantTests(TestCase):
    """Temporary grants grant permissions and role until expires_at."""

    def test_active_grant_grants_permission(self):
        user = User.objects.create_user(
            username="auditor",
            password="pass1234",
            role=User.Role.PARENT,
        )
        user.roles.clear()
        self.assertFalse(user.has_feature_permission("reports.manage"))
        role = AccessRole.objects.get(code="BURSAR")
        TemporaryRoleGrant.objects.create(
            user=user,
            role=role,
            expires_at=timezone.now() + timedelta(days=30),
        )
        self.assertTrue(
            user.has_feature_permission("reports.manage"),
            msg="Active temporary BURSAR grant should grant reports.manage",
        )

    def test_expired_grant_does_not_grant_permission(self):
        user = User.objects.create_user(
            username="ex_auditor",
            password="pass1234",
            role=User.Role.PARENT,
        )
        user.roles.clear()
        role = AccessRole.objects.get(code="BURSAR")
        TemporaryRoleGrant.objects.create(
            user=user,
            role=role,
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(user.has_feature_permission("reports.manage"))

    def test_has_role_includes_active_temporary_grant(self):
        user = User.objects.create_user(
            username="temp_bursar",
            password="pass1234",
            role=User.Role.PARENT,
        )
        user.roles.clear()
        self.assertFalse(has_role(user, "BURSAR"))
        role = AccessRole.objects.get(code="BURSAR")
        TemporaryRoleGrant.objects.create(
            user=user,
            role=role,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.assertTrue(has_role(user, "BURSAR"))
