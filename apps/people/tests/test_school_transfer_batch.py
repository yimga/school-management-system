"""Wave D — school merge/split batch e2e (design §10 exit criterion).

A dual-approved merge batch fans out REAL transfer cases and drives them
through the unmodified Wave B engine: both seeded students land at the target
school, the batch rolls up to COMPLETED, and the source hands off to the
EXISTING wind-down (portability export + deactivate — never purge). Failure
isolation is proven with the offline-pending guard: one blocked student
exhausts the attempt ledger while the other still moves, and the batch lands
COMPLETED_WITH_ISSUES instead of stranding.
"""

from __future__ import annotations

import os
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academics.models import AcademicYear, Classroom, Department
from apps.people.models import StudentProfile
from apps.people.models_school_batch import BatchStateError, SchoolTransferBatch
from apps.people.models_transfer import TransferCase
from apps.people.school_batch_service import (
    MAX_CASE_ATTEMPTS,
    BatchBlockedError,
    advance_batch,
    advance_running_batches,
    cancel_batch,
    preview_batch,
    record_batch_approval,
    start_batch,
    wind_down_source,
)
from apps.schools.models import School

User = get_user_model()

_ENV = {"MIGRATION_CLOUD__MIGRATION_CLOUD__ORCHESTRATOR__WORKER_COUNT": "1"}


def _make_campus(name: str, slug: str, dept_code: str, class_code: str):
    school = School.objects.create(name=name, slug=slug, subdomain=slug)
    year = AcademicYear.objects.create(
        school=school,
        name="2025/2026",
        start_date=date(2025, 9, 1),
        end_date=date(2026, 7, 1),
    )
    department = Department.objects.create(
        school=school, name="Science", code=dept_code
    )
    classroom = Classroom.objects.create(
        school=school,
        academic_year=year,
        department=department,
        name="Form 5A",
        code=class_code,
    )
    return school, year, classroom


