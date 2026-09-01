"""The grades lander may borrow a teacher, but never from another tenant.

Audit close-out, 2026-09-01. ``GradesLander._assignment_teacher`` used to end
with an UNSCOPED last resort::

    return TeacherProfile.objects.order_by("pk").first()

reached whenever the importing school had zero ``TeacherProfile`` rows — a
routine state, because staff land in an earlier wave than grades. It carried an
isolation-allow marker asserting that schema-per-tenant context isolated the
query "when no school FK", and the reason was false twice over: the line
directly above it filters ``school=ctx.school``, so the model plainly HAS a
school FK; and the platform also ships a shared-schema RLS mode
(``apps/tenancy/strategy.py``) for the sovereign edge box, where every school's
teachers live in one ``people_teacherprofile`` table whose RLS policy is
recorded as ``missing-force`` — so Django, which owns the table, is not bound by
it either. Measured live: a bundle for school ``4154c00a…`` landed an assignment
attributed to a teacher of school ``42ac5473…``.

What is NOT under test here is the fallback itself. Borrowing a teacher of the
SAME school is a deliberate product call — the score, student, subject and term
are all faithful, and holding the row would discard academic history the school
is paying to migrate (``test_landers_fk_resolution`` pins that). These tests pin
the two things that were missing from it:

1. The borrowing stops at the tenant line. With no teacher in the tenant the row
   is HELD (``invalid_ref``, the class the zero-touch spec replays once staff
   land), never attributed to a stranger.
2. A borrowed teacher is VISIBLE. Filler attribution is declared in the row's own
   ``remarks``, the same provenance column and convention the lander already uses
   for an aggregate score, so the admin who is supposed to reassign it can find
   the rows by query instead of by noticing that a teacher does not recognise a
   class.

The trap that makes test 1 mean anything: a rival school's teacher is minted at a
LOWER pk than anything in the importing school, so a naive global
``order_by("pk").first()`` genuinely reaches across. Without that, the unscoped
query returns the same row as the scoped one and the test proves nothing.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.evals.models import Evaluation
from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.grades_lander import (
    _REMARK_AGGREGATE,
    _REMARK_FILLER_TEACHER,
    GradesLander,
)
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School

User = get_user_model()


class _ImportingSchoolMixin:
    """One importable grading graph, plus a rival tenant minted BEFORE it."""

    def _mint_rival_teacher(self, tag: str) -> TeacherProfile:
        """A teacher of ANOTHER school. Minted first, so it wins ``order_by(pk)``."""
        rival_school = School.objects.create(
            name=f"Rival {tag}",
            slug=f"rival-{tag}",
            subdomain=f"rival-{tag}",
        )
        rival_user = User.objects.create_user(
            username=f"rival_teacher_{tag}", password="pass123"
        )
        return TeacherProfile.objects.create(user=rival_user, school=rival_school)

    def _build_graph(self, tag: str, *, with_teacher: bool):
        school = School.objects.create(
            name=f"Importing {tag}", slug=f"importing-{tag}", subdomain=f"importing-{tag}"
        )
        year = AcademicYear.objects.create(
            school=school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
            is_active=True,
        )
        department = Department.objects.create(
            school=school, name="Science", code=f"SCI-{tag}"
        )
        classroom = Classroom.objects.create(
            school=school,
            academic_year=year,
            department=department,
            name="Form 4A",
            code=f"F4A-{tag}",
        )
        specialty = Specialty.objects.create(
            school=school, department=department, name="General", code=f"GEN-{tag}"
        )
        subject = Subject.objects.create(school=school, name="Mathematics")
        term = Term.objects.create(
            school=school,
            academic_year=year,
            name="FIRST",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
        )
        assignment = SubjectAssignment.objects.create(
            school=school,
            academic_year=year,
            term=term,
            classroom=classroom,
            specialty=specialty,
            subject=subject,
        )
        teacher = None
        if with_teacher:
            teacher_user = User.objects.create_user(
                username=f"our_teacher_{tag}", password="pass123"
            )
            teacher = TeacherProfile.objects.create(user=teacher_user, school=school)
        student = StudentProfile.objects.create(
            school=school,
            first_name="Placed",
            last_name="Student",
            admission_number=f"ADM-{tag}-1",
            academic_year=year,
            classroom=classroom,
            specialty=specialty,
        )
        return {
            "school": school,
            "year": year,
            "term": term,
            "assignment": assignment,
            "teacher": teacher,
            "student": student,
            "admission_number": f"ADM-{tag}-1",
        }

    def _ctx(self, school, dry_run: bool = False) -> LanderContext:
        return LanderContext(
            school=school,
            schema_name="",
            bundle_id=None,
            artifact_id=None,
            dry_run=dry_run,
        )

    def _row(self, admission_number: str, **overrides):
        row = {
            "student_external_id": admission_number,
            "subject_code": "Mathematics",
            "term": "FIRST",
            "academic_year": "2025/2026",
            "seq1_score": "14.50",
            "seq2_score": "15.00",
        }
        row.update(overrides)
        return row

    def _foreign_attributions(self, fx):
        """Landed rows whose teacher is not this school's. NULL-safe on purpose.

        ``.exclude(teacher__school=school)`` would MISS a teacher whose own
        ``school`` is NULL — ``NOT (school_id = X)`` is NULL, not true, for a NULL
        column, so the row silently drops out of the very queryset meant to catch
        it. Comparing in Python has no NULL arm to fall through.
        """
        return [
            ev
            for ev in Evaluation.objects.filter(student=fx["student"]).select_related(
                "teacher"
            )
            if ev.teacher.school_id != fx["school"].pk
        ]


class GradesTeacherAttributionStaysInTenantTests(_ImportingSchoolMixin, TestCase):
    def setUp(self):
        # Order matters: the rival is minted FIRST so its pk is the lowest of any
        # teacher this test creates.
        self.rival_teacher = self._mint_rival_teacher("p1")
        self.fx = self._build_graph("p1", with_teacher=False)

    def _assert_trap_armed(self):
        """The unscoped query must be able to return somebody else's teacher.

        Without this the test is theatre: if the importing school were the only
        holder of a TeacherProfile, ``order_by("pk").first()`` would return the
        same row as ``filter(school=...)`` and the cross-tenant reach would be
        invisible.
        """
        self.assertEqual(
            TeacherProfile.objects.filter(school=self.fx["school"]).count(),
            0,
            "the importing school must have NO teacher for this branch to run",
        )
        globally_first = TeacherProfile.objects.order_by("pk").first()
        self.assertIsNotNone(
            globally_first, "trap not armed: no TeacherProfile exists anywhere"
        )
        self.assertNotEqual(
            globally_first.school_id,
            self.fx["school"].pk,
            "trap not armed: the globally-first teacher is the importing "
            "school's own, so an unscoped read would look correct",
        )
        self.assertEqual(
            globally_first.pk,
            self.rival_teacher.pk,
            "trap not armed: expected the rival tenant's teacher to be the "
            "globally-first row an unscoped read would pick up",
        )

    def test_zero_teacher_school_holds_the_row_rather_than_borrow_a_stranger(self):
        self._assert_trap_armed()

        result = GradesLander().land(
            canonical_rows=iter([self._row(self.fx["admission_number"])]),
            ctx=self._ctx(self.fx["school"]),
        )

        foreign = self._foreign_attributions(self.fx)
        self.assertEqual(
            [(ev.pk, ev.teacher.school_id) for ev in foreign],
            [],
            "a grade landed attributed to a teacher of ANOTHER school",
        )
        self.assertEqual(
            Evaluation.objects.filter(student=self.fx["student"]).count(),
            0,
            "nothing may land while the tenant has nobody to attribute it to",
        )
        self.assertEqual(result.created, 0)
        self.assertEqual(result.quarantined, 1)
        self.assertEqual(len(result.errors), 1)

    def test_the_hold_says_what_the_school_must_fix_and_is_replayable(self):
        result = GradesLander().land(
            canonical_rows=iter([self._row(self.fx["admission_number"])]),
            ctx=self._ctx(self.fx["school"]),
        )
        self.assertEqual(result.quarantined, 1)
        message = result.errors[0]
        self.assertIn("no teacher on record", message)
        self.assertIn("nobody in this tenant", message)
        self.assertIn(self.fx["admission_number"], message)

        held = result.error_rows[0]
        self.assertEqual(held["error"], message)
        # ``invalid_ref`` is the replayable class: "this school has no teachers
        # yet" is nearly always the staff wave not having landed, so the row
        # should come back on its own rather than wait for a human.
        self.assertEqual(held["reason_code"], "invalid_ref")
        self.assertIn(self.fx["admission_number"], str(held["row"]))

    def test_the_rival_tenant_is_left_untouched(self):
        GradesLander().land(
            canonical_rows=iter([self._row(self.fx["admission_number"])]),
            ctx=self._ctx(self.fx["school"]),
        )
        self.assertEqual(
            Evaluation.objects.filter(teacher=self.rival_teacher).count(),
            0,
            "the other tenant's teacher must not acquire evaluations from an "
            "import they have nothing to do with",
        )

    def test_a_bundle_with_no_school_cannot_borrow_anyone(self):
        """``MigrationBundle.school`` is nullable (pre-tenant signup bundles).

        With no tenant named there is nobody to borrow FROM, and the old code
        went straight to the global first-by-pk read in exactly this state.
        """
        self.assertIsNone(
            GradesLander._school_teacher_fallback(
                TeacherProfile, self._ctx(None)
            )
        )


class GradesFillerAttributionIsVisibleTests(_ImportingSchoolMixin, TestCase):
    """A borrowed teacher that nobody can find is a teacher nobody reassigns."""

    def setUp(self):
        self.rival_teacher = self._mint_rival_teacher("p2")
        self.fx = self._build_graph("p2", with_teacher=True)
        self.assertLess(
            self.rival_teacher.pk,
            self.fx["teacher"].pk,
            "trap not armed: the rival teacher must sort first by pk",
        )

    def test_a_real_attribution_writes_no_filler_remark(self):
        """Control: the note must not be written unconditionally."""
        self.fx["assignment"].teachers.add(self.fx["teacher"].user)
        result = GradesLander().land(
            canonical_rows=iter([self._row(self.fx["admission_number"])]),
            ctx=self._ctx(self.fx["school"]),
        )
        self.assertEqual(result.errors, [])
        ev = Evaluation.objects.get(student=self.fx["student"])
        self.assertEqual(ev.teacher_id, self.fx["teacher"].pk)
        self.assertEqual(ev.remarks, "")

    def test_filler_attribution_is_declared_in_remarks(self):
        self.fx["assignment"].teachers.clear()
        result = GradesLander().land(
            canonical_rows=iter([self._row(self.fx["admission_number"])]),
            ctx=self._ctx(self.fx["school"]),
        )
        self.assertEqual(result.errors, [])
        self.assertEqual(result.created, 1)
        ev = Evaluation.objects.get(student=self.fx["student"])
        # Still inside the tenant...
        self.assertEqual(ev.teacher_id, self.fx["teacher"].pk)
        self.assertNotEqual(ev.teacher_id, self.rival_teacher.pk)
        # ...and now findable by the admin who has to reassign it.
        self.assertEqual(ev.remarks, _REMARK_FILLER_TEACHER)
        self.assertEqual(
            Evaluation.objects.filter(
                student__school=self.fx["school"],
                remarks__contains=_REMARK_FILLER_TEACHER,
            ).count(),
            1,
            "the provenance must be queryable, not merely present",
        )
        # The grade itself is untouched by the attribution gap.
        self.assertEqual(ev.seq1_score, Decimal("14.50"))
        self.assertEqual(ev.seq2_score, Decimal("15.00"))

    def test_filler_note_joins_the_existing_aggregate_note(self):
        """Both provenances are true at once, so both are written.

        ``_REMARK_AGGREGATE`` stays first and unchanged, so the existing
        aggregate-provenance contract is not disturbed by adding a second note.
        """
        self.fx["assignment"].teachers.clear()
        row = self._row(self.fx["admission_number"])
        row.pop("seq1_score")
        row.pop("seq2_score")
        row["score"] = "13.25"
        result = GradesLander().land(
            canonical_rows=iter([row]), ctx=self._ctx(self.fx["school"])
        )
        self.assertEqual(result.errors, [])
        ev = Evaluation.objects.get(student=self.fx["student"])
        self.assertEqual(
            ev.remarks, f"{_REMARK_AGGREGATE}; {_REMARK_FILLER_TEACHER}"
        )
        self.assertEqual(ev.exam_score, Decimal("13.25"))
        self.assertLessEqual(
            len(ev.remarks),
            Evaluation._meta.get_field("remarks").max_length,
            "the composed provenance must fit the column",
        )


class RetiredMarkerPremiseTests(TestCase):
    """The retired marker's stated reason, checked against the models.

    Kept as a test rather than a comment because both halves are structural: if
    either ever becomes true, the argument for holding the row changes and
    somebody should be made to re-read it.
    """

    def test_teacherprofile_has_a_school_fk(self):
        field = TeacherProfile._meta.get_field("school")
        self.assertTrue(field.is_relation)
        self.assertEqual(field.related_model.__name__, "School")

    def test_evaluation_teacher_is_not_nullable(self):
        """Why "land it unattributed" was not on the table.

        A null teacher would need a schema migration, and this repo enforces one
        migration leaf per app; holding the row needs neither.
        """
        self.assertFalse(Evaluation._meta.get_field("teacher").null)
