"""Guardian-linked parents get a SchoolMembership → offline password recovery works.

A parent who onboards via a guardian invite (``claim_invite`` →
``link_guardian_via_invite``) or the admission-number wizard
(``link_guardian_to_student``) is a login-capable tenant user; historically they
received only a ``StudentGuardian`` link and NO ``SchoolMembership``, which left
them invisible to the tenant identity roster and — because ``can_reset_target``
requires a membership — un-resettable by a tenant admin from the UI (the
offline-recovery hole, the sibling of the ``novijonongni`` symptom). These tests
lock the fix: both link paths now ensure a membership, the shared helper is
idempotent + primary-safe, and a backfill command repairs pre-existing accounts.
"""
import uuid
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.accounts.credential_reset import can_reset_target
from apps.accounts.models import User
from apps.accounts.services_link_child import link_guardian_to_student
from apps.accounts.tenant_identity import (
    ensure_school_membership,
    user_has_school_membership,
)
from apps.people.models import StudentGuardian, StudentProfile
from apps.portal.models import PendingGuardianInvite
from apps.portal.services import link_guardian_via_invite
from apps.schools.models import School, SchoolMembership


def _school(tag="g"):
    suffix = uuid.uuid4().hex[:8]
    return School.objects.create(
        name=f"School {tag}",
        slug=f"{tag}-{suffix}",
        subdomain=f"{tag}-{suffix}",
        is_active=True,
    )


def _parent():
    ident = uuid.uuid4().hex[:8]
    return User.objects.create_user(
        username=f"p-{ident}",
        email=f"{ident}@example.test",
        password="pass12345678",
        role=User.Role.PARENT,
    )


def _student(school, admission_number=""):
    return StudentProfile.objects.create(
        school=school,
        first_name="Kid",
        last_name="Doe",
        admission_number=admission_number or None,
    )


class EnsureSchoolMembershipHelperTests(TestCase):
    def test_creates_and_is_idempotent(self):
        school = _school()
        parent = _parent()
        membership, created = ensure_school_membership(
            parent, school, role=User.Role.PARENT
        )
        self.assertTrue(created)
        self.assertEqual(membership.role, User.Role.PARENT)
        self.assertTrue(membership.is_primary)  # first membership → primary

        # Second call is a no-op — no duplicate, created=False.
        _again, created_again = ensure_school_membership(
            parent, school, role=User.Role.PARENT
        )
        self.assertFalse(created_again)
        self.assertEqual(
            SchoolMembership.objects.filter(user=parent, school=school).count(), 1
        )

    def test_preserves_existing_primary_landing(self):
        parent = _parent()
        primary_school = _school("primary")
        other_school = _school("other")
        # An existing primary membership must not be demoted by a second ensure.
        SchoolMembership.objects.create(
            user=parent, school=primary_school, role=User.Role.PARENT, is_primary=True
        )
        membership, created = ensure_school_membership(
            parent, other_school, role=User.Role.PARENT
        )
        self.assertTrue(created)
        self.assertFalse(membership.is_primary)  # never steals primary
        self.assertTrue(
            SchoolMembership.objects.get(
                user=parent, school=primary_school
            ).is_primary
        )

    def test_bad_request_returns_none(self):
        self.assertEqual(ensure_school_membership(None, _school(), role="PARENT"), (None, False))
        self.assertEqual(ensure_school_membership(_parent(), None, role="PARENT"), (None, False))


class InviteClaimCreatesMembershipTests(TestCase):
    def test_invite_claim_creates_membership_and_enables_reset(self):
        school = _school()
        student = _student(school)
        parent = _parent()
        invite = PendingGuardianInvite.objects.create(
            student=student,
            relationship=PendingGuardianInvite.Relationship.GUARDIAN,
            preferred_contact=PendingGuardianInvite.PreferredContact.EMAIL,
        )

        # Before: a bare parent user has no membership on the school.
        self.assertFalse(user_has_school_membership(parent, school))

        link_guardian_via_invite(invite, parent, awarded_by=parent)

        # After: the claim carries a PARENT membership on the invite's school.
        self.assertTrue(user_has_school_membership(parent, school))
        membership = SchoolMembership.objects.get(user=parent, school=school)
        self.assertEqual(membership.role, User.Role.PARENT)

        # And that membership is exactly what makes the parent resettable by an
        # admin (can_reset_target requires a membership) — the gap this closes.
        actor = User.objects.create_user(
            username=f"a-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@example.test",
            password="pass12345678",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.assertTrue(can_reset_target(actor, parent, school))


class WizardLinkCreatesMembershipTests(TestCase):
    def test_admission_number_wizard_creates_membership(self):
        school = _school()
        student = _student(school, admission_number="ADM-0001")
        parent = _parent()

        result = link_guardian_to_student(
            school=school,
            actor_user_id=parent.pk,
            admission_number="ADM-0001",
            relationship="mother",
            preferred_contact="email",
        )
        self.assertTrue(result.get("ok"), msg=result)
        self.assertTrue(user_has_school_membership(parent, school))
        self.assertEqual(
            SchoolMembership.objects.get(user=parent, school=school).role,
            User.Role.PARENT,
        )


class BackfillGuardianMembershipsTests(TestCase):
    def _preexisting_guardian_without_membership(self, school):
        """Simulate a parent claimed BEFORE the fix: a guardian link, no membership."""
        parent = _parent()
        student = _student(school)
        StudentGuardian.objects.create(guardian_user=parent, student=student)
        self.assertFalse(user_has_school_membership(parent, school))
        return parent

    def test_dry_run_reports_but_writes_nothing(self):
        school = _school()
        parent = self._preexisting_guardian_without_membership(school)

        out = StringIO()
        call_command("backfill_guardian_memberships", stdout=out)

        self.assertIn("WOULD", out.getvalue())
        self.assertFalse(user_has_school_membership(parent, school))

    def test_apply_creates_membership_and_is_idempotent(self):
        school = _school()
        parent = self._preexisting_guardian_without_membership(school)

        call_command("backfill_guardian_memberships", "--apply")
        self.assertTrue(user_has_school_membership(parent, school))
        self.assertEqual(
            SchoolMembership.objects.get(user=parent, school=school).role,
            User.Role.PARENT,
        )

        # Re-run writes no duplicate.
        call_command("backfill_guardian_memberships", "--apply")
        self.assertEqual(
            SchoolMembership.objects.filter(user=parent, school=school).count(), 1
        )
