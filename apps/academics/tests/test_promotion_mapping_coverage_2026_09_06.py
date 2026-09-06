"""A rollover must not silently skip a classroom that has nowhere to go.

`ClassroomPromotionMapping` is the only thing that says which classroom in the
target year an advancing student lands in. Before this file:

* `clone_academic_year` created none, so the FIRST thing a school did after
  rolling over was run a promotion that moved nobody;
* `run_auto_promotion` printed "No promotion mappings ..." and returned --
  **exit code 0**, so a scheduler or an operator reading a status saw success;
* a PARTIAL ladder was worse: the mapped classrooms moved, the unmapped ones
  produced one `no_target_classroom` warning per student in a long log, and
  the summary still read like a clean run;
* nothing asked the question before `execute_year_close` locked the source
  year behind the students it could not move.

The four things this file pins, in the order they bite:

  1. a clone CARRIES a ladder forward (author it once, inherit it after)
  2. a clone never INVENTS one (identity mappings are retention mislabelled)
  3. the close scorecard NAMES the classrooms that cannot move
  4. the promotion command REFUSES rather than reporting a no-op as success
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.academics.models import (
    AcademicYear,
    Classroom,
    ClassroomPromotionMapping,
    Department,
    Term,
)
from apps.academics.promotion_mappings import promotion_mapping_coverage
from apps.academics.services_year_setup import clone_academic_year
from apps.academics.year_close import evaluate_year_close_blockers
from apps.people.models import Enrollment, StudentProfile
from apps.schools.models import School


class PromotionMappingCoverageTests(TestCase):
    """One school, three years, a ladder that must survive the rollover."""

    @classmethod
    def setUpTestData(cls):
        cls.uid = uuid.uuid4().hex[:8]
        cls.school = School.objects.create(
            name="Ladder College " + cls.uid,
            slug="ladder-" + cls.uid,
            subdomain="ladder" + cls.uid,
            is_active=True,
        )
        cls.dept = Department.objects.create(
            school=cls.school, name="General " + cls.uid, code="GEN" + cls.uid[:5]
        )
        cls.y1 = cls._year("2025/2026", 2025)
        cls.y2 = cls._year("2026/2027", 2026)

    # -- fixtures --------------------------------------------------------

    @classmethod
    def _year(cls, name, start):
        year = AcademicYear.objects.create(
            school=cls.school,
            name=name,
            start_date=dt.date(start, 9, 1),
            end_date=dt.date(start + 1, 6, 30),
            is_active=False,
        )
        Term.objects.create(
            school=cls.school,
            academic_year=year,
            name="Term 1",
            start_date=dt.date(start, 9, 1),
            end_date=dt.date(start, 12, 10),
        )
        return year

    def _classroom(self, year, name, code):
        return Classroom.objects.create(
            school=self.school,
            academic_year=year,
            department=self.dept,
            name=name,
            code=code + self.uid[:4],
        )

    def _student(self, year, classroom, tag):
        return StudentProfile.objects.create(
            school=self.school,
            first_name="Roll",
            last_name=tag,
            date_of_birth="2010-01-01",
            student_code="STD" + self.uid + tag,
            academic_year=year,
            classroom=classroom,
            is_active=True,
        )

    def _new_year(self, name, start):
        return self._year(name, start)

    # -- 1. the clone carries the ladder forward -------------------------

    def test_clone_carries_last_years_ladder_forward(self):
        form5 = self._classroom(self.y1, "Form 5A", "F5A")
        lower6_y2 = self._classroom(self.y2, "Lower Sixth A", "L6A")
        form5_y2 = self._classroom(self.y2, "Form 5A", "F5A2")
        # The ladder a person authored for last year's rollover.
        ClassroomPromotionMapping.objects.create(
            school=self.school,
            source_year=self.y1,
            source_classroom=form5,
            target_year=self.y2,
            target_classroom=lower6_y2,
        )

        y3 = self._new_year("2027/2028", 2027)
        stats = clone_academic_year(self.y2, y3)

        self.assertEqual(
            stats["promotion_mappings_created"],
            1,
            "the ladder into y2 must be shifted onto the y2 -> y3 rollover",
        )
        carried = ClassroomPromotionMapping.objects.get(
            source_year=self.y2, target_year=y3
        )
        self.assertEqual(
            carried.source_classroom_id,
            form5_y2.pk,
            "the new source is the SAME GRADE one year on, matched by name",
        )
        self.assertEqual(
            carried.target_classroom.name,
            "Lower Sixth A",
            "the new target is the clone of the grade that grade advances into",
        )
        self.assertEqual(carried.target_classroom.academic_year_id, y3.pk)
        self.assertEqual(
            carried.school_id, self.school.pk, "a carried mapping must be owned"
        )

    def test_carrying_forward_is_idempotent(self):
        form5 = self._classroom(self.y1, "Form 5A", "F5A")
        lower6_y2 = self._classroom(self.y2, "Lower Sixth A", "L6A")
        self._classroom(self.y2, "Form 5A", "F5A2")
        ClassroomPromotionMapping.objects.create(
            school=self.school,
            source_year=self.y1,
            source_classroom=form5,
            target_year=self.y2,
            target_classroom=lower6_y2,
        )
        y3 = self._new_year("2027/2028", 2027)
        first = clone_academic_year(self.y2, y3)["promotion_mappings_created"]
        second = clone_academic_year(self.y2, y3)["promotion_mappings_created"]
        self.assertEqual(first, 1)
        self.assertEqual(second, 0, "re-running a rollover must not duplicate a ladder")
        self.assertEqual(
            ClassroomPromotionMapping.objects.filter(
                source_year=self.y2, target_year=y3
            ).count(),
            1,
        )

    # -- 2. and never invents one ----------------------------------------

    def test_a_clone_never_invents_a_ladder(self):
        """The control that makes test 1 mean something.

        A clone reproduces the SAME grades a year later. Minting
        ``Form 5A -> Form 5A`` would place every advancing student back in
        their own grade and report it as a promotion -- worse than no mapping,
        because it looks like it worked.
        """
        self._classroom(self.y2, "Form 5A", "F5A")
        self._classroom(self.y2, "Lower Sixth A", "L6A")
        y3 = self._new_year("2027/2028", 2027)

        stats = clone_academic_year(self.y2, y3)

        self.assertGreater(
            stats["classrooms_created"], 0, "the clone must still copy structure"
        )
        self.assertEqual(
            stats["promotion_mappings_created"],
            0,
            "a school with no authored ladder must get NO mappings, not guesses",
        )
        self.assertFalse(
            ClassroomPromotionMapping.objects.filter(source_year=self.y2).exists()
        )

    # -- 3. coverage names what cannot move ------------------------------

    def test_coverage_counts_only_populated_classrooms(self):
        mapped = self._classroom(self.y1, "Form 5A", "F5A")
        unmapped = self._classroom(self.y1, "Form 4B", "F4B")
        self._classroom(self.y1, "Empty Room", "EMP")  # no students
        target = self._classroom(self.y2, "Lower Sixth A", "L6A")
        self._student(self.y1, mapped, "A")
        self._student(self.y1, unmapped, "B")
        ClassroomPromotionMapping.objects.create(
            school=self.school,
            source_year=self.y1,
            source_classroom=mapped,
            target_year=self.y2,
            target_classroom=target,
        )

        cov = promotion_mapping_coverage(self.y1, self.y2, school=self.school)

        self.assertEqual(cov["total"], 2, "an empty classroom needs no mapping")
        self.assertEqual(cov["mapped"], 1)
        self.assertEqual(cov["unmapped"], 1)
        self.assertEqual(
            [c["name"] for c in cov["unmapped_classrooms"]],
            ["Form 4B"],
            "the operator needs the NAME, not a number they cannot act on",
        )

    def test_coverage_follows_the_enrollment_row_not_the_profile_field(self):
        """`promote_student` reads the enrollment first, so coverage must too.

        A student moved mid-year has a stale ``StudentProfile.classroom``.
        Asking the wrong one reports a classroom the promotion run never
        visits -- a blocker on an empty room, which is how a gate gets
        switched off.
        """
        stale = self._classroom(self.y1, "Form 5A", "F5A")
        actual = self._classroom(self.y1, "Form 5B", "F5B")
        student = self._student(self.y1, stale, "C")
        Enrollment.objects.create(
            school=self.school,
            student=student,
            academic_year=self.y1,
            classroom=actual,
            status=Enrollment.Status.ACTIVE,
            entry_date=dt.date(2025, 9, 1),
        )

        cov = promotion_mapping_coverage(self.y1, self.y2, school=self.school)

        self.assertEqual(
            [c["name"] for c in cov["unmapped_classrooms"]],
            ["Form 5B"],
            "the enrollment row is where the student actually sits",
        )

    def test_coverage_is_empty_when_the_year_has_no_students(self):
        self._classroom(self.y1, "Form 5A", "F5A")
        cov = promotion_mapping_coverage(self.y1, self.y2, school=self.school)
        self.assertEqual(
            cov,
            {"total": 0, "mapped": 0, "unmapped": 0, "unmapped_classrooms": []},
        )

    # -- 4. the close scorecard --------------------------------------

    def test_close_scorecard_blocks_on_an_unmapped_populated_classroom(self):
        room = self._classroom(self.y1, "Form 5A", "F5A")
        self._student(self.y1, room, "D")
        self._classroom(self.y2, "Lower Sixth A", "L6A")  # target IS structured

        card = evaluate_year_close_blockers(self.school, self.y1, self.y2)

        codes = [b["code"] for b in card["blockers"]]
        self.assertIn("promotion_mapping_missing", codes)
        self.assertEqual(card["counts"]["unmapped_classrooms"], 1)
        self.assertEqual(card["counts"]["populated_classrooms"], 1)
        message = next(
            b["message"] for b in card["blockers"] if b["code"] == "promotion_mapping_missing"
        )
        self.assertIn("Form 5A", message, "a blocker must name what to fix")

    def test_close_scorecard_stays_quiet_before_the_target_year_is_structured(self):
        """The question is premature until there are classrooms to map ONTO.

        A rollover clones structure into the target year and only then can a
        ladder exist. Asking earlier would answer "none of them" for every
        school on every close -- a blocker nobody can clear.
        """
        room = self._classroom(self.y1, "Form 5A", "F5A")
        self._student(self.y1, room, "E")
        self.assertFalse(Classroom.objects.filter(academic_year=self.y2).exists())

        card = evaluate_year_close_blockers(self.school, self.y1, self.y2)

        self.assertNotIn(
            "promotion_mapping_missing", [b["code"] for b in card["blockers"]]
        )
        self.assertEqual(card["counts"]["unmapped_classrooms"], 0)

    def test_close_scorecard_clears_once_the_ladder_is_mapped(self):
        room = self._classroom(self.y1, "Form 5A", "F5A")
        self._student(self.y1, room, "F")
        target = self._classroom(self.y2, "Lower Sixth A", "L6A")
        ClassroomPromotionMapping.objects.create(
            school=self.school,
            source_year=self.y1,
            source_classroom=room,
            target_year=self.y2,
            target_classroom=target,
        )

        card = evaluate_year_close_blockers(self.school, self.y1, self.y2)

        self.assertNotIn(
            "promotion_mapping_missing", [b["code"] for b in card["blockers"]]
        )
        self.assertEqual(card["counts"]["mapped_classrooms"], 1)

    # -- 5. the command refuses instead of reporting a no-op -------------

    def test_run_auto_promotion_refuses_when_a_classroom_is_unmapped(self):
        room = self._classroom(self.y1, "Form 5A", "F5A")
        self._student(self.y1, room, "G")
        self._classroom(self.y2, "Lower Sixth A", "L6A")

        err = StringIO()
        with self.assertRaises(CommandError) as caught:
            call_command(
                "run_auto_promotion",
                from_year=self.y1.name,
                to_year=self.y2.name,
                school=str(self.school.pk),
                dry_run=True,
                stdout=StringIO(),
                stderr=err,
            )

        self.assertIn(
            "Form 5A",
            str(caught.exception),
            "the refusal itself must name the classroom -- a scheduler may only "
            "ever see the exception",
        )
        self.assertIn("Form 5A", err.getvalue(), "and the log must list every one")

    def test_run_auto_promotion_refuses_when_there_is_no_ladder_at_all(self):
        """The original defect, verbatim: it used to print a warning and exit 0."""
        with self.assertRaises(CommandError):
            call_command(
                "run_auto_promotion",
                from_year=self.y1.name,
                to_year=self.y2.name,
                school=str(self.school.pk),
                dry_run=True,
                stdout=StringIO(),
                stderr=StringIO(),
            )

    def test_run_auto_promotion_reports_coverage_when_fully_mapped(self):
        room = self._classroom(self.y1, "Form 5A", "F5A")
        self._student(self.y1, room, "H")
        target = self._classroom(self.y2, "Lower Sixth A", "L6A")
        ClassroomPromotionMapping.objects.create(
            school=self.school,
            source_year=self.y1,
            source_classroom=room,
            target_year=self.y2,
            target_classroom=target,
        )
        out = StringIO()

        call_command(
            "run_auto_promotion",
            from_year=self.y1.name,
            to_year=self.y2.name,
            school=str(self.school.pk),
            dry_run=True,
            stdout=out,
            stderr=StringIO(),
        )

        self.assertIn("1/1", out.getvalue())
