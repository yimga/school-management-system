"""
Tests for report publish term view: RBAC and approved-grades settings.
"""
from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.evals.models import Evaluation, GradeApprovalRequest
from apps.people.models import StudentProfile, TeacherProfile
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.reports.models import TermPublishStatus
from apps.reports.services import grade_approval_publish_readiness, term_report_context


class PublishTermRBACTestCase(TestCase):
    """Publish term page is staff-only and respects reports_require_approved_grades_before_publish."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff_pub",
            password="testpass123",
            is_staff=True,
        )
        self.staff.role = User.Role.ADMIN
        self.staff.save(update_fields=["role"])
        self.year = AcademicYear.objects.create(
            name="2024-2025",
            start_date=date(2024, 9, 1),
            end_date=date(2025, 6, 30),
            is_active=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year,
            name="First",
            start_date=date(2024, 9, 1),
            end_date=date(2024, 12, 15),
            position=1,
            is_active=True,
        )
        self.department = Department.objects.create(name="Science", code="SCI")
        self.specialty = Specialty.objects.create(department=self.department, name="Physics", code="PHY")
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="SS1A",
            code="SS1A",
        )
        self.subject = Subject.objects.create(name="Mathematics")
        self.subject_assignment = SubjectAssignment.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=self.subject,
            coefficient=1,
        )
        self.teacher_user = User.objects.create_user(
            username="teacher_pub",
            password="testpass123",
            role=User.Role.TEACHER,
        )
        self.teacher_profile = TeacherProfile.objects.create(user=self.teacher_user)
        self.student = StudentProfile.objects.create(
            first_name="Jane",
            last_name="Doe",
            student_code="STU-PUB-1",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
            is_active=True,
        )
        self.site = get_platform_site_settings_record(create=True)
        self.site.grade_approval_enabled = True
        self.site.reports_require_approved_grades_before_publish = True
        self.site.reports_use_approved_grades_only = True
        self.site.save()

    def _create_evaluation(self):
        return Evaluation.objects.create(
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.subject_assignment,
            student=self.student,
            teacher=self.teacher_profile,
            seq1_score=15,
            seq2_score=14,
            exam_score=16,
            remarks="Ready for publish tests",
        )

    def _create_approval(self, status):
        return GradeApprovalRequest.objects.create(
            teacher=self.teacher_profile,
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.subject_assignment,
            entries=[{"student_id": self.student.id, "scores": {"seq1": "15", "seq2": "14", "exam": "16"}}],
            summary={"total_students": 1, "submitted_rows": 1},
            status=status,
            requested_by=self.teacher_user,
        )

    def test_publish_term_requires_staff(self):
        parent = User.objects.create_user(
            username="parent_pub",
            password="testpass123",
            role=User.Role.PARENT,
        )
        self.client.force_login(parent)
        response = self.client.get(reverse("reports:publish_term_results"))
        self.assertIn(response.status_code, (302, 403))

    def test_publish_term_page_loads_for_staff(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("reports:publish_term_results"))
        self.assertEqual(response.status_code, 200)

    def test_publish_blocks_when_approval_request_is_missing(self):
        self.client.force_login(self.staff)
        self._create_evaluation()

        response = self.client.post(
            reverse("reports:publish_term_results"),
            data={"year": self.year.id, "term": self.term.id, "publish_school": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cannot publish: grade approvals are incomplete")
        self.assertFalse(
            TermPublishStatus.objects.filter(
                academic_year=self.year,
                term=self.term,
                classroom__isnull=True,
                is_published=True,
            ).exists()
        )

    def test_publish_blocks_when_latest_approval_is_not_final(self):
        self.client.force_login(self.staff)
        self._create_evaluation()
        self._create_approval(GradeApprovalRequest.Status.APPROVED)
        self._create_approval(GradeApprovalRequest.Status.REVISION_REQUESTED)

        response = self.client.post(
            reverse("reports:publish_term_results"),
            data={"year": self.year.id, "term": self.term.id, "publish_school": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pending: 1")
        self.assertFalse(
            TermPublishStatus.objects.filter(
                academic_year=self.year,
                term=self.term,
                classroom__isnull=True,
                is_published=True,
            ).exists()
        )

    def test_publish_allows_when_latest_approval_is_approved(self):
        self.client.force_login(self.staff)
        self._create_evaluation()
        self._create_approval(GradeApprovalRequest.Status.APPROVED)

        response = self.client.post(
            reverse("reports:publish_term_results"),
            data={"year": self.year.id, "term": self.term.id, "publish_school": "1"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            TermPublishStatus.objects.filter(
                academic_year=self.year,
                term=self.term,
                classroom__isnull=True,
                is_published=True,
            ).exists()
        )

    def test_unpublish_is_allowed_even_when_approvals_are_not_ready(self):
        self.client.force_login(self.staff)
        self._create_evaluation()
        TermPublishStatus.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=None,
            is_published=True,
            published_by=self.staff,
        )

        response = self.client.post(
            reverse("reports:publish_term_results"),
            data={"year": self.year.id, "term": self.term.id},
        )

        self.assertEqual(response.status_code, 302)
        school_status = TermPublishStatus.objects.get(
            academic_year=self.year,
            term=self.term,
            classroom__isnull=True,
        )
        self.assertFalse(school_status.is_published)

    def test_class_scope_publish_checks_only_selected_classrooms(self):
        self.client.force_login(self.staff)
        self._create_evaluation()
        self._create_approval(GradeApprovalRequest.Status.APPROVED)

        classroom_b = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="SS1B",
            code="SS1B",
        )
        subject_assignment_b = SubjectAssignment.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=classroom_b,
            specialty=self.specialty,
            subject=self.subject,
            coefficient=1,
        )
        student_b = StudentProfile.objects.create(
            first_name="John",
            last_name="Scope",
            student_code="STU-PUB-2",
            academic_year=self.year,
            classroom=classroom_b,
            specialty=self.specialty,
            is_active=True,
        )
        Evaluation.objects.create(
            academic_year=self.year,
            term=self.term,
            subject_assignment=subject_assignment_b,
            student=student_b,
            teacher=self.teacher_profile,
            seq1_score=9,
            seq2_score=10,
            exam_score=11,
            remarks="No approval yet in other class",
        )

        response = self.client.post(
            reverse("reports:publish_term_results"),
            data={
                "year": self.year.id,
                "term": self.term.id,
                "classroom_ids": [str(self.classroom.id)],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            TermPublishStatus.objects.filter(
                academic_year=self.year,
                term=self.term,
                classroom=self.classroom,
                is_published=True,
            ).exists()
        )
        self.assertFalse(
            TermPublishStatus.objects.filter(
                academic_year=self.year,
                term=self.term,
                classroom=classroom_b,
                is_published=True,
            ).exists()
        )
        self.assertFalse(
            TermPublishStatus.objects.filter(
                academic_year=self.year,
                term=self.term,
                classroom__isnull=True,
                is_published=True,
            ).exists()
        )

    def test_term_context_uses_latest_approval_status_for_approved_only_filter(self):
        self._create_evaluation()
        self._create_approval(GradeApprovalRequest.Status.APPROVED)
        self._create_approval(GradeApprovalRequest.Status.UNDER_REVIEW)

        context = term_report_context(self.student, self.year, self.term)

        self.assertEqual(len(context["rows"]), 0)

    def test_publish_readiness_respects_empty_classroom_scope(self):
        self._create_evaluation()
        self._create_approval(GradeApprovalRequest.Status.APPROVED)

        scoped_state = grade_approval_publish_readiness(
            self.year.id,
            self.term.id,
            classroom_ids=[],
        )
        self.assertEqual(scoped_state["subject_assignments_with_grades"], 0)
        self.assertEqual(scoped_state["approved_count"], 0)
        self.assertTrue(scoped_state["ready_for_publish"])

        included_state = grade_approval_publish_readiness(
            self.year.id,
            self.term.id,
            classroom_ids=[self.classroom.id],
        )
        self.assertEqual(included_state["subject_assignments_with_grades"], 1)
        self.assertEqual(included_state["approved_count"], 1)
        self.assertTrue(included_state["ready_for_publish"])
