from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.academics.degree_audit import run_degree_audit
from apps.academics.models import (
    AcademicYear,
    Classroom,
    DegreeProgram,
    Department,
    GraduateMilestone,
    Specialty,
    StudentDegreeEnrollment,
    Subject,
    SubjectAssignment,
    Term,
    TransferCredit,
)
from apps.evals.models import Evaluation
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School


class DegreeAuditSolverTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Degree Audit School",
            slug="degree-audit-school",
            subdomain="degree-audit-school",
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        self.term1 = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name="TERM_1",
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            is_active=True,
        )
        self.term2 = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name="TERM_2",
            position=2,
            start_date=date(2026, 1, 5),
            end_date=date(2026, 4, 30),
            is_active=True,
        )
        self.department = Department.objects.create(
            school=self.school,
            name="Science",
            code="SCI-DA",
        )
        self.specialty = Specialty.objects.create(
            school=self.school,
            department=self.department,
            name="General Science",
            code="GS-DA",
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=self.department,
            name="Level 200",
            code="L200-DA",
        )

        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Ada",
            last_name="Lovelace",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
            custom_attributes={"gpa": 3.4},
        )
        teacher_user = User.objects.create_user(
            username="teacher.degree.audit",
            email="teacher.degree.audit@example.com",
            password="x",
            role=User.Role.TEACHER,
        )
        self.teacher = TeacherProfile.objects.create(
            school=self.school,
            user=teacher_user,
        )

    def _enrollment(self, requirements_json: dict) -> StudentDegreeEnrollment:
        program = DegreeProgram.objects.create(
            school=self.school,
            name="BSc Computer Science",
            level="BSC",
            requirements_json=requirements_json,
            is_active=True,
        )
        return StudentDegreeEnrollment.objects.create(
            student=self.student,
            program=program,
            is_active=True,
        )

    def _transfer_credit(self, code: str, credits: str):
        TransferCredit.objects.create(
            student=self.student,
            external_institution="External University",
            course_code=code,
            credits=Decimal(credits),
            approved_at=timezone.now(),
        )

    def test_required_courses_resolve_with_equivalency_and_waiver(self):
        self._transfer_credit("INTRO_LOGIC", "3.00")
        self._transfer_credit("CALC2", "3.00")

        enrollment = self._enrollment(
            {
                "min_credits": 6,
                "required_course_codes": ["PHL101", "ADVPHY"],
                "waived_course_codes": ["ADVPHY"],
                "course_equivalencies": {
                    "PHL101": ["INTRO_LOGIC"],
                },
                "prerequisite_graph": {
                    "ADVPHY": ["CALC2"],
                },
                "min_gpa": 3.0,
            }
        )

        result = run_degree_audit(enrollment)

        self.assertTrue(result["is_eligible"])
        self.assertEqual(result["missing_courses"], [])
        self.assertEqual(result["missing_prerequisites"], {})
        self.assertEqual(result["missing_corequisites"], {})
        self.assertEqual(result["transfer_credits"], Decimal("6.00"))

    def test_prerequisite_and_corequisite_gaps_block_eligibility(self):
        self._transfer_credit("ADVPHY", "3.00")

        enrollment = self._enrollment(
            {
                "min_credits": 3,
                "required_course_codes": ["ADVPHY"],
                "prerequisite_graph": {
                    "ADVPHY": ["CALC2"],
                },
                "corequisite_graph": {
                    "ADVPHY": ["LAB_ADVPHY"],
                },
            }
        )

        result = run_degree_audit(enrollment)

        self.assertFalse(result["is_eligible"])
        self.assertEqual(result["missing_courses"], [])
        self.assertEqual(result["missing_prerequisites"], {"ADVPHY": ["CALC2"]})
        self.assertEqual(result["missing_corequisites"], {"ADVPHY": ["LAB_ADVPHY"]})

    def test_earned_credit_dedup_for_repeated_passed_subject(self):
        subject = Subject.objects.create(
            school=self.school,
            name="CALC2",
            category=Subject.Category.GENERAL,
            credits=Decimal("3.00"),
        )
        assignment_term1 = SubjectAssignment.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term1,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=subject,
            coefficient=1,
        )
        assignment_term2 = SubjectAssignment.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term2,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=subject,
            coefficient=1,
        )

        Evaluation.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term1,
            subject_assignment=assignment_term1,
            student=self.student,
            teacher=self.teacher,
            seq1_score=Decimal("16.00"),
            seq2_score=Decimal("16.00"),
            exam_score=Decimal("16.00"),
        )
        Evaluation.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term2,
            subject_assignment=assignment_term2,
            student=self.student,
            teacher=self.teacher,
            seq1_score=Decimal("15.00"),
            seq2_score=Decimal("15.00"),
            exam_score=Decimal("15.00"),
        )

        enrollment = self._enrollment(
            {
                "min_credits": 3,
                "pass_threshold": 10,
                "required_course_codes": ["CALC2"],
            }
        )

        result = run_degree_audit(enrollment)

        self.assertTrue(result["is_eligible"])
        self.assertEqual(result["missing_courses"], [])
        self.assertEqual(result["earned_credits"], Decimal("3.00"))
        self.assertIn("CALC2", result["completed_course_codes"])

    def test_milestone_rules_block_when_committee_constraints_fail(self):
        GraduateMilestone.objects.create(
            school=self.school,
            student=self.student,
            type=GraduateMilestone.Type.DEFENSE,
            status="COMPLETED",
            is_signed_off=True,
            completion_date=date(2026, 2, 10),
            committee_member_count=2,
            external_member_count=0,
        )
        enrollment = self._enrollment(
            {
                "min_credits": 0,
                "required_course_codes": [],
                "milestones_required": ["DEFENSE"],
                "milestone_rules": {
                    "DEFENSE": {
                        "committee_min_members": 4,
                        "external_member_min": 1,
                        "require_committee_chair": True,
                    }
                },
            }
        )

        result = run_degree_audit(enrollment)

        self.assertFalse(result["is_eligible"])
        self.assertEqual(result["missing_milestones"], [])
        self.assertEqual(
            result["milestone_rule_violations"]["DEFENSE"],
            [
                "committee_member_count<4",
                "external_member_count<1",
                "committee_chair_missing",
            ],
        )

    def test_milestone_rules_block_when_embargo_exceeds_limit(self):
        GraduateMilestone.objects.create(
            school=self.school,
            student=self.student,
            type=GraduateMilestone.Type.SUBMISSION,
            status="COMPLETED",
            is_signed_off=True,
            completion_date=date(2026, 1, 10),
            embargo_until=date(2029, 2, 10),
            embargo_reason="Patent filing",
            committee_member_count=4,
            external_member_count=1,
        )
        enrollment = self._enrollment(
            {
                "min_credits": 0,
                "required_course_codes": [],
                "milestones_required": ["SUBMISSION"],
                "milestone_rules": {
                    "SUBMISSION": {
                        "require_embargo": True,
                        "max_embargo_months": 24,
                    }
                },
            }
        )

        result = run_degree_audit(enrollment)

        self.assertFalse(result["is_eligible"])
        self.assertEqual(
            result["milestone_rule_violations"]["SUBMISSION"],
            ["embargo_exceeds_24_months"],
        )