@patch.dict("os.environ", _ENV)
class SchoolBatchEngineTests(TestCase):
    def setUp(self):
        self.source, self.source_year, self.source_classroom = _make_campus(
            "Batch Src", "batch-src", "SCI-BS", "F5A-BS"
        )
        # Matching structures at the target (branch-campus scenario) so
        # enrollment placement resolves the classroom by name.
        self.target, _ty, self.target_classroom = _make_campus(
            "Batch Tgt", "batch-tgt", "SCI-BT", "F5A-BT"
        )
        self.students = []
        for i in (1, 2):
            user = User.objects.create_user(
                username=f"sb_student_{i}", password="pass123"
            )
            self.students.append(
                StudentProfile.objects.create(
                    school=self.source,
                    user=user,
                    first_name=f"Move{i}",
                    last_name="Batcher",
                    student_code=f"SB-00{i}",
                    admission_number=f"ADM-SB-00{i}",
                    academic_year=self.source_year,
                    classroom=self.source_classroom,
                    joined_date=date(2025, 9, 2),
                )
            )
        # Ineligible rows the preview must EXCLUDE: an inactive student and an
        # already-transferred one.
        StudentProfile.objects.create(
            school=self.source,
            first_name="Gone",
            last_name="Inactive",
            student_code="SB-INACT",
            is_active=False,
        )
        StudentProfile.objects.create(
            school=self.source,
            first_name="Al",
            last_name="Ready",
            student_code="SB-MOVED",
            status=StudentProfile.Status.TRANSFERRED,
        )
        self.op1 = User.objects.create_user(
            username="sb_op1", password="pass123", is_staff=True
        )
        self.op2 = User.objects.create_user(
            username="sb_op2", password="pass123", is_staff=True
        )
        self.batch = SchoolTransferBatch.objects.create(
            kind=SchoolTransferBatch.Kind.MERGE,
            source_school=self.source,
            target_school=self.target,
            consent_basis="Governing-board merger resolution 2026-07",
            created_by=self.op1,
        )

    def _approve(self, batch=None):
        batch = batch or self.batch
        preview_batch(batch)
        record_batch_approval(batch, self.op1, batch.source_school.slug)
        record_batch_approval(batch, self.op2, batch.source_school.slug)
        self.assertEqual(batch.status, SchoolTransferBatch.Status.APPROVED)

    def test_preview_counts_only_eligible_students(self):
        preview = preview_batch(self.batch)
        self.assertEqual(preview["to_move"], 2)
        self.assertEqual(preview["eligible"], 2)
        self.assertEqual(self.batch.status, SchoolTransferBatch.Status.PREVIEWED)

    def test_dual_approval_requires_distinct_operators(self):
        preview_batch(self.batch)
        outcome = record_batch_approval(self.batch, self.op1, "batch-src")
        self.assertFalse(outcome["approved"])
        with self.assertRaises(BatchBlockedError):
            record_batch_approval(self.batch, self.op1, "batch-src")
        outcome = record_batch_approval(self.batch, self.op2, "batch-src")
        self.assertTrue(outcome["approved"])
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, SchoolTransferBatch.Status.APPROVED)

    def test_wrong_confirm_slug_refused(self):
        preview_batch(self.batch)
        with self.assertRaises(BatchBlockedError):
            record_batch_approval(self.batch, self.op1, "wrong-slug")

    def test_institutional_mode_requires_consent_basis(self):
        batch = SchoolTransferBatch.objects.create(
            kind=SchoolTransferBatch.Kind.MERGE,
            source_school=self.source,
            target_school=self.target,
            consent_basis="",
        )
        preview_batch(batch)
        with self.assertRaises(BatchBlockedError):
            record_batch_approval(batch, self.op1, "batch-src")

    def test_illegal_batch_transition_raises(self):
        with self.assertRaises(BatchStateError):
            self.batch.advance(SchoolTransferBatch.Status.RUNNING)

    def test_full_merge_batch_end_to_end_with_wind_down(self):
        self._approve()
        outcome = start_batch(self.batch, actor=self.op1)
        self.assertEqual(outcome["cases_created"], 2)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, SchoolTransferBatch.Status.RUNNING)

        # Institutional consent journaled the basis on every case.
        cases = list(TransferCase.objects.filter(batch=self.batch))
        self.assertEqual(len(cases), 2)
        for case in cases:
            self.assertEqual(case.status, TransferCase.Status.APPROVED)
            self.assertEqual(case.consent_reference, f"batch:{self.batch.pk}")
            notes = " ".join(e.get("note", "") for e in case.history)
            self.assertIn("institutional authority", notes)

        summary = advance_batch(self.batch, actor=self.op1, max_cases=10)
        self.assertEqual(summary["ran"], 2)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, SchoolTransferBatch.Status.COMPLETED)
        self.assertIsNotNone(self.batch.completed_at)

        # Both students really moved: retired at source, present at target.
        for i, profile in enumerate(self.students, start=1):
            profile.refresh_from_db()
            self.assertEqual(profile.status, StudentProfile.Status.TRANSFERRED)
            self.assertFalse(profile.is_active)
            target_profile = StudentProfile.objects.get(
                school=self.target, admission_number=f"ADM-SB-00{i}"
            )
            self.assertEqual(
                target_profile.classroom_id, self.target_classroom.pk
            )

        # Wind-down handoff: export + deactivate, receipt on the batch.
        receipt = wind_down_source(
            self.batch, actor=self.op1, confirm_slug="batch-src"
        )
        self.assertTrue(receipt["deactivated"])
        self.assertTrue(os.path.exists(receipt["export_zip"]))
        self.source.refresh_from_db()
        self.assertFalse(self.source.is_active)

        # A second wind-down refuses — the handoff is once per batch.
        with self.assertRaises(BatchBlockedError):
            wind_down_source(self.batch, actor=self.op1, confirm_slug="batch-src")

    def test_failure_isolation_one_blocked_student_never_strands_the_batch(self):
        from apps.platform_runtime.models import OfflineAction

        OfflineAction.objects.create(
            user=self.students[0].user,
            school=self.source,
            action_type=OfflineAction.ActionType.HOMEWORK_SUBMISSION,
            payload={},
        )
        self._approve()
        start_batch(self.batch, actor=self.op1)

        # Attempt 1: student 2 moves, student 1 blocks on the offline guard.
        summary = advance_batch(self.batch, actor=self.op1, max_cases=10)
        self.assertEqual(summary["ran"], 1)
        self.assertEqual(summary["blocked"], 1)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, SchoolTransferBatch.Status.RUNNING)

        # Exhaust the blocked case's attempt ledger.
        for _ in range(MAX_CASE_ATTEMPTS - 1):
            advance_batch(self.batch, actor=self.op1, max_cases=10)
        self.batch.refresh_from_db()
        self.assertEqual(
            self.batch.status, SchoolTransferBatch.Status.COMPLETED_WITH_ISSUES
        )

        blocked_case = TransferCase.objects.get(
            batch=self.batch, source_profile_pk=str(self.students[0].pk)
        )
        # The blocked case is still APPROVED — resolvable in the single-case
        # console once the offline queue drains; nothing was force-failed.
        self.assertEqual(blocked_case.status, TransferCase.Status.APPROVED)
        entry = self.batch.ledger[str(blocked_case.pk)]
        self.assertGreaterEqual(entry["attempts"], MAX_CASE_ATTEMPTS)
        self.assertIn("offline action", entry["last_error"])

        # Wind-down refuses over the unfinished case.
        with self.assertRaises(BatchBlockedError):
            wind_down_source(self.batch, actor=self.op1, confirm_slug="batch-src")

    def test_split_cohort_scopes_the_fan_out(self):
        other_dept = Department.objects.create(
            school=self.source, name="Arts", code="ART-BS"
        )
        other_classroom = Classroom.objects.create(
            school=self.source,
            academic_year=self.source_year,
            department=other_dept,
            name="Form 5B",
            code="F5B-BS",
        )
        self.students[1].classroom = other_classroom
        self.students[1].save(update_fields=["classroom"])

        batch = SchoolTransferBatch.objects.create(
            kind=SchoolTransferBatch.Kind.SPLIT,
            source_school=self.source,
            target_school=self.target,
            consent_basis="Campus split charter 2026",
            cohort={"classroom_ids": [str(self.source_classroom.pk)]},
        )
        preview = preview_batch(batch)
        self.assertEqual(preview["to_move"], 1)
        record_batch_approval(batch, self.op1, "batch-src")
        record_batch_approval(batch, self.op2, "batch-src")
        outcome = start_batch(batch, actor=self.op1)
        self.assertEqual(outcome["cases_created"], 1)
        case = TransferCase.objects.get(batch=batch)
        self.assertEqual(case.source_profile_pk, str(self.students[0].pk))

        # Split never winds down the source.
        batch.refresh_from_db()
        with self.assertRaises(BatchBlockedError):
            wind_down_source(batch, actor=self.op1, confirm_slug="batch-src")

    def test_restart_skips_students_already_moving(self):
        self._approve()
        start_batch(self.batch, actor=self.op1)
        batch2 = SchoolTransferBatch.objects.create(
            kind=SchoolTransferBatch.Kind.MERGE,
            source_school=self.source,
            target_school=self.target,
            consent_basis="Governing-board merger resolution 2026-07",
        )
        preview = preview_batch(batch2)
        self.assertEqual(preview["to_move"], 0)
        self.assertEqual(preview["already_in_flight_or_moved"], 2)

    def test_per_guardian_mode_waits_for_the_consent_rail(self):
        batch = SchoolTransferBatch.objects.create(
            kind=SchoolTransferBatch.Kind.MERGE,
            source_school=self.source,
            target_school=self.target,
            consent_mode=SchoolTransferBatch.ConsentMode.PER_GUARDIAN,
        )
        preview_batch(batch)
        record_batch_approval(batch, self.op1, "batch-src")
        record_batch_approval(batch, self.op2, "batch-src")
        start_batch(batch, actor=self.op1)
        self.assertEqual(
            TransferCase.objects.filter(
                batch=batch, status=TransferCase.Status.DRAFT
            ).count(),
            2,
        )
        summary = advance_batch(batch, actor=self.op1, max_cases=10)
        self.assertEqual(summary["ran"], 0)
        batch.refresh_from_db()
        self.assertEqual(batch.status, SchoolTransferBatch.Status.RUNNING)

    def test_cancel_stops_scheduling(self):
        self._approve()
        start_batch(self.batch, actor=self.op1)
        cancel_batch(self.batch, actor=self.op1)
        self.assertEqual(self.batch.status, SchoolTransferBatch.Status.CANCELLED)
        with self.assertRaises(BatchBlockedError):
            advance_batch(self.batch, actor=self.op1)

    def test_periodic_entry_advances_running_batches(self):
        self._approve()
        start_batch(self.batch, actor=self.op1)
        outcome = advance_running_batches(max_cases=10)
        self.assertEqual(outcome["advanced"], 1)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, SchoolTransferBatch.Status.COMPLETED)

    def test_periodic_job_registered_cron_only(self):
        from apps.platform_runtime import periodic

        periodic.ensure_default_jobs()
        job = periodic._REGISTRY.get("people.advance_school_transfer_batches")
        self.assertIsNotNone(job)
        self.assertFalse(job.auto_eligible)


