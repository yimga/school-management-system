"""School-wide ranking must not rank students from another school.

Under schema-per-tenant a bare `StudentProfile.objects.filter(is_active=True)`
is safe: the schema search_path already excludes every other school. Under RLS
-- which is what the Cameroon edge box runs -- several schools share ONE
schema, and the only thing standing between the query and a foreign roll is a
policy on the connection Django is not guaranteed to be using.

`_compute_rankings` carried a `# tenant-isolation-allow` marker asserting the
school-wide branch was "scoped via surrounding tenant context". Nothing scoped
it. This file is the reproduction: two schools, one schema, one term.

The leak is not only a disclosure. Every foreign student enters `aggregates`
with an average of 0.0, so they pad `total_students`, and every real student's
percentile is computed against a cohort that is not their school.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from django.core.cache import cache
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
from apps.accounts.models import User
from apps.evals.models import Evaluation
from apps.evals.ranking import (
    _compute_rankings,
    get_class_ranking,
    get_rank_position_with_context,
    get_school_ranking,
)
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School


class SchoolWideRankingScopeTests(TestCase):
    """Two schools in one schema. Rankings for one must never see the other."""

    @classmethod
    def setUpTestData(cls):
        cls.uid = uuid.uuid4().hex[:8]
        cls.school_a, cls.a = cls._build_school("A", ["Ada", "Bih"])
        cls.school_b, cls.b = cls._build_school("B", ["Xu", "Yaya", "Zed"])

    @classmethod
    def _build_school(cls, tag, names):
        """A whole small school: year, term, classroom, subject, marked roll."""
        uid = cls.uid + tag
        school = School.objects.create(
            name="Rank " + tag + " " + uid,
            slug="rank-" + uid.lower(),
            subdomain="rank" + uid.lower(),
            is_active=True,
        )
        year = AcademicYear.objects.create(
            school=school,
            name="2026/2027",
            start_date=dt.date(2026, 9, 1),
            end_date=dt.date(2027, 6, 30),
            is_active=True,
        )
        term = Term.objects.create(
            school=school,
            academic_year=year,
            name="Term 1",
            start_date=dt.date(2026, 9, 1),
            end_date=dt.date(2026, 12, 10),
        )
        dept = Department.objects.create(
            school=school, name="Sciences " + uid, code="SCI" + uid[:5]
        )
        specialty = Specialty.objects.create(
            school=school, department=dept, name="General", code="GEN" + uid[:5]
        )
        classroom = Classroom.objects.create(
            school=school,
            academic_year=year,
            department=dept,
            name="Form 5" + tag,
            code="F5" + uid[:5],
        )
        subject = Subject.objects.create(
            school=school, name="Mathematics", code="MTH" + uid[:5]
        )
        assignment = SubjectAssignment.objects.create(
            school=school,
            academic_year=year,
            term=term,
            classroom=classroom,
            specialty=specialty,
            subject=subject,
            coefficient=Decimal("4.00"),
        )
        teacher = TeacherProfile.objects.create(
            user=User.objects.create_user(
                username="rk_t_" + uid, password="Test1234!x"
            )
        )
        students = []
        for i, name in enumerate(names):
            student = StudentProfile.objects.create(
                school=school,
                first_name=name,
                last_name="Scope",
                date_of_birth="2011-05-05",
                student_code="STD" + uid + str(i),
                academic_year=year,
                classroom=classroom,
                specialty=specialty,
                is_active=True,
            )
            # Descending marks so rank order is deterministic and distinct.
            Evaluation.objects.create(
                school=school,
                academic_year=year,
                term=term,
                subject_assignment=assignment,
                student=student,
                teacher=teacher,
                seq1_score=Decimal(str(16 - i)),
            )
            students.append(student)
        ns = {
            "year": year,
            "term": term,
            "classroom": classroom,
            "students": students,
        }
        return school, ns

    def setUp(self):
        # get_school_ranking memoises; a stale entry would mask the fix.
        cache.clear()

    # -- the leak --------------------------------------------------------

    def test_school_wide_ranking_holds_only_this_schools_students(self):
        entries = _compute_rankings(self.a["term"])
        foreign = [
            e.student for e in entries if e.student.school_id != self.school_a.id
        ]
        self.assertEqual(
            [s.student_code for s in foreign],
            [],
            "school-wide ranking for school A returned students from another "
            "school in the same schema",
        )
        self.assertEqual(
            len(entries),
            len(self.a["students"]),
            "cohort size must be school A's roll, not every active student "
            "in the database",
        )

    def test_public_school_ranking_entrypoint_is_scoped_too(self):
        entries = get_school_ranking(self.a["term"])
        self.assertEqual(
            sorted(e.student.school_id for e in entries),
            [self.school_a.id] * len(self.a["students"]),
        )

    def test_cohort_size_and_percentile_are_computed_against_the_right_roll(self):
        top = self.a["students"][0]
        ctx = get_rank_position_with_context(top, self.a["term"])
        self.assertEqual(
            ctx["school_size"],
            len(self.a["students"]),
            "a padded cohort silently deflates every percentile in the school",
        )
        self.assertEqual(ctx["school_rank"], 1)
        self.assertEqual(ctx["school_percentile"], 100.0)

    def test_the_other_school_sees_only_itself(self):
        """Symmetry: the fix must not merely privilege whichever school is first."""
        entries = _compute_rankings(self.b["term"])
        self.assertEqual(
            {e.student.school_id for e in entries},
            {self.school_b.id},
        )
        self.assertEqual(len(entries), len(self.b["students"]))

    # -- controls --------------------------------------------------------

    def test_classroom_branch_was_already_scoped(self):
        """The classroom filter was never the bug; keep it proven."""
        entries = get_class_ranking(self.a["classroom"], self.a["term"])
        self.assertEqual(
            {e.student.school_id for e in entries},
            {self.school_a.id},
        )
        self.assertEqual(len(entries), len(self.a["students"]))

    def test_the_fixture_really_does_share_one_schema(self):
        """If this fails the whole file is vacuous -- the leak cannot be seen."""
        self.assertNotEqual(self.school_a.id, self.school_b.id)
        self.assertEqual(
            StudentProfile.objects.filter(
                is_active=True,
                school_id__in=[self.school_a.id, self.school_b.id],
            ).count(),
            len(self.a["students"]) + len(self.b["students"]),
            "both schools' students must be visible to an unfiltered query, or "
            "this test proves nothing",
        )
