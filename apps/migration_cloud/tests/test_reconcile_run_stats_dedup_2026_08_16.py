"""Reconciliation must count only the LATEST apply attempt, never sum across them.

Feature ④ (Migration Cloud → 100% infallible), finding #6.

Every apply attempt creates a fresh MigrationRun per (domain, artifact). Blindly
summing created_count across all of them double-counts after a re-apply (repair, or
rollback + reapply): reconciliation sees more "created" than are visible in the
school, raises a phantom drift note, and wedges the bundle at APPLIED — it can never
seal RECONCILED. Dry-run preview runs (which never landed rows) inflate it too.

``_domain_run_stats`` now keeps only the latest non-dry-run run per artifact.

Before the fix, ``test_reapply_does_not_double_count`` sees created == 200 (the
double-count) and ``test_dry_run_runs_are_excluded`` sees the phantom 999.
"""
from __future__ import annotations

from django.test import TestCase

from apps.automation.models import MigrationRun
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)
from apps.migration_cloud.reconciliation import _domain_run_stats


class _Factory(TestCase):
    def _bundle(self, key):
        return MigrationBundle.objects.create(
            label="recon", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"recon-{key}", status=BundleStatus.APPLIED, school=None,
        )

    def _artifact(self, bundle, name):
        return MigrationArtifact.objects.create(
            bundle=bundle, path_within_bundle=name, filename=name,
            detected_format=ArtifactFormat.CSV, sha256=f"sha-{name}", quarantined=False,
        )

    def _run(self, bundle, artifact, *, domain, created, updated=0, errors=0, dry_run=False):
        return MigrationRun.objects.create(
            school=bundle.school,
            migration_type=f"{domain}:{artifact.path_within_bundle}"[:64],
            dry_run=dry_run,
            status=MigrationRun.Status.SUCCESS,
            created_count=created,
            updated_count=updated,
            error_count=errors,
            execution_summary={
                "bundle_id": bundle.pk,
                "artifact_id": artifact.pk,
                "domain": domain,
            },
        )


class ReconcileRunStatsDedupTests(_Factory):
    def test_reapply_does_not_double_count(self):
        b = self._bundle("reapply")
        art = self._artifact(b, "students.csv")
        # Attempt 1 (rolled back), then attempt 2 (the live one) — same artifact.
        self._run(b, art, domain="students", created=100)
        self._run(b, art, domain="students", created=100)

        stats = _domain_run_stats(b)
        self.assertEqual(stats["students"]["created"], 100)  # latest only, NOT 200

    def test_dry_run_runs_are_excluded(self):
        b = self._bundle("dry")
        art = self._artifact(b, "students.csv")
        self._run(b, art, domain="students", created=100)                 # live
        self._run(b, art, domain="students", created=999, dry_run=True)   # preview

        stats = _domain_run_stats(b)
        self.assertEqual(stats["students"]["created"], 100)  # dry preview ignored

    def test_distinct_artifacts_in_one_domain_still_sum(self):
        # Two real files in the same domain must still add up — the dedup is
        # per-artifact, not per-domain.
        b = self._bundle("multi")
        a1 = self._artifact(b, "students_a.csv")
        a2 = self._artifact(b, "students_b.csv")
        self._run(b, a1, domain="students", created=60)
        self._run(b, a2, domain="students", created=40)

        stats = _domain_run_stats(b)
        self.assertEqual(stats["students"]["created"], 100)  # 60 + 40, both counted
