"""Transfer Wave B — REAL apply end-to-end (the go-live exit criterion).

A consented, approved case moves an actual student: new StudentProfile at the
target school (same external ref, DIFFERENT row — proving the school-scoped
lander upserts), attendance history lands school-bound at the target,
unresolvable guardian rows quarantine VISIBLY (never silently), the passport
GUID links both profiles, the source profile retires as TRANSFERRED, and the
offline-pending guard refuses to move a student whose device still holds
undrained writes.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.academics.models import AcademicYear, Attendance, Classroom, Department
from apps.people.models import StudentGuardian, StudentProfile
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
_DOMAINS = ["students", "guardians", "enrollment", "attendance"]


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
        guardian_user = User.objects.create_user(
            username="rb_guardian",
            password="pass123",
            first_name="Guard",
            last_name="Ian",
        )
        StudentGuardian.objects.create(
            guardian_user=guardian_user,
            student=self.profile,
            phone="+237600000003",
        )
        Attendance.objects.create(
            school=self.source,
            student=self.profile,
            classroom=self.classroom,
            date=date(2025, 10, 8),
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
            run_transfer_case(self.case, actor=self.operator)

    def test_real_apply_end_to_end(self):
        self._approve_via_consent()
        summary = run_transfer_case(self.case, actor=self.operator)
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

        # Guardian rows cannot resolve a linkable user at the target yet —
        # they must quarantine VISIBLY, never land silently broken.
        self.assertFalse(
            StudentGuardian.objects.filter(student=target_profile).exists()
        )
        self.assertGreaterEqual(summary["apply"]["total_quarantined"], 1)

        # Passport GUID links both profiles; source retired honestly.
        self.profile.refresh_from_db()
        self.assertIsNotNone(self.profile.passport_id)
        self.assertEqual(target_profile.passport_id, self.profile.passport_id)
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
        run_transfer_case(self.case, actor=self.operator)
        self.case.refresh_from_db()
        with self.assertRaises(TransferBlockedError):
            run_transfer_case(self.case, actor=self.operator)

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
            run_transfer_case(self.case, actor=self.operator)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, TransferCase.Status.APPROVED)

        # Drained queue unblocks the same case.
        action.status = OfflineAction.Status.SYNCED
        action.save(update_fields=["status"])
        self.assertEqual(offline_transfer_blockers(self.profile), [])
        summary = run_transfer_case(self.case, actor=self.operator)
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
