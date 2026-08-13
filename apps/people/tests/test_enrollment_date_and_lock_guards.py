"""Enrollment integrity guards (M29 / EOY hardening).

Two MUST-FIRE guards on the enrollment lifecycle:

* **Fix 3 — date integrity.** ``Enrollment.clean()`` rejects ``entry_date >
  exit_date``; before it existed a transposed pair saved silently and every
  downstream date-arithmetic read a negative-length placement as garbage.
* **Fix 4 — year-lock write guard.** ``open_enrollment`` refuses to open a
  placement into an ``AcademicYear`` whose ``is_locked`` is set. Run-observed
  gap: an enrollment could be written into a year already locked by a prior
  rollover with nothing objecting.

Each test fails on the pre-fix code (no ``clean()``, no guard) and passes after.
The fixture is shared with ``test_enrollment.py`` so the whole two-year school is
built the same way as the existing suite.
"""

from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.people.enrollment_services import assert_year_writable, open_enrollment
from apps.people.models import Enrollment
from apps.people.tests.test_enrollment import EnrollmentFixtureMixin


class EnrollmentDateIntegrityTests(EnrollmentFixtureMixin, TestCase):
    """Fix 3 — an enrollment cannot end before it began."""

    def setUp(self):
        self.build_school("dateguard")
        self.student = self.make_student("DATE-1")

    def test_entry_after_exit_raises_validation_error(self):
        # MUST-FIRE: pre-fix Enrollment had no clean(), so full_clean() accepted
        # a transposed window and the row saved silently.
        enrollment = Enrollment(
            school=self.school,
            student=self.student,
            academic_year=self.year_1,
            classroom=self.grade5_y1,
            entry_date=date(2026, 7, 1),
            exit_date=date(2025, 9, 1),
        )
        with self.assertRaises(ValidationError) as ctx:
            enrollment.full_clean()
        # The error is attached to exit_date, not some unrelated field.
        self.assertIn("exit_date", ctx.exception.message_dict)

    def test_entry_before_exit_is_accepted(self):
        enrollment = Enrollment(
            school=self.school,
            student=self.student,
            academic_year=self.year_1,
            classroom=self.grade5_y1,
            entry_date=date(2025, 9, 1),
            exit_date=date(2026, 7, 1),
        )
        # Must not raise. (Uniqueness/constraint checks are the DB's job; the
        # create entrypoints call full_clean the same way.)
        enrollment.full_clean(validate_unique=False, validate_constraints=False)

    def test_equal_entry_and_exit_is_accepted(self):
        enrollment = Enrollment(
            school=self.school,
            student=self.student,
            academic_year=self.year_1,
            classroom=self.grade5_y1,
            entry_date=date(2025, 9, 1),
            exit_date=date(2025, 9, 1),
        )
        enrollment.full_clean(validate_unique=False, validate_constraints=False)

    def test_open_enrollment_still_produces_a_valid_active_row(self):
        # open_enrollment now runs full_clean before insert; a normal open must
        # still succeed and yield an ACTIVE enrollment.
        enrollment = open_enrollment(self.student, self.year_1, self.grade5_y1)
        self.assertTrue(enrollment.pk)
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)
        self.assertIsNone(enrollment.exit_date)


class OpenEnrollmentYearLockGuardTests(EnrollmentFixtureMixin, TestCase):
    """Fix 4 — opening a placement in a LOCKED year is refused."""

    def setUp(self):
        self.build_school("lockguard")
        self.student = self.make_student("LOCK-1")

    def test_open_into_locked_year_raises(self):
        # MUST-FIRE: pre-fix there was no guard, so this wrote an enrollment into
        # a locked year.
        self.year_2.is_locked = True
        self.year_2.save(update_fields=["is_locked"])
        with self.assertRaises(ValidationError):
            open_enrollment(self.student, self.year_2, self.grade6_y2)
        # Nothing was written.
        self.assertEqual(
            self.student.enrollments.filter(academic_year=self.year_2).count(), 0
        )

    def test_open_into_unlocked_year_succeeds(self):
        # Control: the identical call succeeds when the target year is writable.
        self.assertFalse(self.year_2.is_locked)
        enrollment = open_enrollment(self.student, self.year_2, self.grade6_y2)
        self.assertTrue(enrollment.pk)
        self.assertEqual(enrollment.academic_year_id, self.year_2.pk)

    def test_assert_year_writable_helper_contract(self):
        self.year_1.is_locked = True
        with self.assertRaises(ValidationError):
            assert_year_writable(self.year_1)
        self.year_1.is_locked = False
        assert_year_writable(self.year_1)  # writable -> no raise
        assert_year_writable(None)  # None is a no-op, never raises
