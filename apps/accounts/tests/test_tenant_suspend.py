"""T7: suspend / reactivate a member.

Suspension revokes a member's management + ownership authority and kills their
live sessions, without deleting the membership (so it's reversible). Owner-gated,
with self and last-active-owner guards mirroring revoke-ownership.
"""

from __future__ import annotations

import uuid

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.accounts.views_tenant_identity import (
    _can_manage_tenant_identity,
    _is_school_owner,
    tenant_identity_reactivate,
    tenant_identity_suspend,
)
from apps.schools.models import School, SchoolMembership


def _make_school(prefix: str) -> School:
    return School.objects.create(
        name=f"{prefix} School",
        slug=f"{prefix}-{uuid.uuid4().hex[:10]}",
        subdomain=f"{prefix}-{uuid.uuid4().hex[:10]}",
        is_active=True,
    )


def _make_user(prefix: str, role=User.Role.ADMIN, **kw) -> User:
    return User.objects.create_user(
        username=f"{prefix}-{uuid.uuid4().hex[:6]}",
        email=f"{prefix}-{uuid.uuid4().hex[:6]}@example.com",
        password="pass12345678",
        role=role,
        **kw,
    )


class SuspendBase(TestCase):
    def setUp(self) -> None:
        self.school = _make_school("susp")
        self.owner = _make_user("owner", is_staff=True)
        # ADMIN who can manage the identity hub but is NOT an owner.
        self.admin = _make_user("adm", is_staff=True)
        self.co_owner = _make_user("co", is_staff=True)
        SchoolMembership.objects.create(
            user=self.owner, school=self.school, role=User.Role.ADMIN,
            is_primary=True, is_school_owner=True,
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role=User.Role.ADMIN,
            is_school_owner=False,
        )
        SchoolMembership.objects.create(
            user=self.co_owner, school=self.school, role=User.Role.ADMIN,
            is_school_owner=True,
        )
        self.factory = RequestFactory()

    def _post(self, user, user_id):
        request = self.factory.post(f"/backend/identity/{user_id}/x/")
        request.user = user
        request.school = self.school
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def _m(self, user):
        return SchoolMembership.objects.get(school=self.school, user=user)


class SuspendReactivateTests(SuspendBase):
    def test_owner_suspends_member_revokes_management(self) -> None:
        self.assertTrue(_can_manage_tenant_identity(self.admin, self.school))
        resp = tenant_identity_suspend(
            self._post(self.owner, self.admin.pk), user_id=self.admin.pk
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIsNotNone(self._m(self.admin).suspended_at)
        # Suspension strips management authority.
        self.assertFalse(_can_manage_tenant_identity(self.admin, self.school))

    def test_reactivate_restores_authority(self) -> None:
        tenant_identity_suspend(
            self._post(self.owner, self.admin.pk), user_id=self.admin.pk
        )
        resp = tenant_identity_reactivate(
            self._post(self.owner, self.admin.pk), user_id=self.admin.pk
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIsNone(self._m(self.admin).suspended_at)
        self.assertTrue(_can_manage_tenant_identity(self.admin, self.school))

    def test_suspended_owner_loses_ownership_actions(self) -> None:
        tenant_identity_suspend(
            self._post(self.owner, self.co_owner.pk), user_id=self.co_owner.pk
        )
        self.assertFalse(_is_school_owner(self.co_owner, self.school))

    def test_non_owner_cannot_suspend(self) -> None:
        resp = tenant_identity_suspend(
            self._post(self.admin, self.co_owner.pk), user_id=self.co_owner.pk
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIsNone(self._m(self.co_owner).suspended_at)

    def test_cannot_suspend_self(self) -> None:
        resp = tenant_identity_suspend(
            self._post(self.owner, self.owner.pk), user_id=self.owner.pk
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIsNone(self._m(self.owner).suspended_at)

    def test_cannot_suspend_last_active_owner(self) -> None:
        su = _make_user("su", is_staff=True, is_superuser=True)
        # Suspend co_owner first → `owner` becomes the last active owner.
        tenant_identity_suspend(self._post(su, self.co_owner.pk), user_id=self.co_owner.pk)
        self.assertIsNotNone(self._m(self.co_owner).suspended_at)
        # Even a superuser can't suspend the last active owner.
        resp = tenant_identity_suspend(self._post(su, self.owner.pk), user_id=self.owner.pk)
        self.assertEqual(resp.status_code, 302)
        self.assertIsNone(self._m(self.owner).suspended_at)

    def test_suspend_revokes_target_live_sessions(self) -> None:
        store = SessionStore()
        store["_auth_user_id"] = str(self.admin.pk)
        store.save()
        key = store.session_key
        self.assertTrue(Session.objects.filter(session_key=key).exists())
        tenant_identity_suspend(
            self._post(self.owner, self.admin.pk), user_id=self.admin.pk
        )
        self.assertFalse(Session.objects.filter(session_key=key).exists())
