"""Tests for the canonical LMS submission service layer (apps.academics.lms_services).

Covers the single write path shared by the online portal views and the offline SODP
applier: submit (create / remote-wins dedup / late / closed-reject / force-resubmit),
grade, and the student-facing read helpers.
"""

from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.academics.lms_services import (
    AssignmentClosedError,
    grade_submission,
    open_assignments_for_student,
    submission_map_for_student,
    submit_assignment,
)
from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Subject,
    Term,
)
from apps.academics.models_lms import LMSAssignment, LMSSubmission
from apps.accounts.models import User
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School


class LMSSubmissionServiceTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="LMS Test School",
            slug="lms-test",
            subdomain="lms-test",
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        self.term = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name="Term 1",
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            is_active=True,
        )
        self.dept = Department.objects.create(school=self.school, name="Math", code="M")
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=self.dept,
            name="Grade 10",
            code="G10",
        )
        self.subject = Subject.objects.create(school=self.school, name="Algebra")
        self.teacher_user = User.objects.create_user(
            username="lms_teacher",
            email="lms_teacher@test.com",
            password="testpass123",
            is_staff=True,
            role=User.Role.TEACHER,
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user, school=self.school
        )
        self.student_user = User.objects.create_user(
            username="lms_student",
            email="lms_student@test.com",
            password="testpass123",
            role=User.Role.STUDENT,
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user,
            first_name="Sam",
            last_name="Tester",
            date_of_birth=date(2012, 1, 1),
            student_code="ST-LMS-1",
            school=self.school,
            classroom=self.classroom,
            academic_year=self.year,
        )

    def _assignment(self, *, status=LMSAssignment.Status.PUBLISHED, due_at=None):
        return LMSAssignment.objects.create(
            school=self.school,
            classroom=self.classroom,
            subject=self.subject,
            term=self.term,
            teacher=self.teacher,
            title="Chapter 3 problems",
            instructions="Do questions 1-10.",
            status=status,
            due_at=due_at if due_at is not None else timezone.now() + timedelta(days=3),
        )

    def test_submit_creates_submitted_row(self):
        assignment = self._assignment()
        sub, changed = submit_assignment(
            assignment=assignment, student=self.student, content="my answers"
        )
        self.assertTrue(changed)
        self.assertEqual(sub.status, LMSSubmission.Status.SUBMITTED)
        self.assertEqual(sub.content, "my answers")
        self.assertIsNotNone(sub.submitted_at)
        self.assertEqual(sub.school_id, self.school.id)

    def test_submit_is_idempotent_remote_wins(self):
        assignment = self._assignment()
        sub1, changed1 = submit_assignment(
            assignment=assignment, student=self.student, content="first"
        )
        sub2, changed2 = submit_assignment(
            assignment=assignment, student=self.student, content="second-replay"
        )
        self.assertTrue(changed1)
        self.assertFalse(changed2)  # already submitted → no-op dedup
        self.assertEqual(sub1.pk, sub2.pk)
        sub2.refresh_from_db()
        self.assertEqual(sub2.content, "first")  # replay did not clobber
        self.assertEqual(LMSSubmission.objects.filter(assignment=assignment).count(), 1)

    def test_force_resubmit_updates_content(self):
        assignment = self._assignment()
        submit_assignment(assignment=assignment, student=self.student, content="v1")
        sub, changed = submit_assignment(
            assignment=assignment, student=self.student, content="v2", force=True
        )
        self.assertTrue(changed)
        sub.refresh_from_db()
        self.assertEqual(sub.content, "v2")

    def test_submit_past_due_is_late(self):
        assignment = self._assignment(due_at=timezone.now() - timedelta(days=1))
        sub, changed = submit_assignment(
            assignment=assignment, student=self.student, content="late work"
        )
        self.assertTrue(changed)
        self.assertEqual(sub.status, LMSSubmission.Status.LATE)

    def test_submit_to_closed_assignment_rejected(self):
        assignment = self._assignment(status=LMSAssignment.Status.DRAFT)
        with self.assertRaises(AssignmentClosedError):
            submit_assignment(assignment=assignment, student=self.student, content="x")
        self.assertEqual(LMSSubmission.objects.filter(assignment=assignment).count(), 0)

    def test_grade_submission(self):
        assignment = self._assignment()
        sub, _ = submit_assignment(
            assignment=assignment, student=self.student, content="answers"
        )
        graded = grade_submission(
            submission=sub, score=85, feedback="Good work", graded_by=self.teacher_user
        )
        self.assertEqual(graded.status, LMSSubmission.Status.GRADED)
        self.assertEqual(int(graded.score), 85)
        self.assertEqual(graded.feedback, "Good work")
        self.assertIsNotNone(graded.graded_at)
        self.assertEqual(graded.graded_by_id, self.teacher_user.id)

    def test_open_assignments_and_submission_map(self):
        published = self._assignment()
        draft = self._assignment(status=LMSAssignment.Status.DRAFT)
        open_qs = open_assignments_for_student(
            school=self.school, student=self.student
        )
        ids = set(open_qs.values_list("id", flat=True))
        self.assertIn(published.id, ids)
        self.assertNotIn(draft.id, ids)

        submit_assignment(assignment=published, student=self.student, content="done")
        smap = submission_map_for_student(
            school=self.school, student=self.student, assignment_ids=[published.id]
        )
        self.assertIn(published.id, smap)
        self.assertEqual(smap[published.id].status, LMSSubmission.Status.SUBMITTED)


