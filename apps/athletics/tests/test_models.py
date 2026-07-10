"""Model-integrity tests — partial-unique constraints + catalog uniqueness.

The partial-unique constraints are the roster's integrity spine: they must
REJECT a second ACTIVE row while ALLOWING an inactive (LEFT) duplicate — the
whole point of the ``condition=`` predicate. Each IntegrityError is asserted
inside its own ``transaction.atomic()`` so the enclosing test transaction is
not poisoned.
"""

from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction

from apps.athletics.models import (
    CoachAssignment,
    MedicalClearance,
    Season,
    Sport,
    Team,
    TeamMembership,
)
from apps.athletics.models.roster import _clearance_upload_path
from apps.athletics.tests.base import BaseAthleticsTestCase
from apps.people.models import StudentProfile


class TeamMembershipConstraintTests(BaseAthleticsTestCase):
    def _student(self, tag):
        return StudentProfile.objects.create(
            school=self.fx.school,
            first_name="S",
            last_name=tag,
            admission_number=f"ADM-a-{tag}",
            academic_year=self.fx.year,
            classroom=self.fx.classroom,
            specialty=self.fx.specialty,
        )

    def test_one_active_membership_per_team_student(self):
        self.add_member(self.fx, status=TeamMembership.Status.ACTIVE)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.add_member(self.fx, status=TeamMembership.Status.ACTIVE)

    def test_second_left_membership_is_allowed(self):
        # Partial constraint: a LEFT row for the same (team, student) is fine.
        self.add_member(self.fx, status=TeamMembership.Status.LEFT)
        second = self.add_member(self.fx, status=TeamMembership.Status.LEFT)
        self.assertIsNotNone(second.pk)
        # And an ACTIVE one can then coexist with the two LEFT rows.
        active = self.add_member(self.fx, status=TeamMembership.Status.ACTIVE)
        self.assertIsNotNone(active.pk)

    def test_injured_and_suspended_also_count_as_active_slot(self):
        self.add_member(self.fx, status=TeamMembership.Status.INJURED)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.add_member(self.fx, status=TeamMembership.Status.SUSPENDED)

    def test_one_active_jersey_per_team(self):
        s1 = self._student("j1")
        s2 = self._student("j2")
        self.add_member(
            self.fx, student=s1, status=TeamMembership.Status.ACTIVE, jersey_number=9
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.add_member(
                self.fx, student=s2, status=TeamMembership.Status.ACTIVE, jersey_number=9
            )

    def test_left_jersey_duplicate_allowed(self):
        s1 = self._student("k1")
        s2 = self._student("k2")
        self.add_member(
            self.fx, student=s1, status=TeamMembership.Status.ACTIVE, jersey_number=7
        )
        # A LEFT member reusing #7 is allowed (jersey constraint is status=active only).
        left = self.add_member(
            self.fx, student=s2, status=TeamMembership.Status.LEFT, jersey_number=7
        )
        self.assertIsNotNone(left.pk)

    def test_null_jersey_never_conflicts(self):
        s1 = self._student("n1")
        s2 = self._student("n2")
        self.add_member(
            self.fx, student=s1, status=TeamMembership.Status.ACTIVE, jersey_number=None
        )
        m2 = self.add_member(
            self.fx, student=s2, status=TeamMembership.Status.ACTIVE, jersey_number=None
        )
        self.assertIsNotNone(m2.pk)


class CoachAssignmentConstraintTests(BaseAthleticsTestCase):
    def test_one_active_coach_per_team(self):
        CoachAssignment.objects.create(
            school=self.fx.school, team=self.fx.team, coach=self.fx.teacher_user,
            is_active=True,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            CoachAssignment.objects.create(
                school=self.fx.school, team=self.fx.team, coach=self.fx.teacher_user,
                is_active=True,
            )

    def test_inactive_coach_duplicate_allowed(self):
        CoachAssignment.objects.create(
            school=self.fx.school, team=self.fx.team, coach=self.fx.teacher_user,
            is_active=False,
        )
        second = CoachAssignment.objects.create(
            school=self.fx.school, team=self.fx.team, coach=self.fx.teacher_user,
            is_active=False,
        )
        self.assertIsNotNone(second.pk)


class CatalogUniquenessTests(BaseAthleticsTestCase):
    def test_sport_unique_school_code(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sport.objects.create(
                school=self.fx.school, name="Football duplicate", code=self.fx.sport.code
            )

    def test_season_unique_school_sport_year_name(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Season.objects.create(
                school=self.fx.school,
                sport=self.fx.sport,
                academic_year=self.fx.year,
                name=self.fx.season.name,
                start_date=date(2025, 9, 1),
                end_date=date(2026, 1, 31),
            )

    def test_team_unique_season_name(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Team.objects.create(
                school=self.fx.school,
                sport=self.fx.sport,
                season=self.fx.season,
                name=self.fx.team.name,
            )


class MedicalClearanceUploadPathTests(BaseAthleticsTestCase):
    """Medical clearance (special-category child health data) upload paths must
    be unguessable — a random per-file uuid segment so school_id + a common
    filename cannot be enumerated."""

    def test_same_filename_yields_distinct_unguessable_paths(self):
        clearance = self.make_clearance(self.fx)
        p1 = _clearance_upload_path(clearance, "scan.pdf")
        p2 = _clearance_upload_path(clearance, "scan.pdf")
        self.assertNotEqual(p1, p2)
        prefix = f"athletics/medical/{self.fx.school.pk}/"
        self.assertTrue(p1.startswith(prefix))
        self.assertTrue(p2.startswith(prefix))
        # A uuid segment sits between the school dir and the filename.
        self.assertRegex(p1, rf"^{prefix}[0-9a-f]{{32}}/scan\.pdf$")


class MedicalClearanceDocumentValidatorTests(BaseAthleticsTestCase):
    """The document FileField enforces a 5MB size cap + an allow-list of types."""

    def _run_document_validators(self, uploaded):
        field = MedicalClearance._meta.get_field("document")
        for validator in field.validators:
            validator(uploaded)

    def test_oversized_file_rejected(self):
        big = SimpleUploadedFile(
            "big.pdf", b"x" * (6 * 1024 * 1024), content_type="application/pdf"
        )
        with self.assertRaises(ValidationError):
            self._run_document_validators(big)

    def test_disallowed_type_rejected(self):
        evil = SimpleUploadedFile(
            "evil.html", b"<html>hi</html>", content_type="text/html"
        )
        with self.assertRaises(ValidationError):
            self._run_document_validators(evil)

    def test_small_pdf_accepted(self):
        ok = SimpleUploadedFile(
            "clearance.pdf", b"%PDF-1.4 tiny", content_type="application/pdf"
        )
        # Must not raise.
        self._run_document_validators(ok)
