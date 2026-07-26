"""Migration Cloud must not stamp a *green* success on an empty import, and a
dry-run preview must never mutate the durable bundle lifecycle.

Two honesty gaps closed here:

  #4 — profiler / orchestrator 0-row honesty. A bundle whose every artifact was
       quarantined (bad format, decompression failure, unreadable bytes) retained
       zero *workable* files, yet ``profile_bundle`` advanced it to PROFILED and
       it sailed through classify → map → apply and stamped a 0-row "APPLIED".
       The operator believed the migration succeeded when nothing landed. Now the
       profiler fails such a bundle, and a defense-in-depth guard in the
       orchestrator fails a 0-workable *real* apply too.

  #6 — dry-run status mutation. A dry-run apply flipped the real bundle to
       APPLYING and back, so ``repair.py`` / the tenant progress card saw a live
       import in flight, and a dry-run worker crash left the bundle wedged /
       FAILED. A dry run must never touch the durable status.
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
from apps.migration_cloud.profiler import profile_bundle


class _Factory(TestCase):
    def _bundle(self, key, status):
        return MigrationBundle.objects.create(
            label="honesty",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"honesty-{key}",
            status=status,
            school=None,
        )

    def _artifact(self, bundle, name, *, quarantined=False, fmt=ArtifactFormat.CSV):
        return MigrationArtifact.objects.create(
            bundle=bundle,
            path_within_bundle=name,
            filename=name,
            detected_format=fmt,
            sha256=f"sha-{name}",
            quarantined=quarantined,
            quarantine_reason="bad-file" if quarantined else "",
        )


class ProfilerAllQuarantinedTests(_Factory):
    def test_all_quarantined_bundle_fails_not_profiled(self):
        b = self._bundle("allq", BundleStatus.INGESTING)
        self._artifact(b, "a.csv", quarantined=True)
        self._artifact(b, "b.csv", quarantined=True)
        profile_bundle(b)
        b.refresh_from_db()
        self.assertEqual(b.status, BundleStatus.FAILED)  # NOT a green PROFILED
        self.assertTrue(b.size_summary.get("profiler_all_quarantined"))
        self.assertEqual(b.size_summary.get("quarantined_artifacts"), 2)

    def test_archive_shell_only_bundle_fails(self):
        # An archive shell holds no rows — a bundle that is *only* an unexpanded
        # archive is not workable either.
        b = self._bundle("arc", BundleStatus.INGESTING)
        self._artifact(b, "drop.zip", fmt=ArtifactFormat.ARCHIVE)
        profile_bundle(b)
        b.refresh_from_db()
        self.assertEqual(b.status, BundleStatus.FAILED)

    def test_one_workable_artifact_still_profiles(self):
        # A single readable file among quarantined ones keeps the bundle healthy.
        b = self._bundle("ok", BundleStatus.INGESTING)
        self._artifact(b, "good.csv")
        self._artifact(b, "bad.csv", quarantined=True)
        profile_bundle(b)
        b.refresh_from_db()
        self.assertEqual(b.status, BundleStatus.PROFILED)


class ZeroWorkableApplyGuardTests(_Factory):
    def test_real_apply_with_all_quarantined_artifacts_fails(self):
        b = self._bundle("zw", BundleStatus.MAPPED)
        self._artifact(b, "a.csv", quarantined=True)
        result = orchestrator.apply_bundle(bundle_id=b.pk, dry_run=False)
        b.refresh_from_db()
        self.assertEqual(b.status, BundleStatus.FAILED)  # NOT a 0-row APPLIED
        self.assertEqual(result.status, BundleStatus.FAILED)
        self.assertTrue(b.size_summary.get("no_workable_artifacts"))


class DryRunDoesNotMutateStatusTests(_Factory):
    def test_dry_run_leaves_status_mapped(self):
        b = self._bundle("dry", BundleStatus.MAPPED)
        result = orchestrator.apply_bundle(bundle_id=b.pk, dry_run=True)
        b.refresh_from_db()
        self.assertEqual(b.status, BundleStatus.MAPPED)  # never flipped to APPLYING
        self.assertEqual(result.status, BundleStatus.MAPPED)
        self.assertIn("last_dry_run", b.size_summary)

    def test_dry_run_crash_leaves_status_mapped(self):
        # A crash DURING a dry-run apply (here: audit-run creation blows up mid-run)
        # must re-raise to the caller but leave the real bundle untouched at MAPPED —
        # a preview failure is not a bundle failure.
        b = self._bundle("drycrash", BundleStatus.MAPPED)
        self._artifact(b, "x.csv")  # one workable file so _run_waves actually runs
        with mock.patch.object(
            orchestrator, "_create_audit_run", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                orchestrator.apply_bundle(bundle_id=b.pk, dry_run=True)
        b.refresh_from_db()
        self.assertEqual(b.status, BundleStatus.MAPPED)  # NOT FAILED