class LMSOfflineApplierTests(LMSSubmissionServiceTests):
    """The canonical offline rail (_apply_lms_submission) converges on LMSSubmission.

    Inherits the fixture from LMSSubmissionServiceTests (school/classroom/student-with-user).
    """

    def test_offline_applier_creates_canonical_submission(self):
        from apps.platform_runtime.offline_queue import _apply_lms_submission

        assignment = self._assignment()
        # student_id in the payload is deliberately spoofed; the applier must IGNORE it and
        # resolve the student from the authenticated user_id.
        result = _apply_lms_submission(
            self.school.id,
            self.student_user.id,
            {"assignment_id": assignment.id, "student_id": 999999, "content": "offline answer"},
        )
        self.assertTrue(result["ok"], result)
        sub = LMSSubmission.objects.get(assignment=assignment, student=self.student)
        self.assertEqual(sub.status, LMSSubmission.Status.SUBMITTED)
        self.assertEqual(sub.content, "offline answer")
        self.assertEqual(result["submission_id"], sub.pk)

    def test_offline_applier_is_idempotent_dedup(self):
        from apps.platform_runtime.offline_queue import _apply_lms_submission

        assignment = self._assignment()
        payload = {"assignment_id": assignment.id, "content": "first"}
        r1 = _apply_lms_submission(self.school.id, self.student_user.id, payload)
        r2 = _apply_lms_submission(self.school.id, self.student_user.id, payload)
        self.assertTrue(r1["ok"])
        self.assertTrue(r2["ok"])
        self.assertTrue(r2["dedup"])  # replay is a clean no-op
        self.assertEqual(LMSSubmission.objects.filter(assignment=assignment).count(), 1)

    def test_offline_applier_rejects_unknown_student_user(self):
        from apps.platform_runtime.offline_queue import _apply_lms_submission

        assignment = self._assignment()
        result = _apply_lms_submission(
            self.school.id,
            self.teacher_user.id,  # a non-student user has no StudentProfile
            {"assignment_id": assignment.id, "content": "x"},
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "student_profile_not_found")

    def test_offline_applier_rejects_cross_school_assignment(self):
        from apps.platform_runtime.offline_queue import _apply_lms_submission

        assignment = self._assignment()
        other_school = School.objects.create(
            name="Other", slug="other-lms", subdomain="other-lms", is_active=True
        )
        result = _apply_lms_submission(
            other_school.id,  # assignment does not belong to this school
            self.student_user.id,
            {"assignment_id": assignment.id, "content": "x"},
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "assignment_not_found")


