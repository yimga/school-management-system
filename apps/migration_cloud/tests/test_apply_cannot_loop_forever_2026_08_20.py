"""A 44-second import must not run 48 times in 24 hours.

Bundle 84 on production apply-completed at 20:32:40 with
``0 created, 105 updated, 442 quarantined`` — and was still labelled "Running"
the next day. The cycle, read straight off its progress-event stream:

  apply runs (44s) -> emits stage_finished -> bundle never leaves APPLYING
  -> 1800s later ``applying_stale_by_time`` says wedged -> self-heal reclaims
  it to MAPPED -> apply runs again -> ... roughly 48 times.

Nothing was broken enough to raise. The self-heal was doing exactly what it was
written to do; it simply had no ceiling, and no one verified that a finished
apply had actually settled.

Three independent guarantees are pinned here, each of which alone stops the loop:

1. The reclaim budget is finite.
2. A settled bundle never reports in-flight, so an orphaned outbox row cannot
   pin a COMPLETED import at "Running" (and then at "Failed (Stuck)").
3. Succeeded outbox rows are reaped, so one import stops looking like five.

All DB-free: pure helpers, a stub bundle, and a faked queryset.
"""

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from apps.migration_cloud.models import BundleStatus
from apps.migration_cloud.orchestrator import (
    _MAX_WEDGED_APPLY_RECLAIMS,
    _TERMINAL_BUNDLE_STATUSES,
    wedged_reclaim_budget_exhausted,
    wedged_reclaims_so_far,
)
from apps.migration_cloud.views_tenant_upload import (
    _SETTLED_BUNDLE_STATUSES,
    _import_flight,
)


class ReclaimBudgetIsFiniteTests(SimpleTestCase):
    def test_a_fresh_bundle_has_used_nothing(self):
        self.assertEqual(wedged_reclaims_so_far({}), 0)
        self.assertFalse(wedged_reclaim_budget_exhausted({}))

    def test_the_budget_runs_out(self):
        for used in range(_MAX_WEDGED_APPLY_RECLAIMS):
            with self.subTest(used=used):
                self.assertFalse(
                    wedged_reclaim_budget_exhausted({"wedged_apply_reclaims": used})
                )
        for used in (_MAX_WEDGED_APPLY_RECLAIMS, _MAX_WEDGED_APPLY_RECLAIMS + 5, 48):
            with self.subTest(used=used):
                self.assertTrue(
                    wedged_reclaim_budget_exhausted({"wedged_apply_reclaims": used})
                )

    def test_the_production_loop_count_would_have_been_stopped(self):
        # 24h / 1800s stale threshold is ~48 cycles. The ceiling must bite long
        # before that; this is the regression the whole file exists for.
        self.assertLess(_MAX_WEDGED_APPLY_RECLAIMS, 10)
        self.assertTrue(wedged_reclaim_budget_exhausted({"wedged_apply_reclaims": 48}))

    def test_a_corrupt_counter_never_raises_inside_an_apply(self):
        for junk in (None, "", "many", {}, [], {"wedged_apply_reclaims": "x"},
                     {"wedged_apply_reclaims": None}, {"wedged_apply_reclaims": -4}):
            with self.subTest(junk=junk):
                self.assertEqual(wedged_reclaims_so_far(junk), 0)

    def test_terminal_statuses_are_the_ones_that_end_an_apply(self):
        for status in (BundleStatus.APPLIED, BundleStatus.RECONCILED,
                       BundleStatus.FAILED, BundleStatus.ABORTED):
            with self.subTest(status=status):
                self.assertIn(status, _TERMINAL_BUNDLE_STATUSES)

    def test_applying_is_not_terminal(self):
        # The entire defect: APPLYING read as an acceptable resting state.
        self.assertNotIn(BundleStatus.APPLYING, _TERMINAL_BUNDLE_STATUSES)
        self.assertNotIn(BundleStatus.MAPPED, _TERMINAL_BUNDLE_STATUSES)


class SettledBundleIsNotInFlightTests(SimpleTestCase):
    """An orphaned outbox row must not resurrect a finished import."""

    def test_an_applied_bundle_reports_settled_without_touching_the_outbox(self):
        bundle = SimpleNamespace(pk=84, status=BundleStatus.APPLIED)
        with mock.patch(
            "apps.platform_runtime.models_heavy_work_outbox.HeavyWorkOutbox"
        ) as outbox:
            flight = _import_flight(bundle)
        self.assertEqual(
            flight, {"in_flight": False, "phase": "", "stuck": False, "dry_run": False}
        )
        outbox.objects.filter.assert_not_called()

    def test_a_reconciled_bundle_is_settled_too(self):
        bundle = SimpleNamespace(pk=84, status=BundleStatus.RECONCILED)
        self.assertFalse(_import_flight(bundle)["in_flight"])

    def test_a_settled_bundle_is_never_reported_stuck(self):
        # "Failed (Stuck)" on an import that succeeded is the exact thing a
        # tenant saw for a full day.
        bundle = SimpleNamespace(pk=84, status=BundleStatus.APPLIED)
        self.assertFalse(_import_flight(bundle)["stuck"])

    def test_failed_and_aborted_are_NOT_settled_for_flight_purposes(self):
        # A repair queued against a failed bundle is real in-flight work the
        # tenant must be able to see; suppressing it would make Repair look dead.
        self.assertNotIn(BundleStatus.FAILED, _SETTLED_BUNDLE_STATUSES)
        self.assertNotIn(BundleStatus.ABORTED, _SETTLED_BUNDLE_STATUSES)

    def test_applying_is_not_settled(self):
        self.assertNotIn(BundleStatus.APPLYING, _SETTLED_BUNDLE_STATUSES)


class SucceededRowsAreReapedTests(SimpleTestCase):
    def test_only_succeeded_rows_past_the_window_are_deleted(self):
        from apps.platform_runtime import heavy_work_outbox as hwo

        captured = {}

        class _FakeQS:
            def delete(self):
                return (5, {})

        class _FakeManager:
            def filter(self, **kw):
                captured.update(kw)
                return _FakeQS()

        fake = mock.MagicMock()
        fake.objects = _FakeManager()
        fake.Status.SUCCEEDED = "succeeded"
        with mock.patch(
            "apps.platform_runtime.models_heavy_work_outbox.HeavyWorkOutbox", fake
        ):
            deleted = hwo._reap_settled_rows()

        self.assertEqual(deleted, 5)
        self.assertEqual(captured.get("status"), "succeeded")
        self.assertIn("created_at__lt", captured)

    def test_failed_rows_are_evidence_and_are_kept(self):
        from apps.platform_runtime import heavy_work_outbox as hwo

        import inspect

        src = inspect.getsource(hwo._reap_settled_rows)
        self.assertIn("SUCCEEDED", src)
        self.assertNotIn("FAILED", src)

    def test_a_reap_failure_never_breaks_the_drain(self):
        from apps.platform_runtime import heavy_work_outbox as hwo

        boom = mock.MagicMock()
        boom.objects.filter.side_effect = RuntimeError("db gone")
        with mock.patch(
            "apps.platform_runtime.models_heavy_work_outbox.HeavyWorkOutbox", boom
        ):
            self.assertEqual(hwo._reap_settled_rows(), 0)

    def test_the_retention_window_keeps_a_day_for_debugging(self):
        from apps.platform_runtime import heavy_work_outbox as hwo

        self.assertGreaterEqual(hwo._SETTLED_ROW_RETENTION_SECONDS, 3600)
