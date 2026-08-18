"""An artifact that rejects every row must not report success.

A live tenant ran five repairs in eighty seconds. Every one reported ``succeeded``
and every one wrote ``0 created / 0 updated / 431 quarantined``: nothing landed,
twice, across two bundles, and because the run looked green nobody went looking
for hours.

The cause was one line -- ``PARTIAL if result.quarantined else SUCCESS`` -- which
has no state for "quarantined everything". Total rejection is now FAILED, which is
both honest and useful: ``repair_readiness`` treats FAILED as repairable once the
source is corrected.

The guard is deliberately narrow. It fires only when rows were REJECTED, so an
artifact that legitimately had nothing to do -- a header-only file, or a re-run
where every record was already current -- still reports success rather than being
called a failure for landing zero rows.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.migration_cloud.landers.base import LanderResult


def _classify(result: LanderResult) -> str:
    """Mirror of the orchestrator's outcome-status rule, kept in one place.

    Asserting the rule directly keeps this test honest about WHAT is being pinned
    (the semantic) without standing up a whole bundle apply, which needs tenant
    schemas this suite does not have.
    """
    if result.quarantined and not (result.created or result.updated):
        return "FAILED"
    return "PARTIAL" if result.quarantined else "SUCCESS"


class TotalRejectionIsFailureTests(SimpleTestCase):
    def _result(self, *, created=0, updated=0, quarantined=0):
        result = LanderResult()
        result.created = created
        result.updated = updated
        result.quarantined = quarantined
        return result

    def test_every_row_rejected_is_a_failure(self):
        """The production case: 0 created, 0 updated, 431 quarantined."""
        self.assertEqual(
            _classify(self._result(quarantined=431)),
            "FAILED",
            "an import that wrote nothing at all still reported success",
        )

    def test_some_landed_some_rejected_is_partial(self):
        self.assertEqual(_classify(self._result(created=180, quarantined=20)), "PARTIAL")

    def test_updates_only_with_rejections_is_partial(self):
        """A repair that updates existing rows HAS done work, even if some fail."""
        self.assertEqual(_classify(self._result(updated=5, quarantined=20)), "PARTIAL")

    def test_clean_run_is_success(self):
        self.assertEqual(_classify(self._result(created=200)), "SUCCESS")

    def test_nothing_to_do_is_still_success(self):
        """Header-only file, or a re-run where every record was already current."""
        self.assertEqual(
            _classify(self._result()),
            "SUCCESS",
            "an artifact with no work and no rejections must not be called a failure",
        )


class OrchestratorRuleIsWiredTests(SimpleTestCase):
    """The rule above must be the one the orchestrator actually applies."""

    def test_orchestrator_contains_the_total_rejection_branch(self):
        import inspect

        from apps.migration_cloud import orchestrator

        source = inspect.getsource(orchestrator)
        self.assertIn(
            "if result.quarantined and not (result.created or result.updated):",
            source,
            "the orchestrator no longer classifies total rejection as a failure",
        )
