"""RBAC helpers for Wave 4 schoolops surfaces (permissions.py)."""

import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase, TestCase

from apps.accounts.permissions import (
    OPS_CLINIC_ROLE_CODES,
    OPS_EXTENDED_MODULE_ROLE_CODES,
    user_can_access_ops_clinic,
    user_can_access_ops_extended_modules,
)

User = get_user_model()


class OpsRoleHelpersContractTests(SimpleTestCase):
    def test_role_code_sets_non_empty(self):
        self.assertTrue(OPS_EXTENDED_MODULE_ROLE_CODES)
        self.assertTrue(OPS_CLINIC_ROLE_CODES)
        self.assertTrue(OPS_CLINIC_ROLE_CODES.issubset(OPS_EXTENDED_MODULE_ROLE_CODES))


class OpsRoleHelpersBehaviorTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username=f"u-{uuid.uuid4().hex[:8]}",
            email="ops@test.invalid",
            password="x",
            role=User.Role.ADMIN,
        )
        self.principal = User.objects.create_user(
            username=f"p-{uuid.uuid4().hex[:8]}",
            email="pr@test.invalid",
            password="x",
            role=User.Role.PRINCIPAL,
        )
        self.teacher = User.objects.create_user(
            username=f"t-{uuid.uuid4().hex[:8]}",
            email="t@test.invalid",
            password="x",
            role=User.Role.TEACHER,
        )

    def test_admin_principal_ops_and_clinic(self):
        self.assertTrue(user_can_access_ops_extended_modules(self.admin))
        self.assertTrue(user_can_access_ops_clinic(self.admin))
        self.assertTrue(user_can_access_ops_extended_modules(self.principal))
        self.assertTrue(user_can_access_ops_clinic(self.principal))

    def test_teacher_denied_ops(self):
        self.assertFalse(user_can_access_ops_extended_modules(self.teacher))
        self.assertFalse(user_can_access_ops_clinic(self.teacher))

    def test_anonymous_denied(self):
        self.assertFalse(user_can_access_ops_extended_modules(AnonymousUser()))
        self.assertFalse(user_can_access_ops_clinic(AnonymousUser()))
