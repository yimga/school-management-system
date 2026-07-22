"""Transfer Wave B — REAL apply end-to-end (the go-live exit criterion).

A consented, approved case moves an actual student: new StudentProfile at the
target school (same external ref, DIFFERENT row — proving the school-scoped
lander upserts), attendance history lands school-bound at the target, the
guardian's PLATFORM account is re-linked at the target (portal access
survives the move), grades land as live Evaluations bound to the TARGET's
term/assignment/teacher graph, the archival transcript record arrives with
source provenance, the passport GUID links both profiles, the source profile
retires as TRANSFERRED, and the offline-pending guard refuses to move a
student whose device still holds undrained writes.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

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
from apps.people.models import (
    StudentGuardian,
    StudentProfile,
    TeacherProfile,
    TranscriptVaultItem,
)
from apps.people.models_transfer import TransferCase
from apps.people.models_transfer_consent import TransferConsent
from apps.people.transfer_service import (
    TransferBlockedError,
    offline_transfer_blockers,
    run_transfer_case,
)
from apps.schools.models import School

User = get_user_model()

_ENV = {"MIGRATION_CLOUD__MIGRATION_CLOUD__ORCHESTRATOR__WORKER_COUNT": "1"}
_DOMAINS = [
    "students",
    "guardians",
    "enrollment",
    "attendance",
    "grades",
    "transcripts",
]


@patch.dict("os.environ", _ENV)
class TransferRealApplyTests(TestCase):
    def setUp(self):
        self.source = School.objects.create(
            name="Real Src", slug="real-src", subdomain="real-src"
        )
        self.target = School.objects.create(
            name="Real Tgt", slug="real-tgt", subdomain="real-tgt"
        )
        year = AcademicYear.objects.create(
            school=self.source,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
        )
        department = Department.objects.create(
            school=self.source, name="Science", code="SCI-RB"
        )
        self.classroom = Classroom.objects.create(
            school=self.source,
            academic_year=year,
            department=department,
            name="Form 4A",
            code="F4A-RB",
        )
        self.student_user = User.objects.create_user(
            username="rb_student", password="pass123"
        )
        self.profile = StudentProfile.objects.create(
            school=self.source,
            user=self.student_user,
            first_name="Real",
            last_name="Mover",
            student_code="RB-001",
            admission_number="ADM-RB-001",
            academic_year=year,
            classroom=self.classroom,
            joined_date=date(2025, 9, 2),
        )
        self.guardian_user = User.objects.create_user(
            username="rb_guardian",
            password="pass123",
            first_name="Guard",
            last_name="Ian",
        )
        StudentGuardian.objects.create(
            guardian_user=self.guardian_user,
            student=self.profile,
            phone="+237600000003",
            # Non-default consent/visibility so the apply proves FIDELITY, not
            # merely that a link exists: opted OUT of email (must not be
            # re-subscribed), results access RESTRICTED (must not be
            # regranted), finance view GRANTED (must not be dropped), plus a
            # non-default contact preference + whatsapp number. Every value
            # here differs from the StudentGuardian field default.
            receives_email=False,
            receives_sms=True,
            receives_whatsapp=True,
            can_view_results=False,
            can_view_finance=True,
            preferred_contact=StudentGuardian.PreferredContact.SMS,
            whatsapp_number="+237600000009",
        )
        Attendance.objects.create(
            school=self.source,
            student=self.profile,
            classroom=self.classroom,
            date=date(2025, 10, 8),
        )
        # Source grading structure + one real evaluation to carry across.
        source_term = Term.objects.create(
            school=self.source,
            academic_year=year,
            name="FIRST",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
        )
        source_specialty = Specialty.objects.create(
            school=self.source, department=department, name="General", code="GEN-RB"
        )
        # Evaluation.clean parity: the student's specialty must match the
        # assignment's — and the export carries it so the target re-places it.
        self.profile.specialty = source_specialty
        self.profile.save(update_fields=["specialty"])
        source_subject = Subject.objects.create(
            school=self.source, name="Mathematics"
        )
        source_teacher_user = User.objects.create_user(
            username="rb_src_teacher", password="pass123"
        )
        source_teacher = TeacherProfile.objects.create(
            user=source_teacher_user, school=self.source
        )
        source_assignment = SubjectAssignment.objects.create(
            school=self.source,
            academic_year=year,
            term=source_term,
            classroom=self.classroom,
            specialty=source_specialty,
            subject=source_subject,
        )
        Evaluation.objects.create(
            school=self.source,
            academic_year=year,
            term=source_term,
            subject_assignment=source_assignment,
            student=self.profile,
            teacher=source_teacher,
            seq1_score=Decimal("14.50"),
            seq2_score=Decimal("15.00"),
        )
        # The target school has matching structures (the branch-campus
        # scenario) — enrollment placement resolves the classroom by name,
        # which lets attendance history bind to the TARGET's classroom.
        target_year = AcademicYear.objects.create(
            school=self.target,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
        )
        target_department = Department.objects.create(
            school=self.target, name="Science", code="SCI-RT"
        )
        self.target_classroom = Classroom.objects.create(
            school=self.target,
            academic_year=target_year,
            department=target_department,
            name="Form 4A",
            code="F4A-RT",
        )
        # Matching grading structure at the target (branch-campus scenario):
        # same year/term/subject labels, its OWN assignment slot + teacher —
        # exactly what the grades lander's FK resolution must bind to.
        self.target_term = Term.objects.create(
            school=self.target,
            academic_year=target_year,
            name="FIRST",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
        )
        target_specialty = Specialty.objects.create(
            school=self.target,
            department=target_department,
            name="General",
            code="GEN-RT",
        )
        target_subject = Subject.objects.create(
            school=self.target, name="Mathematics"
        )
        self.target_teacher_user = User.objects.create_user(
            username="rb_tgt_teacher", password="pass123"
        )
        self.target_teacher = TeacherProfile.objects.create(
            user=self.target_teacher_user, school=self.target
        )
        self.target_assignment = SubjectAssignment.objects.create(
            school=self.target,
            academic_year=target_year,
            term=self.target_term,
            classroom=self.target_classroom,
            specialty=target_specialty,
            subject=target_subject,
        )
        self.target_assignment.teachers.add(self.target_teacher_user)
        self.operator = User.objects.create_user(
            username="rb_operator", password="pass123", is_staff=True
        )
        self.case = TransferCase.objects.create(
            source_school=self.source,
            target_school=self.target,
            source_profile_pk=str(self.profile.pk),
            domains=_DOMAINS,
            created_by=self.operator,
        )

    def _approve_via_consent(self):
        self.case.advance(TransferCase.Status.CONSENT_PENDING)
        _raw, consent = TransferConsent.mint(
            case=self.case,
            guardian_name="Guard Ian",
            guardian_email="guardian@example.com",
            consent_text_version="v1",
            consent_text="consent body v1",
        )
        consent.consent()
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, TransferCase.Status.APPROVED)

    def test_unapproved_case_refused(self):
        with self.assertRaises(TransferBlockedError):
            run_transfer_case(self.case, actor=self.operator, off_http=False)

    def test_real_apply_end_to_end(self):
        self._approve_via_consent()
        summary = run_transfer_case(self.case, actor=self.operator, off_http=False)
        self.case.refresh_from_db()

        # Case landed in a terminal-success state with the bundle recorded.
        self.assertIn(
            self.case.status,
            (TransferCase.Status.APPLIED, TransferCase.Status.RECONCILED),
        )
        self.assertIsNotNone(self.case.target_bundle_id)

        # A NEW profile exists at the target with the same external ref.
        target_profile = StudentProfile.objects.get(
            school=self.target, admission_number="ADM-RB-001"
        )
        self.assertNotEqual(str(target_profile.pk), str(self.profile.pk))
        self.assertEqual(target_profile.first_name, "Real")

        # Enrollment placement resolved the target's own classroom (by name),
        # and attendance history landed bound to the TARGET's structures —
        # never the source school's classroom row.
        self.assertEqual(target_profile.classroom_id, self.target_classroom.pk)
        attendance = Attendance.objects.get(school=self.target, student=target_profile)
        self.assertEqual(attendance.classroom_id, self.target_classroom.pk)

        # Guardian re-link: the SAME platform account is linked at the
        # target (carried as guardian_user_ref), so the parent's portal
        # access — scoped via StudentGuardian — survives the move.
        target_link = StudentGuardian.objects.get(student=target_profile)
        self.assertEqual(target_link.guardian_user_id, self.guardian_user.pk)

        # Consent / visibility / contact-preference fidelity: the target link
        # carries the SOURCE values, not the model defaults. Without the carry
        # each of these would land at its default (receives_email True,
        # receives_sms/whatsapp False, can_view_results True, can_view_finance
        # False, preferred_contact EMAIL) — silently re-subscribing an
        # opted-out parent, regranting a restricted guardian results access,
        # and dropping granted finance visibility.
        self.assertFalse(target_link.receives_email)
        self.assertTrue(target_link.receives_sms)
        self.assertTrue(target_link.receives_whatsapp)
        self.assertFalse(target_link.can_view_results)
        self.assertTrue(target_link.can_view_finance)
        self.assertEqual(
            target_link.preferred_contact,
            StudentGuardian.PreferredContact.SMS,
        )
        self.assertEqual(target_link.whatsapp_number, "+237600000009")

        # Grades: the FK graph resolved at the TARGET — a live Evaluation
        # bound to the target's own term/assignment/teacher, with faithful
        # component scores (never a re-derived aggregate).
        evaluation = Evaluation.objects.get(school=self.target, student=target_profile)
        self.assertEqual(evaluation.term_id, self.target_term.pk)
        self.assertEqual(evaluation.subject_assignment_id, self.target_assignment.pk)
        self.assertEqual(evaluation.teacher_id, self.target_teacher.pk)
        self.assertEqual(evaluation.seq1_score, Decimal("14.50"))
        self.assertEqual(evaluation.seq2_score, Decimal("15.00"))

        # Archival transcript record arrived with SOURCE provenance, hanging
        # off the same passport GUID the transfer links below.
        vault = TranscriptVaultItem.objects.get(student_profile=target_profile)
        self.assertEqual(vault.issuing_school_id, self.source.pk)
        self.assertEqual(vault.artifact_type, "transfer_grade_record")
        self.assertIn("Mathematics", vault.artifact_ref)

        # The full default domain set lands CLEAN — nothing quarantined.
        self.assertEqual(summary["apply"]["total_quarantined"], 0)

        # Passport GUID links both profiles; source retired honestly. The
        # vault item's passport converged on the SAME GUID (no fork).
        self.profile.refresh_from_db()
        self.assertIsNotNone(self.profile.passport_id)
        self.assertEqual(target_profile.passport_id, self.profile.passport_id)
        self.assertEqual(vault.passport_id, self.profile.passport_id)
        self.assertEqual(self.profile.status, StudentProfile.Status.TRANSFERRED)
        self.assertFalse(self.profile.is_active)

        # The pipeline's own audit trail knows the mapping.
        from apps.migration_cloud.models import MigrationIdMapping

        self.assertTrue(
            MigrationIdMapping.objects.filter(
                school=self.target, legacy_id="ADM-RB-001", domain="students"
            ).exists()
        )

    def test_rerun_of_finished_case_refused(self):
        self._approve_via_consent()
        run_transfer_case(self.case, actor=self.operator, off_http=False)
        self.case.refresh_from_db()
        with self.assertRaises(TransferBlockedError):
            run_transfer_case(self.case, actor=self.operator, off_http=False)

    def test_offline_pending_guard_blocks(self):
        from apps.platform_runtime.models import OfflineAction

        action = OfflineAction.objects.create(
            user=self.student_user,
            school=self.source,
            action_type=OfflineAction.ActionType.HOMEWORK_SUBMISSION,
            payload={},
        )
        self.assertTrue(offline_transfer_blockers(self.profile))
        self._approve_via_consent()
        with self.assertRaises(TransferBlockedError):
            run_transfer_case(self.case, actor=self.operator, off_http=False)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, TransferCase.Status.APPROVED)

        # Drained queue unblocks the same case.
        action.status = OfflineAction.Status.SYNCED
        action.save(update_fields=["status"])
        self.assertEqual(offline_transfer_blockers(self.profile), [])
        summary = run_transfer_case(self.case, actor=self.operator, off_http=False)
        self.assertIn("bundle_id", summary)


class TransferRunnerRegistrationTests(TestCase):
    def test_get_runner_dispatches_student_transfer(self):
        from apps.orchestration.models import OrchestrationRun, ProcessDefinition
        from apps.orchestration.runners import StudentTransferRunner, get_runner

        definition = ProcessDefinition.objects.create(
            code="student_transfer", name="Student transfer"
        )
        run = OrchestrationRun.objects.create(
            definition=definition, input_payload={"case_id": "missing"}
        )
        runner = get_runner(run)
        self.assertIsInstance(runner, StudentTransferRunner)
        outcome = runner.run_step()
        self.assertEqual(outcome.get("error"), "case_not_found")
