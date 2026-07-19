"""G7 — a tenant must not activate silently ownerless.

``resolve_provisioning_contact_email`` can come back empty (an operator
create_school with no email AND no SignupVerification), so the admin_user step
skips ``ensure_admin_user_for_school`` and Phase A activates a live tenant with no
owner: is_active=True, workspace present, but nobody can log in and there is no
setup link to reveal. The guard does NOT block activation (an owner can be
assigned out of band via the identity console) but flags the state loudly -- a
``needs_owner`` marker + a ``PROVISION_NO_OWNER`` event -- and clears it once an
owner exists. It queries the membership, not the passed admin_user, so a
prior-drive owner counts and a suspended-only owner does not.
"""
from __future__ import annotations

import uuid
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership, SchoolProvisioningEvent
from apps.schools.tasks import _activate_portal_phase_a

_PROBE = "apps.schools.tenant_workspace.tenant_workspace_exists"


class OwnerlessActivationGuardTests(TestCase):
    def _school(self) -> School:
        slug = f"own-{uuid.uuid4().hex[:8]}"
        return School.objects.create(
            name="Ownerless", slug=slug, subdomain=slug, is_active=False
        )

    def _activate(self, school, admin_user=None):
        # None probe = the RLS/SQLite "unknowable" answer -> activation proceeds.
        with mock.patch(_PROBE, return_value=None):
            _activate_portal_phase_a(
                school,
                school_id=str(school.pk),
                contact_email="",
                admin_user=admin_user,
                wf_run=None,
                pulse=lambda *a, **k: None,
            )

    def _owner(self, school, *, suspended=False):
        user = User.objects.create_user(
            username=f"o-{uuid.uuid4().hex[:6]}",
            email=f"{uuid.uuid4().hex[:6]}@x.com",
            password="pass12345678",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=user,
            school=school,
            role=User.Role.ADMIN,
            is_primary=True,
            is_school_owner=True,
            suspended_at=timezone.now() if suspended else None,
        )
        return user

    def _needs_owner(self, school) -> bool:
        school.refresh_from_db()
        return bool((school.settings or {}).get("provisioning", {}).get("needs_owner"))

    def _has_no_owner_event(self, school) -> bool:
        return SchoolProvisioningEvent.objects.filter(
            school=school, event_type="PROVISION_NO_OWNER"
        ).exists()

    def test_ownerless_activation_is_flagged(self):
        school = self._school()
        self._activate(school)
        self.assertTrue(
            self._needs_owner(school), "ownerless activation must set needs_owner"
        )
        self.assertTrue(
            self._has_no_owner_event(school),
            "ownerless activation must record a PROVISION_NO_OWNER event",
        )

    def test_owned_school_is_not_flagged(self):
        school = self._school()
        self._owner(school)
        self._activate(school, admin_user=None)  # param None, but a membership exists
        self.assertFalse(self._needs_owner(school))
        self.assertFalse(self._has_no_owner_event(school))

    def test_suspended_only_owner_counts_as_ownerless(self):
        school = self._school()
        self._owner(school, suspended=True)  # the only owner is suspended
        self._activate(school)
        self.assertTrue(
            self._needs_owner(school),
            "a school whose only owner is suspended has no one who can log in",
        )

    def test_flag_clears_once_owner_added(self):
        school = self._school()
        self._activate(school)  # ownerless -> flagged
        self.assertTrue(self._needs_owner(school))
        self._owner(school)  # owner assigned out of band
        self._activate(school)  # idempotent re-activation clears the flag
        self.assertFalse(self._needs_owner(school))
