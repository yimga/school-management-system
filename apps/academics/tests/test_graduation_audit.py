"""W22 graduation-requirements audit engine.

Every test here is MUST-FIRE: the whole module imports
``apps.academics.graduation_audit``, which does not exist before this change, so
on the pre-change tree the file fails to import (collection error = red). After
the change each test asserts a distinct behaviour of the engine:

* K-12 settings requirements — eligible / below-average / missing-subject /
  min-subjects-passed / NOT-configured (behaviour-preserving pass);
* higher-ed delegation — a student with a ``StudentDegreeEnrollment`` is routed
  through the (previously orphaned) ``run_degree_audit`` engine.

Scores are entered on the francophone /20 operational scale (the bare test
school's default ``score_scale`` is 20, and ``Evaluation.clean`` upper-bounds to
it), so a mark of 16 both saves and passes (pass mark = half the scale = 10).
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.academics.graduation_audit import (
    GraduationAuditResult,
    audit_graduation_eligibility,
    resolve_graduation_requirements,
)
from apps.academics.models import (
    AcademicYear,
    Classroom,
    DegreeProgram,
    Department,
    Specialty,
    StudentDegreeEnrollment,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.accounts.models import User
from apps.evals.models import AssessmentWeights, Evaluation
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School


class GraduationAuditFixtureMixin:
    def build(self, suffix="grad"):
        self.school = School.objects.create(
            name=f"Grad School {suffix}",
            slug=f"grad-school-{suffix}",
            subdomain=f"grad-school-{suffix}",
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
        self.department = Department.objects.create(
            school=self.school, name="General", code=f"GEN-{suffix}"
        )
        self.specialty = Specialty.objects.create(
            school=self.school,
            department=self.department,
            name="General",
            code=f"GS-{suffix}",
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=self.department,
            name="Final Year",
            code=f"FY-{suffix}",
        )
        # Real provisioning (apps/evals/grading_provisioning.py) seeds a
        # school-wide AssessmentWeights row for every school, and that row is the
        # operational score-scale source of truth: score_scale defaults to 20, and
        # the letter bands beside it (grade_b_min 16, grade_d_min 10) are /20-shaped.
        # Without it, resolve_school_score_scale falls through AssessmentWeights to
        # the locale band, which is 100 for a school carrying no country_code -- so
        # the pass mark resolved to 50 and the 16/20 marks these tests record all
        # read as failures. Create it explicitly rather than leaning on the shape
        # an unprovisioned school happens to have.
        AssessmentWeights.objects.create(
            school=self.school,
            academic_year=self.year,
            term=None,
            classroom=None,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Grace",
            last_name="Hopper",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
        )
        teacher_user = User.objects.create_user(
            username=f"grad-teacher-{suffix}",
            email=f"grad-teacher-{suffix}@example.com",
            password="pass12345",
            role=User.Role.TEACHER,
        )
        self.teacher = TeacherProfile.objects.create(
            school=self.school, user=teacher_user
        )

    def add_subject_score(self, name, seq1, seq2, exam):
        subject = Subject.objects.create(school=self.school, name=name)
        assignment = SubjectAssignment.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term1,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=subject,
            coefficient=1,
        )
        Evaluation.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term1,
            subject_assignment=assignment,
            student=self.student,
            teacher=self.teacher,
            seq1_score=Decimal(str(seq1)),
            seq2_score=Decimal(str(seq2)),
            exam_score=Decimal(str(exam)),
        )
        return subject

    def set_requirements(self, **reqs):
        settings = dict(getattr(self.school, "settings", None) or {})
        settings["graduation_requirements"] = reqs
        self.school.settings = settings
        self.school.save(update_fields=["settings"])


class ResolveGraduationRequirementsTests(GraduationAuditFixtureMixin, TestCase):
    def setUp(self):
        self.build("resolve")

    def test_absent_config_is_not_configured(self):
        reqs = resolve_graduation_requirements(self.school)
        self.assertFalse(reqs["configured"])
        self.assertIsNone(reqs["min_annual_average"])
        self.assertEqual(reqs["required_subject_codes"], [])
        self.assertIsNone(reqs["min_subjects_passed"])

    def test_typed_coercion_and_code_normalization(self):
        self.set_requirements(
            min_annual_average="12.5",
            required_subject_codes=["Mathematics", " english ", "Mathematics"],
            min_subjects_passed="3",
        )
        reqs = resolve_graduation_requirements(self.school)
        self.assertTrue(reqs["configured"])
        self.assertEqual(reqs["min_annual_average"], Decimal("12.5"))
        # normalized (strip+upper) and de-duplicated, order preserved
        self.assertEqual(reqs["required_subject_codes"], ["MATHEMATICS", "ENGLISH"])
        self.assertEqual(reqs["min_subjects_passed"], 3)


class K12GraduationAuditTests(GraduationAuditFixtureMixin, TestCase):
    def setUp(self):
        self.build("k12")

    def test_eligible_when_all_configured_requirements_met(self):
        self.add_subject_score("Mathematics", 16, 16, 16)
        self.add_subject_score("English", 16, 16, 16)
        self.set_requirements(
            min_annual_average=10,
            min_subjects_passed=2,
            required_subject_codes=["Mathematics", "English"],
        )

        result = audit_graduation_eligibility(self.student, self.year)

        self.assertIsInstance(result, GraduationAuditResult)
        self.assertTrue(result.requirements_configured)
        self.assertTrue(result.is_eligible, result.reasons)
        self.assertEqual(result.source, "k12-settings")
        self.assertEqual(result.subjects_passed, 2)
        self.assertEqual(result.missing_required_subjects, [])

    def test_ineligible_when_annual_average_below_min(self):
        self.add_subject_score("Mathematics", 16, 16, 16)
        self.set_requirements(min_annual_average=18)

        result = audit_graduation_eligibility(self.student, self.year)

        self.assertTrue(result.requirements_configured)
        self.assertFalse(result.is_eligible)
        self.assertTrue(
            any("average" in r.lower() for r in result.reasons), result.reasons
        )

    def test_missing_required_subject_is_flagged(self):
        # Mathematics present & passing; English required but never sat.
        self.add_subject_score("Mathematics", 16, 16, 16)
        self.set_requirements(required_subject_codes=["Mathematics", "English"])

        result = audit_graduation_eligibility(self.student, self.year)

        self.assertFalse(result.is_eligible)
        self.assertIn("ENGLISH", result.missing_required_subjects)
        self.assertNotIn("MATHEMATICS", result.missing_required_subjects)

    def test_min_subjects_passed_enforced(self):
        self.add_subject_score("Mathematics", 16, 16, 16)  # only one passing subject
        self.set_requirements(min_subjects_passed=2)

        result = audit_graduation_eligibility(self.student, self.year)

        self.assertFalse(result.is_eligible)
        self.assertEqual(result.subjects_passed, 1)
        self.assertTrue(
            any("subject" in r.lower() for r in result.reasons), result.reasons
        )

    def test_no_requirements_configured_is_eligible_and_marked_unconfigured(self):
        # No graduation_requirements at all → the gate must stay inert.
        result = audit_graduation_eligibility(self.student, self.year)

        self.assertFalse(result.requirements_configured)
        self.assertTrue(result.is_eligible)
        self.assertEqual(result.source, "no-requirements")


class DegreeDelegationAuditTests(GraduationAuditFixtureMixin, TestCase):
    def setUp(self):
        self.build("degree")

    def _enroll(self, requirements_json):
        program = DegreeProgram.objects.create(
            school=self.school,
            name="BSc Computer Science",
            level="BSC",
            requirements_json=requirements_json,
            is_active=True,
        )
        return StudentDegreeEnrollment.objects.create(
            student=self.student, program=program, is_active=True
        )

    def test_degree_student_delegates_and_reports_ineligible(self):
        # A credits requirement the student cannot meet (no passed evals) → the
        # orphaned degree-audit engine is what produces this answer.
        self._enroll({"min_credits": 120})

        result = audit_graduation_eligibility(self.student, self.year)

        self.assertEqual(result.source, "degree-audit")
        self.assertTrue(result.requirements_configured)
        self.assertFalse(result.is_eligible)
        self.assertTrue(result.reasons)

    def test_degree_student_delegates_and_reports_eligible(self):
        self._enroll({"min_credits": 0})

        result = audit_graduation_eligibility(self.student, self.year)

        self.assertEqual(result.source, "degree-audit")
        self.assertTrue(result.is_eligible)
