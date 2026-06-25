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
        self.student = StudentProfile.objects.create(
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
