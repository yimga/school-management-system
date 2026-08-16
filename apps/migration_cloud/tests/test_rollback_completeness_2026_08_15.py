"""RMC Edge feature ④ — rollback-completeness seals (2026-08-15).

Two VERIFIED gaps closed, each proven end-to-end through a real apply (which
spawns worker threads, hence ``TransactionTestCase``):

Fix A — enrollment rollback RESTORES the snapshotted prior values.
    ``enrollment_lander`` snapshots the OLD non-empty value of every field it
    overwrites into ``updated_ids_with_old_values``. ``_rollback_enrollment``
    used to IGNORE that list and return ``success=False, reverted_count=0`` with
    a message claiming the values "were not snapshotted". Now it re-applies each
    recorded prior value, school-scoped, and reports the restored count.

Fix B — a FAILED non-atomic bundle must not leave committed rows LIVE.
    In a non-atomic multi-artifact apply where artifact A commits rows and
    artifact B fails, the bundle read FAILED while A's rows stayed live — the
    orchestrator's normal-return ``failed`` branch never rolled the succeeded
    runs back. Now it calls ``_rollback_all_runs`` (child-first) so a FAILED
    bundle really leaves nothing behind — matching the "FAILED = nothing landed"
    contract the atomic path already guarantees.

Both tests FAIL against the pre-fix code and PASS against the fix.
"""

from __future__ import annotations

import io
import types
from unittest import mock

from django.test import TransactionTestCase

from apps.migration_cloud import artifact_blob_store as store
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)


def _xlsx_bytes(headers, rows):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _payload(data: bytes):
    return types.SimpleNamespace(content_opener=lambda: io.BytesIO(data))


def _add_artifact(bundle, path, domain, headers, rows, sha):
    """A non-quarantined XLSX artifact with its source bytes captured + its
    domain pinned, so ``apply_bundle`` lands it via ``domain``'s lander."""
    data = _xlsx_bytes(headers, rows)
    art = MigrationArtifact.objects.create(
        bundle=bundle,
        path_within_bundle=path,
        filename=path,
        detected_format=ArtifactFormat.XLSX,
        byte_size=len(data),
        sha256=sha,
        assigned_domain=domain,
    )
    store.capture_artifact_blob(art, _payload(data))
    return art


def _map(bundle, per_artifact):
    """Pin explicit column→canonical mappings so apply is deterministic without
    running the classifier/mapper. ``per_artifact`` maps path → [(src, canon)]."""
    bundle.mapping_summary = {
        **(bundle.mapping_summary or {}),
        "per_artifact": {
            path: [
                {"source_column": src, "canonical_field": canon}
                for src, canon in cols
            ]
            for path, cols in per_artifact.items()
        },
    }
    bundle.save(update_fields=["mapping_summary", "updated_at"])


