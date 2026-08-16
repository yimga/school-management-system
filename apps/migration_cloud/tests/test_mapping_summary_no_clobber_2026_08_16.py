"""The apply finalize must not clobber lander-written mapping_summary data.

Feature ④ (Migration Cloud → 100% infallible), finding #7.

Landers (student / staff) write operator-review data — ``dedup_candidates`` /
``dedup_links`` — straight to the bundle row's ``mapping_summary`` during the apply,
using their OWN re-fetched bundle instance (LanderContext carries bundle_id, not the
orchestrator's object). The orchestrator's in-memory bundle still held the PRE-wave
mapping_summary, so its finalize rebuild + ``save(update_fields=["mapping_summary"])``
overwrote the row and dropped the operator's duplicate-review queue.

The fix refreshes mapping_summary from the DB before the finalize merge.

Before the fix, ``test_finalize_preserves_lander_dedup_writes`` sees dedup_candidates
gone (clobbered).
"""
from __future__ import annotations

from unittest import mock

from django.test import TestCase

from apps.migration_cloud import orchestrator
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)
from apps.migration_cloud.orchestrator import ArtifactApplyOutcome


class MappingSummaryNoClobberTests(TestCase):
    def _bundle(self):
        return MigrationBundle.objects.create(
            label="clobber", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="clobber-1", status=BundleStatus.MAPPED, school=None,
            mapping_summary={"per_artifact": {"students.csv": []}},  # map-phase state
        )

    def _artifact(self, bundle):
        return MigrationArtifact.objects.create(
            bundle=bundle, path_within_bundle="students.csv", filename="students.csv",
            detected_format=ArtifactFormat.CSV, sha256="sha-clobber", quarantined=False,
        )

    def test_finalize_preserves_lander_dedup_writes(self):
        b = self._bundle()
        self._artifact(b)

        def _fake_apply_artifact(bundle, job, *, dry_run):
            # Exactly what the real landers do: mutate mapping_summary on a SEPARATE
            # (re-fetched) instance and save just that field mid-apply.
            fresh = MigrationBundle.objects.get(pk=bundle.pk)
            summary = dict(fresh.mapping_summary or {})
            summary.setdefault("dedup_candidates", []).append({"who": "possible-dup"})
            fresh.mapping_summary = summary
            fresh.save(update_fields=["mapping_summary"])
            return ArtifactApplyOutcome(
                artifact_id=job.artifact.pk,
                path_within_bundle=job.artifact.path_within_bundle,
                domain=job.domain,
                migration_run_id=None,
                status="SUCCESS",
            )

        with mock.patch.object(orchestrator, "_apply_artifact", side_effect=_fake_apply_artifact):
            result = orchestrator.apply_bundle(bundle_id=b.pk, dry_run=False)

        self.assertEqual(result.status, BundleStatus.APPLIED)
        b.refresh_from_db()
        # The lander's operator-review queue survived the finalize...
        self.assertIn("dedup_candidates", b.mapping_summary)
        self.assertEqual(len(b.mapping_summary["dedup_candidates"]), 1)
        # ...and the finalize still layered apply_totals + kept the map-phase state.
        self.assertIn("apply_totals", b.mapping_summary)
        self.assertIn("per_artifact", b.mapping_summary)
