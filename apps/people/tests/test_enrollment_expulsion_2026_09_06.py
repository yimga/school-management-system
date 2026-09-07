"""Expulsion is its own outcome, not a label on "withdrawn".

`Enrollment.Outcome` could say a student left -- GRADUATED, TRANSFERRED_OUT,
WITHDRAWN -- but not that the school made them leave. The nearest fit was
WITHDRAWN, which is the family's decision, and the two behave differently
everywhere it matters: re-admission, a transfer certificate, a ministry return,
and what a school must be able to show years later if the decision is
challenged. A school that expelled a student and a school a family walked away
from produced byte-identical records.

Two things this file pins:

  * EXPELLED is inside EXIT_OUTCOMES (the student has left) and ALSO inside the
    narrower INVOLUNTARY_EXIT_OUTCOMES, so "did they leave" and "were they made
    to leave" are separately answerable. If the second set ever collapses into
    the first, the distinction is gone and these tests say so.
  * An expulsion cannot be recorded without its ground. Every other outcome is
    derivable from marks or is the family's own decision; this one is neither,
    and the moment it is written is the only moment anyone still knows why.
"""

from __future__ import annotations

import datetime as dt
import uuid

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.academics.models import AcademicYear, Classroom, Department
from apps.people.models import Enrollment, StudentProfile
from apps.schools.models import School


class EnrollmentExpulsionOutcomeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        uid = uuid.uuid4().hex[:8]
        cls.uid = uid
        cls.school = School.objects.create(
            name="Discipline College " + uid,
            slug="disc-" + uid,
            subdomain="disc" + uid,
            is_active=True,
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="2026/2027",
            start_date=dt.date(2026, 9, 1),
            end_date=dt.date(2027, 6, 30),
        )
        dept = Department.objects.create(
            school=cls.school, name="General " + uid, code="GEN" + uid[:5]
        )
        cls.classroom = Classroom.objects.create(
            school=cls.school,
            academic_year=cls.year,
            department=dept,
            name="Form 4A",
            code="F4A" + uid[:5],
        )

    def _enroll(self, tag):
        student = StudentProfile.objects.create(
            school=self.school,
            first_name="Case",
            last_name=tag,
            date_of_birth="2010-03-03",
            student_code="STD" + self.uid + tag,
            academic_year=self.year,
            classroom=self.classroom,
            is_active=True,
        )
        return Enrollment.objects.create(
            school=self.school,
            student=student,
            academic_year=self.year,
            classroom=self.classroom,
            status=Enrollment.Status.ACTIVE,
            entry_date=dt.date(2026, 9, 1),
        )

    # -- the outcome exists and behaves --------------------------------

    def test_an_expulsion_can_be_recorded_and_survives_a_round_trip(self):
        enrollment = self._enroll("A")

        enrollment.close(
            Enrollment.Outcome.EXPELLED,
            reason="Repeated assault after a final written warning.",
        )

        stored = Enrollment.objects.get(pk=enrollment.pk)
        self.assertEqual(stored.outcome, Enrollment.Outcome.EXPELLED)
        self.assertEqual(
            stored.status,
            Enrollment.Status.WITHDRAWN,
            "a year that ended early leaves the ROW withdrawn, not completed",
        )
        self.assertIsNotNone(stored.exit_date, "an exit must be dated")
        self.assertIsNotNone(
            stored.outcome_recorded_at, "and stamped with when it was decided"
        )
        self.assertIn("final written warning", stored.outcome_reason)

    def test_the_enrollment_is_never_deleted(self):
        """The record is the point. An expulsion that erases history is useless."""
        enrollment = self._enroll("B")
        student_id = enrollment.student_id

        enrollment.close(Enrollment.Outcome.EXPELLED, reason="Ground on record.")

        self.assertTrue(
            Enrollment.objects.filter(student_id=student_id).exists(),
            "the closed row must remain queryable forever",
        )

    # -- the distinction, which is the reason it is a separate outcome --

    def test_expelled_is_an_exit_but_a_different_kind_of_exit(self):
        self.assertIn(Enrollment.Outcome.EXPELLED, Enrollment.EXIT_OUTCOMES)
        self.assertIn(
            Enrollment.Outcome.EXPELLED, Enrollment.INVOLUNTARY_EXIT_OUTCOMES
        )
        self.assertNotIn(
            Enrollment.Outcome.WITHDRAWN,
            Enrollment.INVOLUNTARY_EXIT_OUTCOMES,
            "a family choosing to leave is not the school dismissing a student",
        )
        self.assertNotIn(
            Enrollment.Outcome.TRANSFERRED_OUT,
            Enrollment.INVOLUNTARY_EXIT_OUTCOMES,
        )
        self.assertNotIn(
            Enrollment.Outcome.GRADUATED, Enrollment.INVOLUNTARY_EXIT_OUTCOMES
        )
        self.assertTrue(
            Enrollment.INVOLUNTARY_EXIT_OUTCOMES < Enrollment.EXIT_OUTCOMES,
            "the involuntary set must stay a STRICT subset -- if it ever equals "
            "EXIT_OUTCOMES the distinction has been lost",
        )

    def test_a_school_can_ask_who_was_made_to_leave_separately(self):
        expelled = self._enroll("C")
        withdrawn = self._enroll("D")
        expelled.close(Enrollment.Outcome.EXPELLED, reason="Ground on record.")
        withdrawn.close(Enrollment.Outcome.WITHDRAWN, reason="Family relocated.")

        left = set(
            Enrollment.objects.filter(
                academic_year=self.year,
                outcome__in=Enrollment.EXIT_OUTCOMES,
            ).values_list("pk", flat=True)
        )
        made_to_leave = set(
            Enrollment.objects.filter(
                academic_year=self.year,
                outcome__in=Enrollment.INVOLUNTARY_EXIT_OUTCOMES,
            ).values_list("pk", flat=True)
        )

        self.assertEqual(left, {expelled.pk, withdrawn.pk})
        self.assertEqual(
            made_to_leave,
            {expelled.pk},
            "the query that could not be written before this outcome existed",
        )

    # -- what the archival record must retain ---------------------------

    def test_an_expulsion_without_a_ground_is_refused(self):
        enrollment = self._enroll("E")

        with self.assertRaises(ValidationError) as caught:
            enrollment.close(Enrollment.Outcome.EXPELLED)

        self.assertIn("outcome_reason", caught.exception.message_dict)
        enrollment.refresh_from_db()
        self.assertEqual(
            enrollment.outcome, "", "a refused close must not half-write the row"
        )
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)

    def test_a_ground_already_on_the_row_satisfies_the_rule(self):
        enrollment = self._enroll("F")
        enrollment.outcome_reason = "Recorded at the hearing on 2026-11-04."
        enrollment.save()

        enrollment.close(Enrollment.Outcome.EXPELLED)

        self.assertEqual(enrollment.outcome, Enrollment.Outcome.EXPELLED)
        self.assertIn("hearing", enrollment.outcome_reason)

    def test_the_rule_applies_to_expulsion_only(self):
        """The control. A reason requirement on every outcome would be noise."""
        enrollment = self._enroll("G")

        enrollment.close(Enrollment.Outcome.WITHDRAWN)

        self.assertEqual(enrollment.outcome, Enrollment.Outcome.WITHDRAWN)
        self.assertEqual(enrollment.outcome_reason, "")

    def test_an_unknown_outcome_is_still_refused(self):
        enrollment = self._enroll("H")
        with self.assertRaises(ValidationError):
            enrollment.close("DISMISSED")
