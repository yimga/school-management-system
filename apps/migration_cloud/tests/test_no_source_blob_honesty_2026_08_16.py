"""A row-bearing artifact with NO readable source must NOT report SUCCESS.

Feature ④ (Migration Cloud → 100% infallible), finding #5.

When an artifact reached apply with no captured blob AND no top-level source file
to fall back to, ``_iter_canonical_rows`` silently yielded nothing, so the lander
landed 0 rows and ``_apply_artifact`` stamped a green SUCCESS. The operator saw a
file "import" when nothing was even readable (an ingest blob-capture gap / a lost
local file). The fix raises a LanderError for row-bearing formats so the outcome is
an HONEST, repairable FAILED — while container / non-tabular formats keep the
lenient empty-yield (they never produce rows through this path, so failing them
would be noise).

Before the fix, ``test_...fails_not_success`` sees the bundle APPLIED (the lie).
"""
from __future__ import annotations

from django.test import TestCase

from apps.migration_cloud import orchestrator
from apps.migration_cloud.landers import LanderError
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)
from apps.migration_cloud.orchestrator import _ArtifactJob


class _Factory(TestCase):
    def _bundle(self, key, status=BundleStatus.MAPPED):
        return MigrationBundle.objects.create(
            label="nosrc", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"nosrc-{key}", status=status, school=None,
        )

    def _artifact(self, bundle, name, *, fmt=ArtifactFormat.CSV):
        # No blob captured, and the bundle has no intake_source_uri, so there is NO
        # readable byte source for this artifact.
        return MigrationArtifact.objects.create(
            bundle=bundle, path_within_bundle=name, filename=name,
            detected_format=fmt, sha256=f"sha-{name}", quarantined=False,
        )


class NoSourceBlobHonestyTests(_Factory):
    def test_row_bearing_artifact_with_no_source_fails_not_success(self):
        b = self._bundle("csv")
        self._artifact(b, "students.csv", fmt=ArtifactFormat.CSV)

        result = orchestrator.apply_bundle(bundle_id=b.pk, dry_run=False)

        b.refresh_from_db()
        self.assertEqual(b.status, BundleStatus.FAILED)   # NOT a 0-row APPLIED
        self.assertEqual(result.status, BundleStatus.FAILED)
        # The per-artifact outcome carries the honest reason.
        self.assertEqual(len(result.per_artifact), 1)
        outcome = result.per_artifact[0]
        self.assertEqual(outcome.status, "FAILED")
        self.assertIn("No source data available", outcome.error)

    def test_iter_rows_raises_for_row_format_without_source(self):
        b = self._bundle("iter-csv")
        art = self._artifact(b, "grades.csv", fmt=ArtifactFormat.CSV)
        job = _ArtifactJob(artifact=art, domain="custom_fields", mappings=[])
        with self.assertRaises(LanderError):
            orchestrator._iter_canonical_rows(job)

    def test_iter_rows_is_lenient_for_container_format_without_source(self):
        # A non-row / container format (sqlite here) never streams rows through this
        # path, so a missing source yields empty rather than false-failing.
        b = self._bundle("iter-sqlite")
        art = self._artifact(b, "legacy.sqlite3", fmt=ArtifactFormat.SQLITE)
        job = _ArtifactJob(artifact=art, domain="custom_fields", mappings=[])
        rows = list(orchestrator._iter_canonical_rows(job))  # must NOT raise
        self.assertEqual(rows, [])
