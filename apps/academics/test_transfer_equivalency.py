from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.academics.degree_audit import run_degree_audit
from apps.academics.models import DegreeProgram, StudentDegreeEnrollment, TransferCredit
from apps.academics.services import (
    get_approved_transfer_equivalency_map,
    review_transfer_equivalency_request,
    submit_transfer_equivalency_request,
)
from apps.people.models import StudentProfile
from apps.schools.models import School


class TransferEquivalencyWorkflowTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Equivalency School",
            slug="equivalency-school",
            subdomain="equivalency-school",
            is_active=True,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Grace",
            last_name="Hopper",
            custom_attributes={"gpa": 3.7},
        )
        self.program = DegreeProgram.objects.create(
            school=self.school,
            name="BSc Informatics",
            level="BSC",
            requirements_json={
                "min_credits": 3,
                "required_course_codes": ["PHL101"],
            },
            is_active=True,
        )
        self.enrollment = StudentDegreeEnrollment.objects.create(
            student=self.student,
            program=self.program,
        )
        self.transfer_credit = TransferCredit.objects.create(
            student=self.student,
            external_institution="Transfer Institute",
            course_code="INTRO_LOGIC",
            credits=Decimal("3.00"),
            approved_at=timezone.now(),
        )
        self.reviewer = User.objects.create_user(
            username="reviewer.equiv",
            email="reviewer.equiv@example.com",
            password="x",
            role=User.Role.ADMIN,
        )

    def test_workflow_approval_applies_to_degree_audit(self):
        request_obj = submit_transfer_equivalency_request(
            student=self.student,
            program=self.program,
            transfer_credit=self.transfer_credit,
            external_course_code="intro_logic",
            internal_course_code="phl101",
            requested_by=self.reviewer,
            request_notes="Community college transfer",
        )
        review_transfer_equivalency_request(
            request_obj,
            approve=True,
            reviewed_by=self.reviewer,
            reviewer_notes="Equivalent syllabus verified",
        )

        mapping = get_approved_transfer_equivalency_map(
            student=self.student, program=self.program
        )
        self.assertEqual(mapping, {"PHL101": ["INTRO_LOGIC"]})

        result = run_degree_audit(self.enrollment)
        self.assertTrue(result["is_eligible"])
        self.assertEqual(result["missing_courses"], [])

    def test_rejected_equivalency_is_not_applied(self):
        request_obj = submit_transfer_equivalency_request(
            student=self.student,
            program=self.program,
            external_course_code="INTRO_LOGIC",
            internal_course_code="PHL101",
        )
        review_transfer_equivalency_request(
            request_obj,
            approve=False,
            reviewed_by=self.reviewer,
            reviewer_notes="Insufficient overlap",
        )

        mapping = get_approved_transfer_equivalency_map(
            student=self.student, program=self.program
        )
        self.assertEqual(mapping, {})

        result = run_degree_audit(self.enrollment)
        self.assertFalse(result["is_eligible"])
        self.assertEqual(result["missing_courses"], ["PHL101"])

    def test_submit_rejects_program_student_school_mismatch(self):
        other_school = School.objects.create(
            name="Other School",
            slug="other-school",
            subdomain="other-school",
            is_active=True,
        )
        other_program = DegreeProgram.objects.create(
            school=other_school,
            name="BSc Other",
            level="BSC",
            requirements_json={},
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            submit_transfer_equivalency_request(
                student=self.student,
                program=other_program,
                external_course_code="INTRO_LOGIC",
                internal_course_code="PHL101",
            )
