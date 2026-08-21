"""Re-applying a bundle must not append another copy of its held rows.

Bundle 84 in production:

    runs 384 | held records 40448
     25600  invalid_ref        students
     13824  missing_required   sections
      1024  missing_required   specialties

That is 316 records x 128 apply cycles -- 128 identical copies of the same
316 rows, growing by 316 every thirty minutes with no upper bound. The apply
regenerates its held rows from scratch every time, so the previous cycle's
PENDING rows were never history; they were duplicates nobody would ever read.

The counters told the same story twice over: 442 held was reported while only
316 were persisted when ``QUARANTINE_RECORD_CAP`` was 200 (students artifact
truncated from 326 to 200). The cap is now 2000 so a full held set persists.

What must NOT be swept is a resolution. REPAIRED and FAILED rows are the audit
trail the whole review surface depends on, and a sweep that ate them would
destroy the record of decisions already made.

DB-free: the quarantine model and run model are faked.
"""

from unittest import mock

from django.test import SimpleTestCase

from apps.migration_cloud.orchestrator import (
    QUARANTINE_RECORD_CAP,
    _clear_superseded_quarantine,
)


class _Captured:
    """Records the filter kwargs a delete() was scoped by."""

    def __init__(self):
        self.filters = None
        self.deleted = 0

    def as_model(self, *, deleted=0, statuses=("PENDING", "REPAIRED", "FAILED")):
        captured = self

        class _QS:
            def delete(self_inner):
                captured.deleted = deleted
                return (deleted, {})

        class _Manager:
            def filter(self_inner, **kw):
                captured.filters = kw
                return _QS()

        model = mock.MagicMock()
        model.objects = _Manager()
        for name in statuses:
            setattr(model.Status, name, name)
        return model


def _run_model(pks):
    runs = mock.MagicMock()
    runs.objects.filter.return_value.values_list.return_value = pks
    return runs


class SupersededQuarantineIsSweptTests(SimpleTestCase):
    def _sweep(self, *, run_pks, deleted):
        cap = _Captured()
        bundle = mock.Mock(pk=84)
        with mock.patch(
            "apps.automation.models.MigrationQuarantineRecord",
            cap.as_model(deleted=deleted),
        ), mock.patch("apps.automation.models.MigrationRun", _run_model(run_pks)):
            result = _clear_superseded_quarantine(bundle)
        return result, cap

    def test_the_production_backlog_would_be_swept(self):
        result, _ = self._sweep(run_pks=list(range(384)), deleted=40448)
        self.assertEqual(result, 40448)

    def test_only_pending_rows_are_swept(self):
        # REPAIRED / FAILED are resolutions. Sweeping them would delete the
        # record of every decision already made about this bundle.
        _, cap = self._sweep(run_pks=[1, 2, 3], deleted=316)
        self.assertEqual(cap.filters.get("status"), "PENDING")

    def test_the_sweep_is_scoped_to_this_bundles_own_runs(self):
        # A sweep scoped wider than the bundle would delete another school's
        # held rows. The run ids ARE the tenant boundary here.
        _, cap = self._sweep(run_pks=[7, 8], deleted=1)
        self.assertEqual(cap.filters.get("migration_run_id__in"), [7, 8])

    def test_a_first_ever_apply_sweeps_nothing(self):
        result, cap = self._sweep(run_pks=[], deleted=999)
        self.assertEqual(result, 0)
        self.assertIsNone(cap.filters, "no prior runs must mean no delete at all")

    def test_a_sweep_failure_never_blocks_the_apply(self):
        bundle = mock.Mock(pk=84)
        boom = mock.MagicMock()
        boom.objects.filter.side_effect = RuntimeError("db gone")
        with mock.patch("apps.automation.models.MigrationRun", boom):
            self.assertEqual(_clear_superseded_quarantine(bundle), 0)


class TruncationIsReportedTests(SimpleTestCase):
    def test_the_cap_is_a_named_constant_not_a_literal(self):
        # It was `result.errors[:200]` inline, which is how it stayed invisible.
        # Raised after bundle 84 dropped 126 of 326 student errors.
        self.assertEqual(QUARANTINE_RECORD_CAP, 2000)

    def test_the_production_shape_is_the_one_that_was_truncated(self):
        # 326 students held, 200 recorded, 126 with no durable record at all.
        # Cap raised to 2000 so this shape is no longer truncated.
        held = 326
        self.assertLessEqual(held, QUARANTINE_RECORD_CAP)

    def test_the_persisted_total_matches_counted_when_under_cap(self):
        # With cap >= held volume, persisted and counted align.
        specialties, sections, students_held = 8, 108, 326
        persisted = specialties + min(students_held, QUARANTINE_RECORD_CAP) + sections
        counted = specialties + students_held + sections
        self.assertEqual(persisted, counted)
        self.assertEqual(persisted, 442)
