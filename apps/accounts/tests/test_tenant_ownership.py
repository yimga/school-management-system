"""School ownership — grant / revoke / transfer endpoints + creator-as-owner.

Covers the security boundary the 3-vote flagged: ownership is gated on *actual
ownership* (the per-school is_school_owner flag), never the broad identity-hub
manage role set; the school can never be left without an owner; and ownership is
a membership flag (role stays ADMIN), so the SUPERADMIN middleware trap is never
tripped.
"""

from __future__ import annotations

import uuid

from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import Http404
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.accounts.views_tenant_identity import (
    _is_school_owner,
    tenant_identity_grant_ownership,
    tenant_identity_offboard,
    tenant_identity_revoke_ownership,
    tenant_identity_transfer_ownership,
)
from apps.schools.models import School, SchoolMembership


def _make_school(prefix: str) -> School:
    return School.objects.create(
        name=f"{prefix} School",
        slug=f"{prefix}-{uuid.uuid4().hex[:10]}",
        subdomain=f"{prefix}-{uuid.uuid4().hex[:10]}",
        is_active=True,
    )


def _make_user(prefix: str, role=User.Role.TEACHER, **kw) -> User:
    return User.objects.create_user(
        username=f"{prefix}-{uuid.uuid4().hex[:6]}",
        email=f"{prefix}-{uuid.uuid4().hex[:6]}@example.com",
        password="pass12345678",
        role=role,
        **kw,
    )


class OwnershipBase(TestCase):
    def setUp(self) -> None:
        self.school = _make_school("own")
        self.other_school = _make_school("other")

        self.owner = _make_user("owner", role=User.Role.ADMIN, is_staff=True)
        self.teacher = _make_user("tch", role=User.Role.TEACHER)
        # An ADMIN who can manage the identity hub but is NOT an owner — the exact
        # actor the broad role gate would (wrongly) let escalate into ownership.
        self.plain_admin = _make_user("padm", role=User.Role.ADMIN, is_staff=True)
        self.outsider = _make_user("out", role=User.Role.ADMIN)

        SchoolMembership.objects.create(
            user=self.owner, school=self.school, role=User.Role.ADMIN,
            is_primary=True, is_school_owner=True,
        )
        SchoolMembership.objects.create(
            user=self.teacher, school=self.school, role=User.Role.TEACHER,
            is_primary=True, is_school_owner=False,
        )
        SchoolMembership.objects.create(
            user=self.plain_admin, school=self.school, role=User.Role.ADMIN,
            is_primary=True, is_school_owner=False,
        )
        # outsider belongs only to other_school
        SchoolMembership.objects.create(
            user=self.outsider, school=self.other_school, role=User.Role.ADMIN,
            is_primary=True, is_school_owner=True,
        )
        self.factory = RequestFactory()

    def _post(self, user, user_id):
        request = self.factory.post(f"/backend/identity/{user_id}/x/")
        request.user = user
        request.school = self.school
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def _membership(self, user, school=None):
        return SchoolMembership.objects.get(school=school or self.school, user=user)


class IsSchoolOwnerHelperTests(OwnershipBase):
    def test_owner_member_is_owner(self) -> None:
        self.assertTrue(_is_school_owner(self.owner, self.school))

    def test_non_owner_member_is_not_owner(self) -> None:
        self.assertFalse(_is_school_owner(self.plain_admin, self.school))
        self.assertFalse(_is_school_owner(self.teacher, self.school))

    def test_superuser_is_owner(self) -> None:
        su = _make_user("su", role=User.Role.ADMIN, is_staff=True, is_superuser=True)
        self.assertTrue(_is_school_owner(su, self.school))

    def test_anonymous_is_not_owner(self) -> None:
        self.assertFalse(_is_school_owner(AnonymousUser(), self.school))


