"""Transfer Wave A — passport dual-rail repair + TransferCase FSM.

Locks design §8 defect 1 (the API timeline reads ``StudentProfile.passport``
while passport_services wrote only ``StudentPassportMembership`` — a portal
passport was invisible to the API) and the §4 TransferCase state machine
(illegal transitions must raise, legal ones journal into ``history``).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.people.models import StudentPassport, StudentProfile
from apps.people.models_transfer import TransferCase, TransferStateError
from apps.people.passport_services import (
    get_or_create_passport_for_student,
    link_student_to_passport,
)
from apps.people.student_passport_models import StudentPassportMembership
from apps.schools.models import School

User = get_user_model()


class PassportDualRailTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Dual Rail A", slug="dualrail-a", subdomain="dualrail-a"
        )
        self.user = User.objects.create_user(username="dualrail-op", password="x")
        self.profile = StudentProfile.objects.create(
            school=self.school,
            first_name="Pass",
            last_name="Port",
            student_code="DR-001",
        )

    def test_create_path_sets_profile_fk(self):
        passport, created = get_or_create_passport_for_student(
            self.profile, self.user
        )
        self.assertTrue(created)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.passport_id, passport.pk)
        self.assertTrue(
            StudentPassportMembership.objects.filter(
                passport=passport, student_profile=self.profile
            ).exists()
        )

    def test_existing_membership_backlinks_fk(self):
        # Historic state: membership exists, FK was never written.
        passport = StudentPassport.objects.create()
        StudentPassportMembership.objects.create(
            passport=passport,
            school=self.school,
            student_profile=self.profile,
            consent_status=StudentPassportMembership.ConsentStatus.PRIVATE,
            role="",
        )
        self.assertIsNone(self.profile.passport_id)
        found, created = get_or_create_passport_for_student(self.profile, self.user)
        self.assertFalse(created)
        self.assertEqual(found.pk, passport.pk)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.passport_id, passport.pk)

    def test_link_second_school_sets_fk(self):
        other_school = School.objects.create(
            name="Dual Rail B", slug="dualrail-b", subdomain="dualrail-b"
        )
        second_profile = StudentProfile.objects.create(
            school=other_school,
            first_name="Pass",
            last_name="Port",
            student_code="DR-002",
        )
        passport, _ = get_or_create_passport_for_student(self.profile, self.user)
        link_student_to_passport(passport, second_profile, self.user)
        second_profile.refresh_from_db()
        self.assertEqual(second_profile.passport_id, passport.pk)

    def test_backfill_command_reconciles_both_directions(self):
        # Direction 1: membership without FK.
        passport = StudentPassport.objects.create()
        StudentPassportMembership.objects.create(
            passport=passport,
            school=self.school,
            student_profile=self.profile,
            consent_status=StudentPassportMembership.ConsentStatus.PRIVATE,
            role="",
        )
        # Direction 2: FK without membership.
        orphan_passport = StudentPassport.objects.create()
        orphan_profile = StudentProfile.objects.create(
            school=self.school,
            first_name="Orphan",
            last_name="Link",
            student_code="DR-003",
            passport=orphan_passport,
        )

        call_command("backfill_passport_links")  # dry-run default
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.passport_id)

        call_command("backfill_passport_links", "--apply")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.passport_id, passport.pk)
        self.assertTrue(
            StudentPassportMembership.objects.filter(
                passport=orphan_passport, student_profile=orphan_profile
            ).exists()
        )


class TransferCaseFSMTests(TestCase):
    def setUp(self):
        self.source = School.objects.create(
            name="FSM Source", slug="fsm-src", subdomain="fsm-src"
        )
        self.target = School.objects.create(
            name="FSM Target", slug="fsm-tgt", subdomain="fsm-tgt"
        )

    def _case(self):
        return TransferCase.objects.create(
            source_school=self.source,
            target_school=self.target,
            source_profile_pk="student-1",
        )

    def test_happy_path_journals_every_transition(self):
        case = self._case()
        chain = [
            TransferCase.Status.CONSENT_PENDING,
            TransferCase.Status.APPROVED,
            TransferCase.Status.EXPORTING,
            TransferCase.Status.ENVELOPE_SEALED,
            TransferCase.Status.APPLYING,
            TransferCase.Status.APPLIED,
            TransferCase.Status.RECONCILED,
        ]
        for status in chain:
            case.advance(status)
        case.refresh_from_db()
        self.assertEqual(case.status, TransferCase.Status.RECONCILED)
        self.assertEqual(len(case.history), len(chain))
        self.assertEqual(case.history[0]["from"], TransferCase.Status.DRAFT)

    def test_illegal_transition_raises(self):
        case = self._case()
        with self.assertRaises(TransferStateError):
            case.advance(TransferCase.Status.APPLIED)
        case.refresh_from_db()
        self.assertEqual(case.status, TransferCase.Status.DRAFT)

    def test_terminal_states_refuse_movement(self):
        case = self._case()
        case.advance(TransferCase.Status.CANCELLED)
        with self.assertRaises(TransferStateError):
            case.advance(TransferCase.Status.CONSENT_PENDING)

    def test_source_must_differ_from_target(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            TransferCase.objects.create(
                source_school=self.source,
                target_school=self.source,
                source_profile_pk="student-1",
            )
