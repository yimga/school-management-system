"""One rejected file must not roll back the good files beside it.

Last wave fixed a real defect: an artifact that quarantined every row reported
``succeeded`` while writing 0 created / 0 updated / 431 quarantined, so nobody
looked for hours. It was marked ``FAILED``.

That fix reached further than intended. The bundle-level rule is
``failed = any(o.status == "FAILED")``, and a FAILED non-atomic bundle then calls
``_rollback_all_runs`` to honour the "FAILED means nothing landed" contract. So a
single unimportable file began rolling back every artifact that had succeeded
next to it -- which is precisely the damage the school reported when its subjects
and specialties disappeared alongside its students. It also broke the
self-serve pipeline test, which is how it was caught.

The correct split:

  * per FILE -- rejecting every row is that file's failure. Its run must read
    Failed, never Success, because being told "succeeded" is what cost the hours.
  * per BUNDLE -- only a hard error, or a bundle where NOTHING landed anywhere,
    is a bundle failure. A bundle that imported four files and rejected a fifth
    keeps the four, stays repairable, and does not throw away good data.

Repairability never depended on the FAILED status anyway: ``_has_unresolved_issues``
already returns True for any bundle carrying quarantined rows.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.migration_cloud.landers.base import LanderResult


def _result(*, created=0, updated=0, quarantined=0) -> LanderResult:
    result = LanderResult()
    result.created = created
    result.updated = updated
    result.quarantined = quarantined
    return result


class _Outcome:
    def __init__(self, status: str):
        self.status = status


class ArtifactStatusTests(SimpleTestCase):
    """The per-file rule, read off the orchestrator itself."""

    def test_total_rejection_is_not_reported_as_success_or_partial(self):
        from apps.migration_cloud.orchestrator import artifact_outcome_status

        self.assertEqual(artifact_outcome_status(_result(quarantined=431)), "REJECTED")

    def test_a_rejected_file_reads_as_failed_on_its_run(self):
        """What the operator sees must not say "succeeded" -- the original defect."""
        from apps.automation.models import MigrationRun
        from apps.migration_cloud.orchestrator import _RUN_STATUS_MAP

        self.assertEqual(_RUN_STATUS_MAP["REJECTED"], MigrationRun.Status.FAILED)

    def test_partial_and_success_are_unchanged(self):
        from apps.migration_cloud.orchestrator import artifact_outcome_status

        self.assertEqual(artifact_outcome_status(_result(created=180, quarantined=20)), "PARTIAL")
        self.assertEqual(artifact_outcome_status(_result(updated=5, quarantined=20)), "PARTIAL")
        self.assertEqual(artifact_outcome_status(_result(created=200)), "SUCCESS")

    def test_nothing_to_do_is_still_success(self):
        from apps.migration_cloud.orchestrator import artifact_outcome_status

        self.assertEqual(
            artifact_outcome_status(_result()),
            "SUCCESS",
            "a header-only file, or a re-run where every record was already "
            "current, must not be called a failure",
        )


class BundleStatusTests(SimpleTestCase):
    """The per-bundle rule — the one that decides whether good rows survive."""

    def _failed(self, outcomes, **totals):
        from apps.migration_cloud.orchestrator import bundle_apply_failed

        base = {"created": 0, "updated": 0, "quarantined": 0}
        base.update(totals)
        return bundle_apply_failed(outcomes=outcomes, totals=base)

    def test_one_rejected_file_beside_good_ones_does_not_fail_the_bundle(self):
        """The regression: this rolled back the subjects and specialties."""
        outcomes = [_Outcome("SUCCESS"), _Outcome("SUCCESS"), _Outcome("REJECTED")]
        self.assertFalse(
            self._failed(outcomes, created=240, quarantined=431),
            "a single unimportable file discarded every good file in the bundle",
        )

    def test_a_bundle_where_nothing_landed_at_all_is_a_failure(self):
        """The 431-of-431 case that started this: one file, everything rejected."""
        self.assertTrue(self._failed([_Outcome("REJECTED")], quarantined=431))

    def test_a_hard_failure_still_fails_the_bundle(self):
        outcomes = [_Outcome("SUCCESS"), _Outcome("FAILED")]
        self.assertTrue(
            self._failed(outcomes, created=10),
            "a crashed lander must still fail the bundle and roll back",
        )

    def test_a_clean_bundle_succeeds(self):
        self.assertFalse(self._failed([_Outcome("SUCCESS")], created=200))

    def test_an_empty_bundle_is_not_called_a_failure_here(self):
        """The all-quarantined-artifacts case is caught earlier, by its own guard."""
        self.assertFalse(self._failed([], created=0))

    def test_a_bundle_that_only_updated_rows_is_not_a_failure(self):
        outcomes = [_Outcome("PARTIAL")]
        self.assertFalse(
            self._failed(outcomes, updated=12, quarantined=3),
            "a repair that updated existing rows did real work",
        )