class GrantOwnershipTests(OwnershipBase):
    def test_owner_grants_co_owner_and_promotes_to_admin(self) -> None:
        resp = tenant_identity_grant_ownership(
            self._post(self.owner, self.teacher.pk), user_id=self.teacher.pk
        )
        self.assertEqual(resp.status_code, 302)
        m = self._membership(self.teacher)
        self.assertTrue(m.is_school_owner)
        self.assertEqual(m.role, User.Role.ADMIN)
        # original owner retained — multi-owner
        self.assertTrue(self._membership(self.owner).is_school_owner)

    def test_non_owner_admin_cannot_grant(self) -> None:
        resp = tenant_identity_grant_ownership(
            self._post(self.plain_admin, self.teacher.pk), user_id=self.teacher.pk
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(self._membership(self.teacher).is_school_owner)

    def test_grant_cross_tenant_target_rejected(self) -> None:
        # Target is a member only of other_school → the school-scoped membership
        # lookup fails → Http404 (the URL dispatcher renders this as a 404 in prod;
        # called directly here, we assert the exception). No cross-tenant mutation.
        with self.assertRaises(Http404):
            tenant_identity_grant_ownership(
                self._post(self.owner, self.outsider.pk), user_id=self.outsider.pk
            )
        self.assertTrue(
            self._membership(self.outsider, self.other_school).is_school_owner
        )

    def test_granting_does_not_set_user_role_superadmin(self) -> None:
        tenant_identity_grant_ownership(
            self._post(self.owner, self.teacher.pk), user_id=self.teacher.pk
        )
        self.teacher.refresh_from_db()
        # The user-level role (read by the SUPERADMIN tenant-redirect middleware)
        # must NOT become SUPERADMIN — ownership is a membership flag only.
        self.assertNotEqual(self.teacher.role, "SUPERADMIN")


class RevokeOwnershipTests(OwnershipBase):
    def test_cannot_remove_last_owner(self) -> None:
        resp = tenant_identity_revoke_ownership(
            self._post(self.owner, self.owner.pk), user_id=self.owner.pk
        )
        self.assertEqual(resp.status_code, 302)
        # still the owner — last-owner guard held
        self.assertTrue(self._membership(self.owner).is_school_owner)

    def test_revoke_succeeds_with_two_owners(self) -> None:
        SchoolMembership.objects.filter(user=self.teacher, school=self.school).update(
            is_school_owner=True
        )
        resp = tenant_identity_revoke_ownership(
            self._post(self.owner, self.teacher.pk), user_id=self.teacher.pk
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(self._membership(self.teacher).is_school_owner)
        self.assertTrue(self._membership(self.owner).is_school_owner)

    def test_owner_can_step_down_when_co_owner_exists(self) -> None:
        SchoolMembership.objects.filter(user=self.teacher, school=self.school).update(
            is_school_owner=True
        )
        resp = tenant_identity_revoke_ownership(
            self._post(self.owner, self.owner.pk), user_id=self.owner.pk
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(self._membership(self.owner).is_school_owner)
        self.assertTrue(self._membership(self.teacher).is_school_owner)

    def test_non_owner_cannot_revoke(self) -> None:
        resp = tenant_identity_revoke_ownership(
            self._post(self.plain_admin, self.owner.pk), user_id=self.owner.pk
        )
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(self._membership(self.owner).is_school_owner)


class TransferOwnershipTests(OwnershipBase):
    def test_transfer_promotes_target_and_steps_caller_down(self) -> None:
        resp = tenant_identity_transfer_ownership(
            self._post(self.owner, self.teacher.pk), user_id=self.teacher.pk
        )
        self.assertEqual(resp.status_code, 302)
        t = self._membership(self.teacher)
        self.assertTrue(t.is_school_owner)
        self.assertEqual(t.role, User.Role.ADMIN)
        self.assertFalse(self._membership(self.owner).is_school_owner)
        # school still has exactly one owner — never orphaned
        self.assertEqual(
            SchoolMembership.objects.filter(
                school=self.school, is_school_owner=True
            ).count(),
            1,
        )

    def test_transfer_to_self_rejected(self) -> None:
        resp = tenant_identity_transfer_ownership(
            self._post(self.owner, self.owner.pk), user_id=self.owner.pk
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(self._membership(self.owner).is_school_owner)

    def test_non_owner_cannot_transfer(self) -> None:
        resp = tenant_identity_transfer_ownership(
            self._post(self.plain_admin, self.teacher.pk), user_id=self.teacher.pk
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(self._membership(self.teacher).is_school_owner)

    def test_superuser_without_membership_cannot_transfer(self) -> None:
        # A platform superuser passes the owner gate but holds no membership here,
        # so "transfer" (which steps the caller down) is refused and nothing moves;
        # they would use "Make co-owner" instead.
        su = _make_user("su", role=User.Role.ADMIN, is_staff=True, is_superuser=True)
        resp = tenant_identity_transfer_ownership(
            self._post(su, self.teacher.pk), user_id=self.teacher.pk
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(self._membership(self.teacher).is_school_owner)
        self.assertTrue(self._membership(self.owner).is_school_owner)


class SuspendedOwnerGuardTests(OwnershipBase):
    """A suspended owner holds no authority, so the delegation guards must treat
    ownership on the ACTIVE-owner axis — never the raw is_school_owner flag — or
    the school can be stranded with an owner who cannot act."""

    def _suspend(self, user) -> None:
        from django.utils import timezone

        SchoolMembership.objects.filter(user=user, school=self.school).update(
            suspended_at=timezone.now()
        )

    def _make_owner(self, user) -> None:
        SchoolMembership.objects.filter(user=user, school=self.school).update(
            is_school_owner=True
        )

    # --- grant / transfer must refuse a suspended target ----------------------

    def test_grant_ownership_to_suspended_member_refused(self) -> None:
        self._suspend(self.teacher)
        resp = tenant_identity_grant_ownership(
            self._post(self.owner, self.teacher.pk), user_id=self.teacher.pk
        )
        self.assertEqual(resp.status_code, 302)
        # Ghost owner not created — suspended member stays a non-owner.
        self.assertFalse(self._membership(self.teacher).is_school_owner)

    def test_transfer_ownership_to_suspended_member_refused(self) -> None:
        self._suspend(self.teacher)
        resp = tenant_identity_transfer_ownership(
            self._post(self.owner, self.teacher.pk), user_id=self.teacher.pk
        )
        self.assertEqual(resp.status_code, 302)
        # No stranding: caller keeps ownership, suspended target is not promoted.
        self.assertTrue(self._membership(self.owner).is_school_owner)
        self.assertFalse(self._membership(self.teacher).is_school_owner)

    # --- revoke must guard on ACTIVE owners, not the raw flag -----------------

    def test_cannot_step_down_when_only_other_owner_is_suspended(self) -> None:
        # owner (active) + teacher (owner, but suspended). Raw owner_count == 2, so
        # the OLD total-count guard would have let the active owner step down and
        # strand the school with only a suspended owner. The active-count guard holds.
        self._make_owner(self.teacher)
        self._suspend(self.teacher)
        resp = tenant_identity_revoke_ownership(
            self._post(self.owner, self.owner.pk), user_id=self.owner.pk
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(self._membership(self.owner).is_school_owner)

    def test_can_revoke_a_suspended_co_owner(self) -> None:
        # Revoking a suspended owner never reduces the active-owner pool, so it's
        # always allowed as long as an active owner remains (self.owner).
        self._make_owner(self.teacher)
        self._suspend(self.teacher)
        resp = tenant_identity_revoke_ownership(
            self._post(self.owner, self.teacher.pk), user_id=self.teacher.pk
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(self._membership(self.teacher).is_school_owner)
        self.assertTrue(self._membership(self.owner).is_school_owner)


class OffboardOwnerGuardTests(OwnershipBase):
    """Deleting an owner's membership is owner-only and can't strip the last
    active owner — the broad manage gate is not enough to remove an owner."""

    def _make_su(self):
        return _make_user(
            "su", role=User.Role.ADMIN, is_staff=True, is_superuser=True
        )

    def _make_owner(self, user) -> None:
        SchoolMembership.objects.filter(user=user, school=self.school).update(
            is_school_owner=True
        )

    def _exists(self, user) -> bool:
        return SchoolMembership.objects.filter(
            school=self.school, user=user
        ).exists()

    def test_non_owner_manager_cannot_offboard_an_owner(self) -> None:
        # plain_admin can manage the identity hub (ADMIN) but is NOT an owner — it
        # must not be able to delete the owner's membership.
        resp = tenant_identity_offboard(
            self._post(self.plain_admin, self.owner.pk), user_id=self.owner.pk
        )
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(self._exists(self.owner))
        self.assertTrue(self._membership(self.owner).is_school_owner)

    def test_cannot_offboard_the_last_active_owner(self) -> None:
        # A suspended co-owner does not count; owner is the last ACTIVE owner. A
        # superuser doing support/recovery (a MEMBER here, so it clears the broad
        # manage gate whose membership check precedes the superuser bypass) still
        # can't delete the last active owner — the raw 2-owner count must not rescue
        # the guard. Grant ownership to another active member first.
        self._make_owner(self.teacher)
        from django.utils import timezone

        SchoolMembership.objects.filter(user=self.teacher, school=self.school).update(
            suspended_at=timezone.now()
        )
        su = self._make_su()
        SchoolMembership.objects.create(
            user=su, school=self.school, role=User.Role.ADMIN, is_school_owner=False,
        )
        resp = tenant_identity_offboard(
            self._post(su, self.owner.pk), user_id=self.owner.pk
        )
        self.assertEqual(resp.status_code, 302)  # refused with a message, not deleted
        self.assertTrue(self._exists(self.owner))

    def test_owner_can_offboard_a_co_owner_when_two_active(self) -> None:
        self._make_owner(self.teacher)  # now two active owners
        resp = tenant_identity_offboard(
            self._post(self.owner, self.teacher.pk), user_id=self.teacher.pk
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(self._exists(self.teacher))
        self.assertTrue(self._exists(self.owner))

    def test_manager_can_still_offboard_a_regular_member(self) -> None:
        # The broad-gate path for non-owner targets is unchanged.
        resp = tenant_identity_offboard(
            self._post(self.plain_admin, self.teacher.pk), user_id=self.teacher.pk
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(self._exists(self.teacher))


class CreatorIsOwnerTests(TestCase):
    def test_ensure_admin_user_for_school_sets_owner(self) -> None:
        from apps.schools.tasks import ensure_admin_user_for_school

        school = _make_school("boot")
        admin_user, _created = ensure_admin_user_for_school(
            school, "founder@example.com"
        )
        self.assertIsNotNone(admin_user)
        m = SchoolMembership.objects.get(school=school, user=admin_user)
        self.assertTrue(m.is_school_owner)
        self.assertEqual(m.role, User.Role.ADMIN)


class AuditSchoolOwnersCommandTests(TestCase):
    def test_repair_assigns_founding_owner(self) -> None:
        from io import StringIO

        from django.core.management import call_command

        school = _make_school("orphan")
        admin = _make_user("oadm", role=User.Role.ADMIN)
        teacher = _make_user("otch", role=User.Role.TEACHER)
        # populated school, but no owner flag anywhere → ownerless
        SchoolMembership.objects.create(
            user=teacher, school=school, role=User.Role.TEACHER, is_school_owner=False
        )
        SchoolMembership.objects.create(
            user=admin, school=school, role=User.Role.ADMIN, is_school_owner=False
        )
        out = StringIO()
        call_command("audit_school_owners", "--repair", stdout=out)
        # earliest ADMIN becomes the owner
        self.assertTrue(
            SchoolMembership.objects.get(school=school, user=admin).is_school_owner
        )
        self.assertFalse(
            SchoolMembership.objects.get(school=school, user=teacher).is_school_owner
        )