class EnrollmentRollbackRestoresPriorValuesTests(TransactionTestCase):
    """Fix A — the in-place enrollment overwrite is reversible from its snapshot."""

    def test_rollback_restores_overwritten_student_status(self):
        from apps.automation.models import MigrationRun
        from apps.migration_cloud.orchestrator import apply_bundle
        from apps.people.models import StudentProfile
        from apps.schools.models import School

        school = School.objects.create(name="Enroll RB", subdomain="enroll-rb")
        student = StudentProfile.objects.create(
            school=school,
            first_name="Ada",
            last_name="Lovelace",
            admission_number="PS-1029",
            status=StudentProfile.Status.RETURNING,
        )
        student.refresh_from_db()
        adm = student.admission_number  # actual key after any save-time policy
        self.assertEqual(student.status, StudentProfile.Status.RETURNING)

        bundle = MigrationBundle.objects.create(
            label="enroll-overwrite",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="rb-enroll-overwrite",
            status=BundleStatus.MAPPED,
            school=school,
            apply_atomic=False,
        )
        _add_artifact(
            bundle, "enrollment.xlsx", "enrollment",
            ["ID", "Status"], [[adm, "withdrawn"]], "e" * 64,
        )
        _map(bundle, {
            "enrollment.xlsx": [
                ("ID", "student_external_id"),
                ("Status", "enrollment_status"),
            ],
        })

        apply_bundle(bundle_id=bundle.pk, workers=1)

        # Sanity: the apply really overwrote the lifecycle status in place.
        student.refresh_from_db()
        self.assertEqual(
            student.status, StudentProfile.Status.TRANSFERRED,
            "apply should have overwritten status withdrawn->TRANSFERRED",
        )

        run = (
            MigrationRun.objects.filter(
                school=school, migration_type__startswith="enrollment:"
            )
            .order_by("-started_at")
            .first()
        )
        self.assertIsNotNone(run, "an enrollment MigrationRun should exist")
        # The prior value WAS snapshotted (the premise Fix A relies on).
        snap = run.rollback_snapshot or {}
        updated = snap.get("updated_ids_with_old_values") or []
        self.assertTrue(updated, "old-value snapshot must be present")
        self.assertEqual(
            updated[0]["old"].get("status"), StudentProfile.Status.RETURNING,
        )

        # --- The fix under test: rollback RESTORES the prior status ------------
        rollback_run, result = run.trigger_rollback(user=None)
        self.assertTrue(
            result.get("success"),
            f"enrollment rollback should succeed, got: {result!r}",
        )
        self.assertEqual(
            result.get("reverted_count"), 1,
            f"one student should be restored, got: {result!r}",
        )
        student.refresh_from_db()
        self.assertEqual(
            student.status, StudentProfile.Status.RETURNING,
            "rollback must restore the student's PRIOR status",
        )


class FailedNonAtomicBundleRollsBackCommittedRowsTests(TransactionTestCase):
    """Fix B — a FAILED non-atomic bundle leaves no committed rows live."""

    def test_second_artifact_failure_rolls_back_first_artifacts_rows(self):
        from apps.migration_cloud.landers import get_lander
        from apps.migration_cloud.orchestrator import apply_bundle
        from apps.people.models import StudentProfile
        from apps.schools.models import School

        school = School.objects.create(name="Partial RB", subdomain="partial-rb")
        bundle = MigrationBundle.objects.create(
            label="partial-fail",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="rb-partial-fail",
            status=BundleStatus.MAPPED,
            school=school,
            apply_atomic=False,  # non-atomic: rows commit per-artifact (autocommit)
        )
        # Artifact A (wave 1, students) commits a brand-new StudentProfile.
        _add_artifact(
            bundle, "students.xlsx", "students",
            ["ID", "First", "Last"], [["S-1", "Grace", "Hopper"]], "a" * 64,
        )
        # Artifact B (wave 2, enrollment) is forced to FAIL below.
        _add_artifact(
            bundle, "enrollment.xlsx", "enrollment",
            ["ID"], [["S-1"]], "b" * 64,
        )
        _map(bundle, {
            "students.xlsx": [
                ("ID", "external_id"),
                ("First", "first_name"),
                ("Last", "last_name"),
            ],
            "enrollment.xlsx": [("ID", "student_external_id")],
        })

        enrollment_lander = get_lander("enrollment")
        with mock.patch.object(
            enrollment_lander, "land",
            side_effect=RuntimeError("boom: enrollment artifact fails after students commit"),
        ):
            apply_bundle(bundle_id=bundle.pk, workers=1)

        bundle.refresh_from_db()
        self.assertEqual(
            bundle.status, BundleStatus.FAILED,
            "a bundle with a FAILED artifact must read FAILED",
        )
        # The heart of Fix B: the committed student from artifact A must NOT be
        # left live behind a FAILED bundle — it is rolled back.
        self.assertEqual(
            StudentProfile.objects.filter(school=school).count(), 0,
            "artifact A's committed rows must be rolled back when the bundle FAILED "
            "— a FAILED bundle must not leave rows live",
        )