class SchoolBatchConsoleTests(TestCase):
    def setUp(self):
        self.source = School.objects.create(
            name="Console Src", slug="console-bsrc", subdomain="console-bsrc"
        )
        self.target = School.objects.create(
            name="Console Tgt", slug="console-btgt", subdomain="console-btgt"
        )
        self.op1 = User.objects.create_user(
            username="cb_op1", password="pass123", is_staff=True, is_superuser=True
        )
        self.op2 = User.objects.create_user(
            username="cb_op2", password="pass123", is_staff=True, is_superuser=True
        )
        self.client.force_login(self.op1)

    def test_non_staff_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("portal:school_batches_index"))
        self.assertEqual(response.status_code, 302)

    def test_create_dual_approve_start_flow(self):
        response = self.client.post(
            reverse("portal:school_batch_create"),
            {
                "kind": "merge",
                "source_school_id": str(self.source.pk),
                "target_school_id": str(self.target.pk),
                "consent_basis": "Board resolution 44/2026",
                "format": "json",
            },
        )
        self.assertEqual(response.status_code, 201)
        batch_id = response.json()["batch"]["id"]
        self.assertEqual(response.json()["batch"]["status"], "previewed")

        # First approval records the primary; same operator again → 409.
        response = self.client.post(
            reverse("portal:school_batch_approve"),
            {"batch_id": batch_id, "confirm_slug": "console-bsrc", "format": "json"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["approved"])
        response = self.client.post(
            reverse("portal:school_batch_approve"),
            {"batch_id": batch_id, "confirm_slug": "console-bsrc", "format": "json"},
        )
        self.assertEqual(response.status_code, 409)

        self.client.force_login(self.op2)
        response = self.client.post(
            reverse("portal:school_batch_approve"),
            {"batch_id": batch_id, "confirm_slug": "console-bsrc", "format": "json"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["approved"])

        response = self.client.post(
            reverse("portal:school_batch_start"),
            {"batch_id": batch_id, "format": "json"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["batch"]["status"], "running")

        # Empty school: the first advance completes the batch cleanly.
        response = self.client.post(
            reverse("portal:school_batch_advance"),
            {"batch_id": batch_id, "format": "json"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["batch"]["status"], "completed")

    def test_same_school_rejected(self):
        response = self.client.post(
            reverse("portal:school_batch_create"),
            {
                "kind": "merge",
                "source_school_id": str(self.source.pk),
                "target_school_id": str(self.source.pk),
                "format": "json",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_wind_down_requires_confirm_slug(self):
        batch = SchoolTransferBatch.objects.create(
            kind=SchoolTransferBatch.Kind.MERGE,
            source_school=self.source,
            target_school=self.target,
            consent_basis="Board resolution 44/2026",
            status=SchoolTransferBatch.Status.COMPLETED,
        )
        response = self.client.post(
            reverse("portal:school_batch_wind_down"),
            {"batch_id": str(batch.pk), "confirm_slug": "wrong", "format": "json"},
        )
        self.assertEqual(response.status_code, 409)
        response = self.client.post(
            reverse("portal:school_batch_wind_down"),
            {
                "batch_id": str(batch.pk),
                "confirm_slug": "console-bsrc",
                "format": "json",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.source.refresh_from_db()
        self.assertFalse(self.source.is_active)

    def test_unknown_batch_404(self):
        response = self.client.post(
            reverse("portal:school_batch_start"),
            {"batch_id": "not-a-uuid", "format": "json"},
        )
        self.assertEqual(response.status_code, 404)

    def test_html_index_renders(self):
        response = self.client.get(reverse("portal:school_batches_index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "School merge / split")
