"""AccessRole school FK — catalog isolation with global template inheritance."""

from __future__ import annotations

import uuid

from django.db import IntegrityError
from django.test import TestCase

from apps.accounts.access_roles import role_applies_to_school, roles_queryset_for_school
from apps.accounts.models import AccessRole, Permission, User
from apps.schools.models import School


class AccessRoleSchoolScopeTests(TestCase):
    def setUp(self) -> None:
        self.school_a = School.objects.create(
            name="Scope A",
            slug=f"sca-{uuid.uuid4().hex[:10]}",
            subdomain=f"sca-{uuid.uuid4().hex[:10]}",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name="Scope B",
            slug=f"scb-{uuid.uuid4().hex[:10]}",
            subdomain=f"scb-{uuid.uuid4().hex[:10]}",
            is_active=True,
        )
        self.global_role = AccessRole.objects.create(
            code="global_template",
            name="Global template",
            school=None,
        )
        self.role_a = AccessRole.objects.create(
            code="local_only",
            name="School A local",
            school=self.school_a,
        )
        self.role_b = AccessRole.objects.create(
            code="local_only",
            name="School B local",
            school=self.school_b,
        )

    def test_roles_queryset_includes_global_and_tenant(self) -> None:
        qs = roles_queryset_for_school(self.school_a)
        codes = set(qs.values_list("code", flat=True))
        self.assertIn("global_template", codes)
        self.assertIn("local_only", codes)
        self.assertEqual(qs.filter(school=self.school_b).count(), 0)

    def test_role_applies_to_school(self) -> None:
        self.assertTrue(role_applies_to_school(self.global_role, self.school_a))
        self.assertTrue(role_applies_to_school(self.role_a, self.school_a))
        self.assertFalse(role_applies_to_school(self.role_a, self.school_b))

    def test_duplicate_code_per_school_allowed(self) -> None:
        self.assertEqual(
            AccessRole.objects.filter(code="local_only").count(),
            2,
        )

    def test_global_code_unique(self) -> None:
        with self.assertRaises(IntegrityError):
            AccessRole.objects.create(
                code="global_template",
                name="Duplicate global",
                school=None,
            )

    def test_has_feature_permission_respects_school_scoped_role(self) -> None:
        perm = Permission.objects.create(code="reports.view", name="View reports")
        self.role_a.permissions.add(perm)
        user = User.objects.create_user(
            username=f"scoped-{uuid.uuid4().hex[:6]}",
            email="scoped@example.com",
            password="pass12345678",
            role=User.Role.TEACHER,
        )
        user.roles.add(self.role_a)
        self.assertTrue(user.has_feature_permission("reports.view", school=self.school_a))
        self.assertFalse(user.has_feature_permission("reports.view", school=self.school_b))