class LMSTeacherAuthoringTests(LMSSubmissionServiceTests):
    """Teacher authoring side: create / publish / list / submissions."""

    def test_create_assignment_draft(self):
        from apps.academics.lms_services import create_assignment

        a = create_assignment(
            school=self.school,
            classroom=self.classroom,
            subject=self.subject,
            teacher=self.teacher,
            title="Essay 1",
            instructions="Write 500 words.",
        )
        self.assertEqual(a.status, LMSAssignment.Status.DRAFT)
        self.assertEqual(a.teacher_id, self.teacher.id)
        self.assertIsNone(a.available_at)

    def test_create_assignment_published_sets_available_at(self):
        from apps.academics.lms_services import create_assignment

        a = create_assignment(
            school=self.school,
            classroom=self.classroom,
            subject=self.subject,
            teacher=self.teacher,
            title="Quiz 1",
            publish=True,
        )
        self.assertEqual(a.status, LMSAssignment.Status.PUBLISHED)
        self.assertIsNotNone(a.available_at)
        self.assertTrue(a.is_open_for_submissions)

    def test_create_assignment_rejects_short_title(self):
        from apps.academics.lms_services import create_assignment

        with self.assertRaises(ValueError):
            create_assignment(
                school=self.school,
                classroom=self.classroom,
                subject=self.subject,
                teacher=self.teacher,
                title="x",
            )

    def test_publish_assignment(self):
        from apps.academics.lms_services import publish_assignment

        a = self._assignment(status=LMSAssignment.Status.DRAFT)
        published = publish_assignment(assignment=a)
        self.assertEqual(published.status, LMSAssignment.Status.PUBLISHED)
        self.assertIsNotNone(published.available_at)

    def test_teacher_assignments_for_counts(self):
        from apps.academics.lms_services import teacher_assignments_for

        a = self._assignment()
        submit_assignment(assignment=a, student=self.student, content="done")
        rows = list(teacher_assignments_for(school=self.school, teacher=self.teacher))
        self.assertTrue(any(r.id == a.id for r in rows))
        row = next(r for r in rows if r.id == a.id)
        self.assertEqual(row.submission_count, 1)
        self.assertEqual(row.graded_count, 0)

    def test_submissions_for_assignment(self):
        from apps.academics.lms_services import submissions_for_assignment

        a = self._assignment()
        submit_assignment(assignment=a, student=self.student, content="done")
        subs = list(submissions_for_assignment(school=self.school, assignment=a))
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0].student_id, self.student.id)


class LMSGradebookTests(LMSSubmissionServiceTests):
    """Read-only homework gradebook matrix (independent of evals.Evaluation)."""

    def test_gradebook_empty_when_no_published_assignments(self):
        from apps.academics.lms_services import homework_gradebook_for

        self._assignment(status=LMSAssignment.Status.DRAFT)  # drafts never appear
        gb = homework_gradebook_for(
            school=self.school, teacher=self.teacher, classroom=self.classroom
        )
        self.assertEqual(gb["assignments"], [])
        self.assertEqual(len(gb["rows"]), 1)  # the one active student
        self.assertEqual(gb["rows"][0]["cells"], [])
        self.assertIsNone(gb["rows"][0]["average"])

    def test_gradebook_average_is_over_graded_only(self):
        from apps.academics.lms_services import homework_gradebook_for

        a1 = self._assignment()
        a2 = self._assignment()
        s1, _ = submit_assignment(assignment=a1, student=self.student, content="x")
        grade_submission(submission=s1, score=80, graded_by=self.teacher_user)
        submit_assignment(assignment=a2, student=self.student, content="y")  # ungraded

        gb = homework_gradebook_for(
            school=self.school, teacher=self.teacher, classroom=self.classroom
        )
        self.assertEqual(len(gb["assignments"]), 2)
        row = gb["rows"][0]
        self.assertEqual(row["graded_count"], 1)
        self.assertEqual(int(row["average"]), 80)  # only the graded item counts
        scored = [c for c in row["cells"] if c["score"] is not None]
        self.assertEqual(len(scored), 1)
        self.assertEqual(int(scored[0]["score"]), 80)

    def test_gradebook_not_submitted_cell_status(self):
        from apps.academics.lms_services import homework_gradebook_for

        self._assignment()  # published; student has NOT submitted
        gb = homework_gradebook_for(
            school=self.school, teacher=self.teacher, classroom=self.classroom
        )
        row = gb["rows"][0]
        self.assertEqual(len(row["cells"]), 1)
        self.assertIsNone(row["cells"][0]["score"])
        self.assertEqual(
            row["cells"][0]["status"], LMSSubmission.Status.NOT_SUBMITTED
        )
        self.assertIsNone(row["average"])
