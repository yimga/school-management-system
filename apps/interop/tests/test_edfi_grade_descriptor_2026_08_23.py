"""Ed-Fi entryGradeLevelDescriptor must not substring-match the grade number.

``_section_to_grade_descriptor`` walked the key list ``["1","2",...,"12"]`` in
order and returned on ``if key in s or s == key``. ``"1"`` is a substring of
"10", "11" and "12", so every double-digit grade short-circuited to *First
grade*: a US state-reporting interchange declared the entire high school as
first-graders. Non-numeric section labels ("Form 5", "JSS 3") were mismapped the
same way, by whichever digit they happened to contain.

The grade number is now extracted with a boundary-anchored regex over 1..12 and
looked up, so "10"/"11"/"12" map to Tenth/Eleventh/Twelfth and a label carrying
no grade number stays *Ungraded* rather than borrowing a stray digit.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.interop.edfi.adapter import (
    _section_to_grade_descriptor,
    student_school_association_to_edfi,
)

PREFIX = "uri://ed-fi.org/GradeLevelDescriptor#"


class _Student:
    pk = 7
    student_code = "S-7"
    admission_number = "ADM-7"
    joined_date = "2025-09-01"

    def __init__(self, section):
        self.section = section


class _School:
    pk = 3


class GradeDescriptorTests(SimpleTestCase):
    def test_double_digit_grades_are_not_swallowed_by_the_one_prefix(self):
        for section, expected in (
            ("10", "Tenth grade"),
            ("11", "Eleventh grade"),
            ("12", "Twelfth grade"),
            ("Grade 12", "Twelfth grade"),
            ("Year 10", "Tenth grade"),
        ):
            with self.subTest(section=section):
                self.assertEqual(
                    _section_to_grade_descriptor(section), PREFIX + expected
                )

    def test_single_digit_grades_still_map(self):
        # Guards the fix from over-correcting: the cases that already worked
        # must keep working, so a green run above is not a green run on nothing.
        for section, expected in (
            ("1", "First grade"),
            ("9", "Ninth grade"),
            ("2A", "Second grade"),
            ("Grade 4", "Fourth grade"),
        ):
            with self.subTest(section=section):
                self.assertEqual(
                    _section_to_grade_descriptor(section), PREFIX + expected
                )

    def test_no_grade_number_is_ungraded(self):
        for section in ("", "Ungraded", "Blue House", "Kindergarten"):
            with self.subTest(section=section):
                self.assertEqual(
                    _section_to_grade_descriptor(section), PREFIX + "Ungraded"
                )

    def test_interchange_row_carries_the_right_grade(self):
        row = student_school_association_to_edfi(_Student("12"), _School())
        # Vacuity guard: the row really is the association payload we think it
        # is, so the descriptor assertion below is reading the real field.
        self.assertEqual(row["studentReference"]["studentUniqueId"], "S-7")
        self.assertEqual(
            row["entryGradeLevelDescriptor"], PREFIX + "Twelfth grade"
        )
