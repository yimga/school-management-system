"""Transfer Wave A — envelope domain_rows extension + real student extraction.

Locks: (1) the checksummed multi-domain payload (omitted-when-empty so legacy
single-record envelopes keep verifying), (2) ``envelope_from_dict`` wire
round-trip, (3) the model-reading student envelope builder (design §5 step 3 —
before this, nothing in-tree ever read a student's actual rows into an
envelope), and (4) canonical-domain validation of the payload.
"""

from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.academics.models import (
    AcademicYear,
    Attendance,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.evals.models import Evaluation
from apps.interop.student_transfer_export import (
    build_student_transfer_envelope,
    extract_student_domain_rows,
    student_external_ref,
)
from apps.interop.transfer_apply import (
    TransferApplyError,
    verify_envelope_checksum,
)
from apps.interop.transfer_envelope import (
    TransferEnvelopeError,
    build_student_envelope,
    envelope_from_dict,
)
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
from apps.schools.models import School

User = get_user_model()


class DomainRowsEnvelopeTests(TestCase):
    def _rows(self):
        return {
            "students": [
                {"external_id": "s-1", "first_name": "Env", "last_name": "Elope"}
            ]
        }

    def test_domain_rows_are_checksummed_and_roundtrip(self):
        envelope = build_student_envelope(
            source_tenant_id="school-a",
            target_tenant_id="school-b",
            canonical_data={},
            domain_rows=self._rows(),
        )
        verify_envelope_checksum(envelope)
        self.assertIn("domain_rows", envelope.to_dict())

        rehydrated = envelope_from_dict(envelope.to_dict())
        verify_envelope_checksum(rehydrated)
        self.assertEqual(rehydrated.domain_rows, envelope.domain_rows)

    def test_tampered_domain_rows_fail_verification(self):
        envelope = build_student_envelope(
            source_tenant_id="school-a",
            target_tenant_id="school-b",
            canonical_data={},
            domain_rows=self._rows(),
        )
        envelope.domain_rows["students"][0]["first_name"] = "Tampered"
        with self.assertRaises(TransferApplyError):
            verify_envelope_checksum(envelope)

    def test_empty_domain_rows_keep_v1_body_shape(self):
        envelope = build_student_envelope(
            source_tenant_id="school-a",
            target_tenant_id="school-b",
            canonical_data={},
        )
        self.assertNotIn("domain_rows", envelope.to_dict())
        verify_envelope_checksum(envelope)

    def test_unknown_domain_rejected(self):
        with self.assertRaises(TransferEnvelopeError):
            build_student_envelope(
                source_tenant_id="school-a",
                target_tenant_id="school-b",
                canonical_data={},
                domain_rows={"not_a_domain": [{"x": "1"}]},
            )

    def test_non_canonical_row_key_rejected(self):
        with self.assertRaises(TransferEnvelopeError):
            build_student_envelope(
                source_tenant_id="school-a",
                target_tenant_id="school-b",
                canonical_data={},
                domain_rows={"students": [{"external_id": "s", "ssn": "x"}]},
            )


class StudentExtractionTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Extract Source", slug="extract-src", subdomain="extract-src"
        )
        self.target = School.objects.create(
            name="Extract Target", slug="extract-tgt", subdomain="extract-tgt"
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
            is_active=True,
        )
        self.term = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name="FIRST",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 5),
            position=1,
            is_active=True,
        )
        department = Department.objects.create(
            school=self.school, name="Science", code="SCI-TX"
        )
        specialty = Specialty.objects.create(
            school=self.school, department=department, name="General", code="GEN-TX"
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=department,
            name="Form 2B",
            code="F2B-TX",
        )
        subject = Subject.objects.create(school=self.school, name="Physics")
        assignment = SubjectAssignment.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=specialty,
            subject=subject,
            coefficient=3,
        )
        teacher_user = User.objects.create_user(
            username="tx_teacher", password="pass123", role=User.Role.TEACHER
        )
        teacher = TeacherProfile.objects.create(
            user=teacher_user, school=self.school
        )
        self.profile = StudentProfile.objects.create(
            school=self.school,
            first_name="Trans",
            last_name="Feree",
            student_code="TX-001",
            admission_number="ADM-TX-001",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=specialty,
            joined_date=date(2025, 9, 2),
            is_active=True,
        )
        guardian_user = User.objects.create_user(
            username="tx_guardian",
            password="pass123",
            first_name="Guard",
            last_name="Ian",
        )
        StudentGuardian.objects.create(
            guardian_user=guardian_user,
            student=self.profile,
            phone="+237600000001",
        )
        Attendance.objects.create(
            school=self.school,
            student=self.profile,
            classroom=self.classroom,
            date=date(2025, 10, 6),
        )
        Evaluation.objects.create(
            student=self.profile,
            subject_assignment=assignment,
            teacher=teacher,
            academic_year=self.year,
            term=self.term,
            seq1_score=12,
            seq2_score=15,
        )

    def test_external_ref_prefers_admission_number(self):
        self.assertEqual(student_external_ref(self.profile), "ADM-TX-001")

    def test_extraction_covers_default_domains(self):
        rows = extract_student_domain_rows(self.profile)
        self.assertEqual(
            set(rows.keys()),
            {"students", "guardians", "enrollment", "attendance", "grades"},
        )
        student_row = rows["students"][0]
        self.assertEqual(student_row["external_id"], "ADM-TX-001")
        self.assertEqual(student_row["first_name"], "Trans")
        self.assertEqual(rows["guardians"][0]["student_external_id"], "ADM-TX-001")
        self.assertEqual(rows["guardians"][0]["first_name"], "Guard")
        self.assertEqual(rows["attendance"][0]["date"], "2025-10-06")
        self.assertEqual(rows["grades"][0]["subject_code"], "Physics")
        self.assertEqual(rows["enrollment"][0]["grade_level"], "Form 2B")

    def test_finance_not_in_default_domains(self):
        rows = extract_student_domain_rows(self.profile)
        self.assertNotIn("finance", rows)

    def test_sealed_envelope_verifies_and_targets_school(self):
        envelope = build_student_transfer_envelope(
            self.profile, target_school=self.target, actor_id="op-1"
        )
        verify_envelope_checksum(envelope)
        self.assertEqual(envelope.envelope_kind, "student")
        self.assertIn("students", envelope.domain_rows)
