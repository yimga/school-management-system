"""Tests for the role-template signal: User.role -> user.roles (AccessRole) on create/update."""
from django.test import TestCase

from apps.accounts.models import AccessRole, User


class RoleTemplateSignalTests(TestCase):
    """Assert that creating or changing User.role applies the corresponding AccessRole."""

    def test_create_user_principal_gets_principal_access_role(self):
        user = User.objects.create_user(
            username="principal1",
            password="pass1234",
            role=User.Role.PRINCIPAL,
        )
        role_codes = list(user.roles.values_list("code", flat=True))
        self.assertEqual(role_codes, ["PRINCIPAL"], msg="Principal user should have PRINCIPAL AccessRole")

    def test_create_user_teacher_gets_teacher_access_role(self):
        user = User.objects.create_user(
            username="teacher1",
            password="pass1234",
            role=User.Role.TEACHER,
        )
        role_codes = list(user.roles.values_list("code", flat=True))
        self.assertEqual(role_codes, ["TEACHER"])

    def test_create_user_bursar_gets_bursar_access_role(self):
        user = User.objects.create_user(
            username="bursar1",
            password="pass1234",
            role=User.Role.BURSAR,
        )
        role_codes = list(user.roles.values_list("code", flat=True))
        self.assertEqual(role_codes, ["BURSAR"])

    def test_principal_has_expected_permission(self):
        user = User.objects.create_user(
            username="principal2",
            password="pass1234",
            role=User.Role.PRINCIPAL,
        )
        self.assertTrue(
            user.has_feature_permission("reports.manage"),
            msg="PRINCIPAL role should grant reports.manage",
        )

    def test_role_change_updates_user_roles(self):
        user = User.objects.create_user(
            username="switch_role",
            password="pass1234",
            role=User.Role.PARENT,
        )
        self.assertEqual(list(user.roles.values_list("code", flat=True)), ["PARENT"])
        user.role = User.Role.DEAN
        user.save()
        user.refresh_from_db()
        self.assertEqual(list(user.roles.values_list("code", flat=True)), ["DEAN"])

    def test_create_user_secretary_gets_secretary_access_role(self):
        user = User.objects.create_user(
            username="secretary1",
            password="pass1234",
            role=User.Role.SECRETARY,
        )
        role_codes = list(user.roles.values_list("code", flat=True))
        self.assertEqual(role_codes, ["SECRETARY"])
