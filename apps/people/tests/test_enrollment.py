"""Enrollment as a first-class entity — program item 2.2.

Every test here is MUST-FIRE: each one asserts a behaviour that literally could
not be expressed before ``people.Enrollment`` existed, so reverting the change
turns them red rather than leaving them vacuously green.

The three defects under test:

1. promotion overwrote ``StudentProfile.classroom``/``.academic_year``, so last
   year's placement was destroyed — no academic history;
2. *repeating a year* was inexpressible: one field cannot hold "Grade 5 in 2025"
   and "Grade 5 again in 2026" at the same time;
3. the promotion job never consulted ``PromotionRule``, so a failing student
   advanced exactly like a passing one.
"""

from datetime import date
from importlib import import_module

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.academics.models import (
    AcademicYear,
    Classroom,
    ClassroomPromotionMapping,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.accounts.models import User
from apps.evals.models import Evaluation
from apps.people.enrollment_services import (
    NO_DATA_RETAIN,
    ensure_enrollment,
    outcome_for_manual_placement,
    promote_cohort,
    resolve_promotion_decision,
    set_placement,
)
from apps.people.models import Enrollment, StudentProfile, TeacherProfile
from apps.reports.models import PromotionRule
from apps.schools.models import School


class EnrollmentFixtureMixin:
    """A two-year school with a pass mark, a passer and a failer."""

    slug = "enrollment-2-2"

    def build_school(self, suffix=""):
        suffix = suffix or self.slug
        self.school = School.objects.create(
            slug=f"school-{suffix}", name=f"Enrollment School {suffix}"
        )
        self.year_1 = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
            is_active=True,
        )
        self.year_2 = AcademicYear.objects.create(
            school=self.school,
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 1),
            is_active=False,
        )
        self.term_1 = Term.objects.create(
            school=self.school,
            academic_year=self.year_1,
            name="FIRST",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 5),
            position=1,
            is_active=True,
        )
        self.department = Department.objects.create(
            school=self.school, name="Science", code=f"SCI-{suffix}"
        )
        self.specialty = Specialty.objects.create(
            school=self.school,
            department=self.department,
            name="General",
            code=f"GEN-{suffix}",
        )
        # Grade 5 and Grade 6 exist in BOTH years. That is what makes a repeat
        # expressible: the same grade, a different year.
        self.grade5_y1 = Classroom.objects.create(
            school=self.school,
            academic_year=self.year_1,
            department=self.department,
            name="Grade 5",
            code=f"G5Y1-{suffix}",
        )
        self.grade6_y1 = Classroom.objects.create(
            school=self.school,
            academic_year=self.year_1,
            department=self.department,
            name="Grade 6",
            code=f"G6Y1-{suffix}",
        )
        self.grade5_y2 = Classroom.objects.create(
            school=self.school,
            academic_year=self.year_2,
            department=self.department,
            name="Grade 5",
            code=f"G5Y2-{suffix}",
        )
        self.grade6_y2 = Classroom.objects.create(
            school=self.school,
            academic_year=self.year_2,
            department=self.department,
            name="Grade 6",
            code=f"G6Y2-{suffix}",
        )
        ClassroomPromotionMapping.objects.create(
            school=self.school,
            source_year=self.year_1,
            source_classroom=self.grade5_y1,
            target_year=self.year_2,
            target_classroom=self.grade6_y2,
        )
        self.subject = Subject.objects.create(
            school=self.school, name=f"Mathematics {suffix}"
        )
        self.assignment = SubjectAssignment.objects.create(
            academic_year=self.year_1,
            term=self.term_1,
            classroom=self.grade5_y1,
            specialty=self.specialty,
            subject=self.subject,
            coefficient=1,
        )
        teacher_user = User.objects.create_user(
            username=f"teacher-{suffix}", password="pass12345", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(
            user=teacher_user, school=self.school
        )

    def make_student(self, code, classroom=None, **kwargs):
        student = StudentProfile.objects.create(
            school=self.school,
            first_name=code,
            last_name="Test",
            student_code=code,
            academic_year=kwargs.pop("academic_year", self.year_1),
            classroom=classroom or self.grade5_y1,
            specialty=self.specialty,
            is_active=kwargs.pop("is_active", True),
            **kwargs,
        )
        return student

    def score(self, student, seq1, seq2, exam):
        return Evaluation.objects.create(
            school=self.school,
            academic_year=self.year_1,
            term=self.term_1,
            subject_assignment=self.assignment,
            student=student,
            teacher=self.teacher,
            seq1_score=seq1,
            seq2_score=seq2,
            exam_score=exam,
        )


class PromotionPreservesHistoryTests(EnrollmentFixtureMixin, TestCase):
    """Acceptance 1 — promoting a cohort must not destroy the prior year."""

    def setUp(self):
        self.build_school("hist")
        PromotionRule.objects.create(
            academic_year=self.year_1,
            classroom=None,
            promotion_average=10,
            demotion_average=0,
        )
        self.passer = self.make_student("PASS-HIST")
        self.score(self.passer, 16, 15, 17)
        ensure_enrollment(self.passer)

    def test_prior_year_enrollment_still_resolves_after_promotion(self):
        result = promote_cohort(self.year_1, self.year_2)
        self.assertEqual(result.promoted, 1, result.as_dict())

        # THE POINT: last year is still there. Before Enrollment existed this
        # row was simply overwritten and the 2025/2026 placement was gone.
        prior = self.passer.enrollment_for_year(self.year_1)
        self.assertIsNotNone(prior)
        self.assertEqual(prior.classroom_id, self.grade5_y1.pk)
        self.assertEqual(prior.outcome, Enrollment.Outcome.PROMOTED)
        self.assertFalse(prior.is_active)
        self.assertIsNotNone(prior.exit_date)

        current = self.passer.enrollment_for_year(self.year_2)
        self.assertIsNotNone(current)
        self.assertEqual(current.classroom_id, self.grade6_y2.pk)
        self.assertTrue(current.is_active)
        self.assertEqual(current.previous_enrollment_id, prior.pk)

        history = list(self.passer.enrollment_history())
        self.assertEqual(
            [e.academic_year_id for e in history], [self.year_1.pk, self.year_2.pk]
        )

    def test_legacy_student_row_still_tracks_the_current_placement(self):
        """Backward compatibility: ~180 readers still use student.classroom."""
        promote_cohort(self.year_1, self.year_2)
        self.passer.refresh_from_db()
        self.assertEqual(self.passer.classroom_id, self.grade6_y2.pk)
        self.assertEqual(self.passer.academic_year_id, self.year_2.pk)
        # ...and the derivation agrees with the projection.
        self.assertEqual(self.passer.current_classroom.pk, self.grade6_y2.pk)
        self.assertEqual(self.passer.current_academic_year.pk, self.year_2.pk)


class RetentionTests(EnrollmentFixtureMixin, TestCase):
    """Acceptance 2 — a student meeting a retention rule STAYS IN GRADE."""

    def setUp(self):
        self.build_school("retain")
        PromotionRule.objects.create(
            academic_year=self.year_1,
            classroom=None,
            promotion_average=10,
            demotion_average=0,
        )
        self.passer = self.make_student("PASS-RET")
        self.failer = self.make_student("FAIL-RET")
        self.score(self.passer, 16, 15, 17)
        self.score(self.failer, 4, 5, 6)
        ensure_enrollment(self.passer)
        ensure_enrollment(self.failer)

    def test_failing_student_is_retained_and_passing_student_is_not(self):
        result = promote_cohort(self.year_1, self.year_2)
        self.assertEqual(result.promoted, 1, result.as_dict())
        self.assertEqual(result.retained, 1, result.as_dict())

        self.failer.refresh_from_db()
        self.passer.refresh_from_db()

        # The failing student stays in Grade 5. Before this change the promotion
        # job never read PromotionRule, so this student advanced to Grade 6
        # exactly like the passing one.
        self.assertEqual(self.failer.current_classroom.name, "Grade 5")
        self.assertEqual(self.passer.current_classroom.name, "Grade 6")

        prior = self.failer.enrollment_for_year(self.year_1)
        self.assertEqual(prior.outcome, Enrollment.Outcome.RETAINED)
        self.assertIsNotNone(prior.decision_average)

    def test_retained_student_holds_two_enrollments_for_the_same_grade(self):
        promote_cohort(self.year_1, self.year_2)

        same_grade = self.failer.enrollments.filter(
            classroom__name="Grade 5"
        ).order_by("academic_year__start_date")
        self.assertEqual(same_grade.count(), 2)
        self.assertEqual(
            [e.academic_year_id for e in same_grade],
            [self.year_1.pk, self.year_2.pk],
        )
        # Same grade, two DIFFERENT years — the repeating case that a single
        # field on the student row cannot represent at all.
        self.assertNotEqual(same_grade[0].classroom_id, same_grade[1].classroom_id)
        self.assertEqual(same_grade[0].classroom.name, same_grade[1].classroom.name)

    def test_conditional_promotion_band_advances_the_student(self):
        rule = PromotionRule.objects.get(academic_year=self.year_1, classroom=None)
        rule.conditional_promotion_average = 4
        rule.save(update_fields=["conditional_promotion_average"])

        decision = resolve_promotion_decision(self.failer, self.year_1)
        self.assertEqual(
            decision.outcome, Enrollment.Outcome.CONDITIONALLY_PROMOTED
        )
        self.assertTrue(decision.advances)

        result = promote_cohort(self.year_1, self.year_2)
        self.assertEqual(result.conditionally_promoted, 1, result.as_dict())
        self.failer.refresh_from_db()
        self.assertEqual(self.failer.current_classroom.name, "Grade 6")
        self.assertEqual(
            self.failer.enrollment_for_year(self.year_1).outcome,
            Enrollment.Outcome.CONDITIONALLY_PROMOTED,
        )

    def test_no_rule_and_no_marks_follows_the_configured_policy(self):
        """The 'undecided' path is a policy, not a silent promotion."""
        PromotionRule.objects.filter(academic_year=self.year_1).delete()
        decision = resolve_promotion_decision(
            self.passer, self.year_1, no_data_policy=NO_DATA_RETAIN
        )
        self.assertEqual(decision.outcome, Enrollment.Outcome.RETAINED)
        self.assertTrue(decision.undecided)

        # Default policy is 'promote' so an unconfigured tenant is unchanged.
        default = resolve_promotion_decision(self.passer, self.year_1)
        self.assertEqual(default.outcome, Enrollment.Outcome.PROMOTED)
        self.assertTrue(default.undecided)


class RepeatingAYearTests(EnrollmentFixtureMixin, TestCase):
    """Acceptance 3 — the model itself must permit same grade, different years."""

    def setUp(self):
        self.build_school("repeat")
        self.student = self.make_student("REPEAT-1")

    def test_same_grade_in_two_different_years_is_representable(self):
        first = Enrollment.objects.create(
            school=self.school,
            student=self.student,
            academic_year=self.year_1,
            classroom=self.grade5_y1,
            entry_date=self.year_1.start_date,
        )
        first.close(Enrollment.Outcome.RETAINED, exit_date=self.year_1.end_date)
        second = Enrollment.objects.create(
            school=self.school,
            student=self.student,
            academic_year=self.year_2,
            classroom=self.grade5_y2,
            entry_date=self.year_2.start_date,
            previous_enrollment=first,
        )

        grades = [e.classroom.name for e in self.student.enrollment_history()]
        self.assertEqual(grades, ["Grade 5", "Grade 5"])
        years = [e.academic_year_id for e in self.student.enrollment_history()]
        self.assertEqual(years, [self.year_1.pk, self.year_2.pk])
        self.assertEqual(self.student.current_enrollment.pk, second.pk)

    def test_only_one_enrollment_may_be_open_at_a_time(self):
        """The constraint is what makes 'current class' a derivation, not a guess."""
        Enrollment.objects.create(
            school=self.school,
            student=self.student,
            academic_year=self.year_1,
            classroom=self.grade5_y1,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Enrollment.objects.create(
                    school=self.school,
                    student=self.student,
                    academic_year=self.year_2,
                    classroom=self.grade5_y2,
                )


class PlacementSyncTests(EnrollmentFixtureMixin, TestCase):
    """The writers that still touch the legacy fields must not drift from it.

    Without ``set_placement`` a mid-year class move via OneRoster or the admin
    bulk-assign action would leave the student row saying one class and the
    enrollment — the source of truth — saying another.
    """

    def setUp(self):
        self.build_school("placement")
        self.student = self.make_student("MOVE-1")
        ensure_enrollment(self.student)

    def test_same_year_class_move_amends_the_open_enrollment(self):
        self.student.classroom = self.grade6_y1
        self.student.save(update_fields=["classroom"])
        set_placement(self.student)

        # One enrollment, amended — a mid-year move is not a new academic year
        # and must not manufacture a second history row.
        self.assertEqual(self.student.enrollments.count(), 1)
        self.assertEqual(
            self.student.current_enrollment.classroom_id, self.grade6_y1.pk
        )

    def test_year_change_opens_a_new_enrollment_and_closes_the_old_one(self):
        set_placement(
            self.student, classroom=self.grade6_y2, academic_year=self.year_2
        )
        self.assertEqual(self.student.enrollments.count(), 2)
        self.assertEqual(
            self.student.enrollment_for_year(self.year_1).status,
            Enrollment.Status.COMPLETED,
        )
        self.assertEqual(
            self.student.current_enrollment.academic_year_id, self.year_2.pk
        )

    def test_manual_placement_outcome_reflects_what_the_operator_chose(self):
        # Same grade next year is a repeat, however the operator got there.
        self.assertEqual(
            outcome_for_manual_placement(self.grade5_y1, self.grade5_y2),
            Enrollment.Outcome.RETAINED,
        )
        # Moved up despite a failing verdict = a conditional promotion, which is
        # a materially different fact from an ordinary promotion.
        self.assertEqual(
            outcome_for_manual_placement(self.grade5_y1, self.grade6_y2, "REPEAT"),
            Enrollment.Outcome.CONDITIONALLY_PROMOTED,
        )
        self.assertEqual(
            outcome_for_manual_placement(self.grade5_y1, self.grade6_y2, "PROMOTED"),
            Enrollment.Outcome.PROMOTED,
        )


class BackfillMigrationTests(EnrollmentFixtureMixin, TestCase):
    """Acceptance 4 — the backfill must not re-class anybody.

    Runs the migration's own ``backfill`` callable against the live app
    registry, so the assertion is about the shipped code path rather than a
    re-implementation of it.
    """

    def setUp(self):
        self.build_school("backfill")
        self.active_a = self.make_student("BF-A")
        self.active_b = self.make_student("BF-B", classroom=self.grade6_y1)
        self.alumnus = self.make_student(
            "BF-C", is_active=False, status=StudentProfile.Status.ALUMNI
        )
        self.no_year = StudentProfile.objects.create(
            school=self.school,
            first_name="NoYear",
            last_name="Test",
            student_code="BF-D",
            is_active=True,
        )
        self.before = {
            s.pk: (s.classroom_id, s.academic_year_id)
            for s in StudentProfile.objects.all()
        }

    @staticmethod
    def run_backfill():
        module = import_module(
            "apps.people.migrations.0071_backfill_enrollment_from_student_row"
        )
        module.backfill(django_apps, None)

    def test_backfill_creates_one_active_enrollment_and_changes_no_class(self):
        self.assertEqual(Enrollment.objects.count(), 0)
        self.run_backfill()

        for student in (self.active_a, self.active_b):
            enrollments = student.enrollments.all()
            self.assertEqual(enrollments.count(), 1, student.student_code)
            enrollment = enrollments.first()
            self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)
            self.assertEqual(enrollment.classroom_id, student.classroom_id)
            self.assertEqual(enrollment.academic_year_id, student.academic_year_id)

        # An alumnus gets HISTORY, not a live placement — an ACTIVE row would be
        # a lie and would collide with the one-active-per-student constraint.
        alumni_enrollment = self.alumnus.enrollments.get()
        self.assertEqual(alumni_enrollment.status, Enrollment.Status.COMPLETED)
        self.assertEqual(alumni_enrollment.outcome, Enrollment.Outcome.GRADUATED)

        # No year to anchor to => no fabricated enrollment.
        self.assertEqual(self.no_year.enrollments.count(), 0)

        # NOTHING was re-classed.
        after = {
            s.pk: (s.classroom_id, s.academic_year_id)
            for s in StudentProfile.objects.all()
        }
        self.assertEqual(after, self.before)

    def test_backfill_is_idempotent(self):
        self.run_backfill()
        first_count = Enrollment.objects.count()
        self.run_backfill()
        self.assertEqual(Enrollment.objects.count(), first_count)

    def test_current_classroom_resolves_identically_before_and_after_backfill(self):
        """The derivation must be a no-op change for every existing reader."""
        before = {
            s.pk: (s.current_classroom.pk if s.current_classroom else None)
            for s in StudentProfile.objects.all()
        }
        self.run_backfill()
        after = {
            s.pk: (s.current_classroom.pk if s.current_classroom else None)
            for s in StudentProfile.objects.all()
        }
        self.assertEqual(after, before)
