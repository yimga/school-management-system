"""Tenant RBAC school-scoping — IDOR guards on user pickers and membership POST."""

from __future__ import annotations

import uuid

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.forms import UserRoleForm
from apps.accounts.models import AccessRole, User
from apps.schools.models import School, SchoolMembership


class TenantRbacScopeTests(TestCase):
    def setUp(self) -> None:
        self.school_a = School.objects.create(
            name="School A",
            slug=f"sa-{uuid.uuid4().hex[:10]}",
            subdomain=f"sa-{uuid.uuid4().hex[:10]}",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name="School B",
            slug=f"sb-{uuid.uuid4().hex[:10]}",
            subdomain=f"sb-{uuid.uuid4().hex[:10]}",
            is_active=True,
        )
        self.admin_a = User.objects.create_user(
            username=f"admina-{uuid.uuid4().hex[:6]}",
            email="admina@example.com",
            password="pass12345678",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.user_b_only = User.objects.create_user(
            username=f"userb-{uuid.uuid4().hex[:6]}",
            email="userb@example.com",
            password="pass12345678",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.create(
            user=self.admin_a,
            school=self.school_a,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        SchoolMembership.objects.create(
            user=self.user_b_only,
            school=self.school_b,
            role=User.Role.TEACHER,
            is_primary=True,
        )
        self.role = AccessRole.objects.create(code="auditor", name="Auditor")
        # admin_a is a superuser → strict MFA enforcement walls the RBAC dashboard
        # behind device enrollment. Give them a confirmed TOTP device so the
        # request reaches the view (the login helper also marks MFA verified).
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.create(user=self.admin_a, name="default", confirmed=True)

    def _login_school_a(self) -> Client:
        client = Client()
        client.force_login(self.admin_a)
        session = client.session
        session["school_id"] = str(self.school_a.id)
        session["mfa_verified"] = True
        session.save()
        return client

    def test_user_role_form_scoped_to_school(self) -> None:
        form = UserRoleForm(school=self.school_a)
        ids = set(form.fields["user"].queryset.values_list("pk", flat=True))
        self.assertIn(self.admin_a.pk, ids)
        self.assertNotIn(self.user_b_only.pk, ids)

    def test_rbac_get_edit_role_rejects_other_school_role(self) -> None:
        role_b = AccessRole.objects.create(
            code="bursar_b",
            name="Bursar B",
            school=self.school_b,
        )
        client = self._login_school_a()
        response = client.get(
            reverse("accounts:rbac"),
            {"edit_role": str(role_b.pk)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context.get("edit_role_id"))

    def test_rbac_post_rejects_cross_school_user(self) -> None:
        client = self._login_school_a()
        response = client.post(
            reverse("accounts:rbac"),
            {
                "form_type": "user_roles",
                "user_role-user": str(self.user_b_only.pk),
                "user_role-roles": [str(self.role.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.user_b_only.refresh_from_db()
        self.assertFalse(self.user_b_only.roles.filter(pk=self.role.pk).exists())
