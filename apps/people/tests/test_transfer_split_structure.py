"""SPLIT into an EMPTY target provisions the academic scaffold + lands LIVE grades.

This is the exit criterion for closing "Gap 2" (the split-into-empty-tenant
gradebook): b69fb559d made grades RESOLVE structure but never fabricate it, so a
split into a greenfield tenant quarantined 100% of grades (archival only). The
StructureLander (wave 0, SPLIT-only) now provisions AcademicYear / Term /
Department / Classroom / Specialty / Subject / SubjectAssignment + a
target-scoped teacher, so enrollment (wave 2) places the student and grades
(wave 3) pass Evaluation.clean parity and land as LIVE Evaluations.

Guardrails proven here: target codes are freshly minted (never the source's,
which are globally unique); the provisioned teacher is a NEW target-scoped User
with role TEACHER and an UNUSABLE password; and provisioning is idempotent
across a cohort (a second student reuses the same year/class/subject/assignment,
never duplicates).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

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
from apps.people.models import (
    StudentGuardian,
    StudentProfile,
    TeacherProfile,
)
from apps.people.models_transfer import TransferCase
from apps.people.models_transfer_consent import TransferConsent
from apps.people.transfer_service import run_transfer_case_await_apply
from apps.schools.models import School

User = get_user_model()

_ENV = {"MIGRATION_CLOUD__MIGRATION_CLOUD__ORCHESTRATOR__WORKER_COUNT": "1"}
# A split carries the structure domain FIRST, then the normal student domains.
_SPLIT_DOMAINS = [
    "structure",
    "students",
    "guardians",
    "enrollment",
    "attendance",
    "grades",
    "transcripts",
]


@patch.dict("os.environ", _ENV)
class SplitStructureProvisioningTests(TestCase):
    def setUp(self):
        # SOURCE school with a full academic graph.
        self.source = School.objects.create(
            name="Split Src", slug="split-src", subdomain="split-src"
        )
        # TARGET school is EMPTY — no year/term/subject/classroom/specialty.
        self.target = School.objects.create(
            name="Split Tgt", slug="split-tgt", subdomain="split-tgt"
        )
        self.year = AcademicYear.objects.create(
            school=self.source, name="2025/2026",
            start_date=date(2025, 9, 1), end_date=date(2026, 7, 1), is_active=True,
        )
        self.department = Department.objects.create(
            school=self.source, name="Science", code="SCI-SPLIT-SRC"
        )
        self.classroom = Classroom.objects.create(
            school=self.source, academic_year=self.year, department=self.department,
            name="Form 4A", code="F4A-SPLIT-SRC",
        )
        self.specialty = Specialty.objects.create(
            school=self.source, department=self.department, name="General",
            code="GEN-SPLIT-SRC",
        )
        self.term = Term.objects.create(
            school=self.source, academic_year=self.year, name="FIRST",
            start_date=date(2025, 9, 1), end_date=date(2025, 12, 15), position=1,
        )
        self.subject = Subject.objects.create(school=self.source, name="Mathematics")
        self.teacher_user = User.objects.create_user(
            username="split_src_teacher", password="pass123",
            first_name="Ada", last_name="Lovelace",
        )
        self.source_teacher = TeacherProfile.objects.create(
            user=self.teacher_user, school=self.source
        )
        self.assignment = SubjectAssignment.objects.create(
            school=self.source, academic_year=self.year, term=self.term,
            classroom=self.classroom, specialty=self.specialty, subject=self.subject,
            coefficient=Decimal("2"),
        )
        self.assignment.teachers.add(self.teacher_user)
        self.operator = User.objects.create_user(
            username="split_operator", password="pass123", is_staff=True
        )

    # ── helpers ─────────────────────────────────────────────────────

    def _make_source_student(self, code: str) -> StudentProfile:
        user = User.objects.create_user(username=f"stu_{code}", password="pass123")
        profile = StudentProfile.objects.create(
            school=self.source, user=user, first_name="Split", last_name=code,
            student_code=code, admission_number=f"ADM-{code}",
            academic_year=self.year, classroom=self.classroom, specialty=self.specialty,
            joined_date=date(2025, 9, 2),
        )
        guardian_user = User.objects.create_user(
            username=f"guard_{code}", password="pass123",
            first_name="Grace", last_name="Hopper",
        )
        StudentGuardian.objects.create(
            guardian_user=guardian_user, student=profile, phone="+237600000001",
        )
        Evaluation.objects.create(
            school=self.source, academic_year=self.year, term=self.term,
            subject_assignment=self.assignment, student=profile,
            teacher=self.source_teacher,
            seq1_score=Decimal("16.00"), seq2_score=Decimal("17.50"),
        )
        return profile

    def _run_split(self, profile: StudentProfile):
        case = TransferCase.objects.create(
            source_school=self.source, target_school=self.target,
            source_profile_pk=str(profile.pk), domains=_SPLIT_DOMAINS,
            created_by=self.operator,
        )
        case.advance(TransferCase.Status.CONSENT_PENDING)
        _raw, consent = TransferConsent.mint(
            case=case, guardian_name="Grace Hopper",
            guardian_email="guardian@example.com",
            consent_text_version="v1", consent_text="consent body v1",
        )
        consent.consent()
        case.refresh_from_db()
        self.assertEqual(case.status, TransferCase.Status.APPROVED)
        summary = run_transfer_case_await_apply(case, actor=self.operator)
        case.refresh_from_db()
        return case, summary

    # ── tests ───────────────────────────────────────────────────────

    def test_split_into_empty_target_lands_live_grades(self):
        s1 = self._make_source_student("RB-001")
        case, summary = self._run_split(s1)

        # Nothing quarantined — the scaffold made enrollment + grades resolve.
        self.assertEqual(summary["apply"]["total_quarantined"], 0)
        self.assertIn(
            case.status,
            (TransferCase.Status.APPLIED, TransferCase.Status.RECONCILED),
        )

        # Structure was provisioned at the (previously empty) target.
        t_year = AcademicYear.objects.get(school=self.target, name="2025/2026")
        t_class = Classroom.objects.get(school=self.target, name="Form 4A")
        t_term = Term.objects.get(school=self.target, academic_year=t_year, name="FIRST")
        t_spec = Specialty.objects.get(school=self.target, name="General")
        t_subject = Subject.objects.get(school=self.target, name="Mathematics")
        t_assign = SubjectAssignment.objects.get(
            school=self.target, academic_year=t_year, term=t_term,
            classroom=t_class, specialty=t_spec, subject=t_subject,
        )

        # GUARDRAIL: globally-unique codes were freshly minted, NOT the source's
        # (reusing them would collide or resolve the source school's row).
        self.assertNotEqual(t_class.code, self.classroom.code)
        self.assertNotEqual(t_spec.code, self.specialty.code)
        self.assertNotEqual(
            Department.objects.get(school=self.target).code, self.department.code
        )

        # GUARDRAIL: the provisioned teacher is a NEW target-scoped User with
        # role TEACHER and an UNUSABLE password (no credential minted), with its
        # own TeacherProfile — never the source teacher's (OneToOne) profile.
        t_teacher_user = t_assign.teachers.first()
        self.assertIsNotNone(t_teacher_user)
        self.assertNotEqual(t_teacher_user.pk, self.teacher_user.pk)
        self.assertFalse(t_teacher_user.has_usable_password())
        self.assertEqual(t_teacher_user.role, User.Role.TEACHER)
        self.assertTrue(
            TeacherProfile.objects.filter(
                user=t_teacher_user, school=self.target
            ).exists()
        )

        # The student is placed at the target and the grade is LIVE, bound to
        # the target's own assignment, with faithful component scores.
        t_student = StudentProfile.objects.get(
            school=self.target, admission_number="ADM-RB-001"
        )
        self.assertEqual(t_student.classroom_id, t_class.pk)
        self.assertEqual(t_student.academic_year_id, t_year.pk)
        self.assertEqual(t_student.specialty_id, t_spec.pk)
        ev = Evaluation.objects.get(school=self.target, student=t_student)
        self.assertEqual(ev.subject_assignment_id, t_assign.pk)
        self.assertEqual(ev.term_id, t_term.pk)
        self.assertEqual(ev.seq1_score, Decimal("16.00"))
        self.assertEqual(ev.seq2_score, Decimal("17.50"))

    def test_structure_provisioning_is_idempotent_across_a_cohort(self):
        s1 = self._make_source_student("RB-001")
        _c1, sum1 = self._run_split(s1)
        s2 = self._make_source_student("RB-002")
        _c2, sum2 = self._run_split(s2)

        self.assertEqual(sum1["apply"]["total_quarantined"], 0)
        self.assertEqual(sum2["apply"]["total_quarantined"], 0)

        # The scaffold is created ONCE and reused — no duplicate structure.
        self.assertEqual(
            AcademicYear.objects.filter(school=self.target, name="2025/2026").count(), 1
        )
        self.assertEqual(
            Classroom.objects.filter(school=self.target, name="Form 4A").count(), 1
        )
        self.assertEqual(
            Subject.objects.filter(school=self.target, name="Mathematics").count(), 1
        )
        self.assertEqual(
            SubjectAssignment.objects.filter(school=self.target).count(), 1
        )
        # Both students landed LIVE grades bound to the same reused assignment.
        assign = SubjectAssignment.objects.get(school=self.target)
        evs = Evaluation.objects.filter(school=self.target)
        self.assertEqual(evs.count(), 2)
        self.assertTrue(all(e.subject_assignment_id == assign.pk for e in evs))
