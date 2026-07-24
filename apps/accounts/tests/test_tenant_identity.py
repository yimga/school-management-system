"""Tenant identity hub — roster, invite, accept, offboard."""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import TenantStaffInvite, User
from apps.accounts.tenant_identity import (
    get_effective_role,
    user_has_school_membership,
    users_queryset_for_school,
)
from apps.accounts.views_tenant_identity import (
    tenant_identity_invite,
    tenant_identity_regulator_grant,
    tenant_identity_roster,
    tenant_staff_invite_accept,
)
from apps.schools.models import School, SchoolMembership


class TenantIdentityHelperTests(TestCase):
    def setUp(self) -> None:
        self.school = School.objects.create(
            name="Identity School",
            slug=f"id-{uuid.uuid4().hex[:10]}",
            subdomain=f"id-{uuid.uuid4().hex[:10]}",
            is_active=True,
        )
        self.other_school = School.objects.create(
            name="Other School",
            slug=f"os-{uuid.uuid4().hex[:10]}",
            subdomain=f"os-{uuid.uuid4().hex[:10]}",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username=f"adm-{uuid.uuid4().hex[:6]}",
            email="admin-id@example.com",
            password="pass12345678",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.teacher = User.objects.create_user(
            username=f"tch-{uuid.uuid4().hex[:6]}",
            email="teacher-id@example.com",
            password="pass12345678",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.create(
            user=self.admin,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        SchoolMembership.objects.create(
            user=self.teacher,
            school=self.school,
            role=User.Role.TEACHER,
            is_primary=True,
        )
        SchoolMembership.objects.create(
            user=self.teacher,
            school=self.other_school,
            role=User.Role.ADMIN,
            is_primary=False,
        )

    def test_users_queryset_scoped_to_school(self) -> None:
        qs = users_queryset_for_school(self.school)
        usernames = set(qs.values_list("username", flat=True))
        self.assertIn(self.admin.username, usernames)
        self.assertIn(self.teacher.username, usernames)
        self.assertEqual(qs.count(), 2)

    def test_effective_role_prefers_membership(self) -> None:
        self.assertEqual(get_effective_role(self.teacher, self.school), "TEACHER")
        self.assertEqual(get_effective_role(self.teacher, self.other_school), "ADMIN")

    def test_membership_check(self) -> None:
        outsider = User.objects.create_user(
            username=f"out-{uuid.uuid4().hex[:6]}",
            email="out@example.com",
            password="pass12345678",
        )
        self.assertTrue(user_has_school_membership(self.admin, self.school))
        self.assertFalse(user_has_school_membership(outsider, self.school))


class TenantIdentityHubViewTests(TestCase):
    def setUp(self) -> None:
        self.school = School.objects.create(
            name="Hub School",
            slug=f"hub-{uuid.uuid4().hex[:10]}",
            subdomain=f"hub-{uuid.uuid4().hex[:10]}",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username=f"hubadm-{uuid.uuid4().hex[:6]}",
            email="hub-admin@example.com",
            password="pass12345678",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        SchoolMembership.objects.create(
            user=self.admin,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        self.factory = RequestFactory()

    def _request(self, user, method: str, path: str, data=None):
        data = data or {}
        if method == "GET":
            request = self.factory.get(path)
        else:
            request = self.factory.post(path, data)
        request.user = user
        request.school = self.school
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_roster_renders(self) -> None:
        response = tenant_identity_roster(
            self._request(self.admin, "GET", "/backend/identity/")
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8").lower()
        self.assertIn("staff identity", body)

    def test_invite_creates_pending_token(self) -> None:
        response = tenant_identity_invite(
            self._request(
                self.admin,
                "POST",
                "/backend/identity/invite/",
                {"email": "newstaff@example.com", "role": "TEACHER"},
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TenantStaffInvite.objects.filter(school=self.school).count(), 1)

    def test_invite_accept_creates_membership(self) -> None:
        invite = TenantStaffInvite.objects.create(
            school=self.school,
            email="accept@example.com",
            role="TEACHER",
            invited_by=self.admin,
            expires_at=timezone.now() + timedelta(days=3),
        )
        factory = RequestFactory()
        request = factory.post(
            f"/authentication/staff-invite/{invite.token}/",
            {
                "username": "acceptedstaff",
                "password": "longpass1234",
                "password2": "longpass1234",
            },
        )
        request.user = AnonymousUser()
        request.school = self.school
        request.session = {}
        request._messages = FallbackStorage(request)
        response = tenant_staff_invite_accept(request, token=invite.token)
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="acceptedstaff")
        self.assertTrue(
            SchoolMembership.objects.filter(user=user, school=self.school).exists()
        )
        invite.refresh_from_db()
        self.assertIsNotNone(invite.accepted_at)

    def test_regulator_grant_page_renders(self) -> None:
        response = tenant_identity_regulator_grant(
            self._request(self.admin, "GET", "/backend/identity/regulator-grant/")
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8").lower()
        self.assertIn("regulator", body)

    def test_teacher_cannot_access_roster(self) -> None:
        teacher = User.objects.create_user(
            username=f"hubt-{uuid.uuid4().hex[:6]}",
            email="hub-teacher@example.com",
            password="pass12345678",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.create(
            user=teacher,
            school=self.school,
            role=User.Role.TEACHER,
            is_primary=True,
        )
        # Since the 2026-07-09 PDP promotion the enforce guard denies BEFORE the
        # view body runs: PermissionDenied -> the branded 403 handler in a full
        # request cycle (same HTTP outcome as the old HttpResponseForbidden).
        from django.core.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            tenant_identity_roster(
                self._request(teacher, "GET", "/backend/identity/")
            )


class TenantIdentityUrlSmokeTests(SimpleTestCase):
    def test_named_urls_resolve(self) -> None:
        self.assertTrue(
            reverse("accounts:tenant_identity_roster").endswith("/backend/identity/")
        )
        self.assertIn(
            "staff-invite",
            reverse(
                "accounts:tenant_staff_invite_accept",
                kwargs={"token": uuid.uuid4()},
            ),
        )
        self.assertTrue(
            reverse("accounts:tenant_identity_regulator_grant").endswith(
                "/backend/identity/regulator-grant/"
            )
        )
