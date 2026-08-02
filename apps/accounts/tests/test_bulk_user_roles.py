"""T20: bulk role assignment — grant ONE role to MANY members in a single POST.

The RBAC dashboard already assigns many roles to one user (``user_roles``). This
covers the inverse group grant (``bulk_user_roles``): scoping, the additive
multi-member grant, and the cross-school guard.
"""

from __future__ import annotations

import uuid

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.forms import BulkUserRolesForm
from apps.accounts.models import AccessRole, User
from apps.schools.models import School, SchoolMembership


class BulkUserRolesTests(TestCase):
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
        self.teacher1 = User.objects.create_user(
            username=f"t1-{uuid.uuid4().hex[:6]}",
            email="t1@example.com",
            password="pass12345678",
            role=User.Role.TEACHER,
        )
        self.teacher2 = User.objects.create_user(
            username=f"t2-{uuid.uuid4().hex[:6]}",
            email="t2@example.com",
            password="pass12345678",
            role=User.Role.TEACHER,
        )
        self.user_b_only = User.objects.create_user(
            username=f"userb-{uuid.uuid4().hex[:6]}",
            email="userb@example.com",
            password="pass12345678",
            role=User.Role.TEACHER,
        )
        for member in (self.admin_a, self.teacher1, self.teacher2):
            SchoolMembership.objects.create(
                user=member,
                school=self.school_a,
                role=member.role,
                is_primary=(member is self.admin_a),
            )
        SchoolMembership.objects.create(
            user=self.user_b_only,
            school=self.school_b,
            role=User.Role.TEACHER,
            is_primary=True,
        )
        self.role = AccessRole.objects.create(
            code="form_teacher", name="Form Teacher", school=self.school_a
        )
        # The admin is a superuser, so strict MFA enforcement walls the RBAC
        # dashboard behind device enrollment. Give them a confirmed TOTP device
        # so `has_device` is true (the _login_school_a session also marks MFA
        # verified) and the request reaches the view.
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.create(user=self.admin_a, name="default", confirmed=True)

    def _login_school_a(self) -> Client:
        client = Client()
        client.force_login(self.admin_a)
        session = client.session
        session["school_id"] = str(self.school_a.id)
        # The RBAC dashboard is behind the post-login MFA gate; mark this session
        # MFA-verified so the request reaches the view instead of being redirected
        # to /authentication/mfa/setup/ (the canonical test pattern — see
        # apps/feedback/tests/test_voice_of_customer_dashboard.py).
        session["mfa_verified"] = True
        session.save()
        return client

    def test_form_users_scoped_to_school(self) -> None:
        form = BulkUserRolesForm(school=self.school_a)
        ids = set(form.fields["users"].queryset.values_list("pk", flat=True))
        self.assertIn(self.teacher1.pk, ids)
        self.assertIn(self.teacher2.pk, ids)
        self.assertNotIn(self.user_b_only.pk, ids)

    def test_bulk_grant_assigns_role_to_many(self) -> None:
        client = self._login_school_a()
        response = client.post(
            reverse("accounts:rbac"),
            {
                "form_type": "bulk_user_roles",
                "bulk_user_roles-role": str(self.role.pk),
                "bulk_user_roles-users": [
                    str(self.teacher1.pk),
                    str(self.teacher2.pk),
                ],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.teacher1.roles.filter(pk=self.role.pk).exists())
        self.assertTrue(self.teacher2.roles.filter(pk=self.role.pk).exists())

    def test_bulk_grant_is_additive(self) -> None:
        existing = AccessRole.objects.create(
            code="exam_officer", name="Exam Officer", school=self.school_a
        )
        self.teacher1.roles.add(existing)
        client = self._login_school_a()
        client.post(
            reverse("accounts:rbac"),
            {
                "form_type": "bulk_user_roles",
                "bulk_user_roles-role": str(self.role.pk),
                "bulk_user_roles-users": [str(self.teacher1.pk)],
            },
        )
        # The prior role is preserved; the new one is added on top.
        self.assertTrue(self.teacher1.roles.filter(pk=existing.pk).exists())
        self.assertTrue(self.teacher1.roles.filter(pk=self.role.pk).exists())

    def test_bulk_grant_rejects_cross_school_user(self) -> None:
        client = self._login_school_a()
        client.post(
            reverse("accounts:rbac"),
            {
                "form_type": "bulk_user_roles",
                "bulk_user_roles-role": str(self.role.pk),
                # A school-B user is not in school A's scoped queryset → the form
                # rejects the choice → no grant happens.
                "bulk_user_roles-users": [str(self.user_b_only.pk)],
            },
        )
        self.user_b_only.refresh_from_db()
        self.assertFalse(self.user_b_only.roles.filter(pk=self.role.pk).exists())
