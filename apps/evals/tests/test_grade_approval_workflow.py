from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Term, Department, Specialty, Classroom, Subject, SubjectAssignment
from apps.evals.models import GradeApprovalRequest, TeacherAssignment
from apps.people.models import TeacherProfile, StudentProfile
from apps.siteconfig.models import SiteSettings


class GradeApprovalWorkflowTestCase(TestCase):
    def setUp(self):
        self.site_settings = SiteSettings.get_solo()
        self.site_settings.grade_approval_enabled = True
        self.site_settings.grade_approval_roles = ["DEAN"]
        self.site_settings.grade_post_roles = ["DEAN"]
        self.site_settings.save()

        self.year = AcademicYear.objects.create(name="2025/2026", start_date="2025-09-01", end_date="2026-08-31", is_active=True)
        self.term = Term.objects.create(academic_year=self.year, name="FIRST", position=1, start_date="2025-09-01", end_date="2025-11-30", is_active=True)
        dept = Department.objects.create(name="Science", code="SCI")
        self.specialty = Specialty.objects.create(department=dept, name="Physics", code="PHY")
        self.classroom = Classroom.objects.create(academic_year=self.year, department=dept, name="SS3A", code="SS3A")
        self.subject = Subject.objects.create(name="Physics")
        self.subject_assignment = SubjectAssignment.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=self.subject,
            coefficient=1.0,
        )

        self.teacher_user = User.objects.create_user("teacher", "teacher@example.com", "pass", role=User.Role.TEACHER)
        self.teacher_profile = TeacherProfile.objects.create(user=self.teacher_user)
        TeacherAssignment.objects.create(
            teacher=self.teacher_profile,
            academic_year=self.year,
            subject_assignment=self.subject_assignment,
            is_active=True,
        )
        self.student = StudentProfile.objects.create(
            first_name="Jane",
            last_name="Doe",
            student_code="STU001",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
            is_active=True,
        )

        self.dean_user = User.objects.create_user("dean", "dean@example.com", "secret", role=User.Role.DEAN)
        self.dean_user.is_staff = True
        self.dean_user.save()

    def test_submit_for_approval_creates_request(self):
        self.client.login(username="teacher", password="pass")
        data = {
            "subject_assignment_id": str(self.subject_assignment.id),
            f"seq1_{self.student.id}": "18",
            f"seq2_{self.student.id}": "17",
            f"exam_{self.student.id}": "16",
            f"mock_{self.student.id}": "15",
            f"practical_{self.student.id}": "14",
            f"remarks_{self.student.id}": "Looks good.",
            "action": "submit_for_approval",
        }
        response = self.client.post(reverse("evals:teacher_marks_entry"), data=data)
        self.assertRedirects(response, reverse("evals:teacher_marks_list"))
        self.assertEqual(GradeApprovalRequest.objects.count(), 1)
        request_obj = GradeApprovalRequest.objects.first()
        self.assertEqual(request_obj.status, GradeApprovalRequest.Status.PENDING)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Grade Approval Needed", mail.outbox[0].subject)

    def test_grade_approval_request_rejects_out_of_range_score(self):
        """Submit 25/20; model validators reject, so marks are not saved and no approval request is created."""
        self.client.login(username="teacher", password="pass")
        data = {
            "subject_assignment_id": str(self.subject_assignment.id),
            f"seq1_{self.student.id}": "25",  # out of range (max 20)
            f"seq2_{self.student.id}": "17",
            f"exam_{self.student.id}": "16",
            f"mock_{self.student.id}": "15",
            f"practical_{self.student.id}": "14",
            f"remarks_{self.student.id}": "Check the outlier.",
            "action": "submit_for_approval",
        }
        self.client.post(reverse("evals:teacher_marks_entry"), data=data)
        # Model MaxValueValidator(20) rejects 25; save fails, so no approval request is created
        self.assertEqual(GradeApprovalRequest.objects.count(), 0)

    def test_grade_approval_list_accessible_by_reviewers(self):
        GradeApprovalRequest.objects.create(
            teacher=self.teacher_profile,
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.subject_assignment,
            entries=[{"student_id": self.student.id, "scores": {"seq1": "18"}}],
            summary={"total_students": 1, "submitted_rows": 1},
            status=GradeApprovalRequest.Status.PENDING,
            requested_by=self.teacher_user,
        )
        self.client.login(username="dean", password="secret")
        response = self.client.get(reverse("evals:grade_approval_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Grade Approval Requests")

    def test_non_final_role_cannot_finalize(self):
        # Restrict final roles so dean cannot finalize
        self.site_settings.grade_post_roles = ["REGISTRAR"]
        self.site_settings.save()
        request_obj = GradeApprovalRequest.objects.create(
            teacher=self.teacher_profile,
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.subject_assignment,
            entries=[{"student_id": self.student.id, "scores": {"seq1": "10"}}],
            summary={"total_students": 1, "submitted_rows": 1},
            status=GradeApprovalRequest.Status.PENDING,
            requested_by=self.teacher_user,
        )
        self.client.login(username="dean", password="secret")
        response = self.client.get(reverse("evals:grade_approval_detail", args=[request_obj.id]))
        choices = response.context["form"].fields["status"].choices
        self.assertNotIn(GradeApprovalRequest.Status.APPROVED, [choice[0] for choice in choices])
        # POST with APPROVED (e.g. forged) — form has no APPROVED choice so invalid; view must not finalize
        post_response = self.client.post(reverse("evals:grade_approval_detail", args=[request_obj.id]), {
            "status": GradeApprovalRequest.Status.APPROVED,
            "reviewer_notes": "Finalizing",
        })
        self.assertEqual(post_response.status_code, 200)
        # Approval must still be PENDING (not finalized)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, GradeApprovalRequest.Status.PENDING)
        # Form should show an error on status (invalid choice or custom message)
        self.assertIn("form", post_response.context)
        form = post_response.context["form"]
        self.assertTrue(form.errors.get("status"), msg="Expected form error on status when non-final role submits APPROVED")
