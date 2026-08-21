"""Unified row-weighted migration progress — monotonic bar + apply band."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase

from apps.migration_cloud.live_import_attention import compose_live_import
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.migration_cloud.progress import APPLY_RUN_EPOCH_KEY, mark_apply_run_start, refresh_snapshot
from apps.migration_cloud.unified_progress import (
    ApplyProgressTracker,
    compute_unified_percent,
    read_monotonic_hwm,
    write_monotonic_hwm,
)


class UnifiedPercentMathTests(SimpleTestCase):
    def test_apply_band_can_exceed_legacy_seventy_five_cap(self):
        bundle = SimpleNamespace(
            pk=1,
            status=BundleStatus.APPLYING,
            artifacts=SimpleNamespace(count=lambda: 3),
            progress_snapshot={},
            size_summary={APPLY_RUN_EPOCH_KEY: "2026-08-21T12:00:00+00:00"},
        )
        snap = {
            "stages": [{"name": "APPLYING", "pct": 100}],
            "live_totals": {
                "rows_processed": 400,
                "rows_expected": 500,
                "artifacts_done": 2,
                "artifacts_total": 3,
                "created": 10,
                "updated": 5,
                "quarantined": 1,
            },
        }
        result = compute_unified_percent(
            bundle,
            snapshot=snap,
            flight={"in_flight": True},
            in_flight=True,
        )
        self.assertGreater(result["percent"], 75.0)
        self.assertLessEqual(result["percent"], 99.0)

    def test_monotonic_hwm_never_regresses_within_run(self):
        bundle = MigrationBundle(
            label="hwm",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="hwm-1",
            status=BundleStatus.APPLYING,
        )
        bundle.size_summary = {APPLY_RUN_EPOCH_KEY: "epoch-a"}
        write_monotonic_hwm(bundle, 62.0, persist=False)
        write_monotonic_hwm(bundle, 55.0, persist=False)
        self.assertEqual(read_monotonic_hwm(bundle), 62.0)


class UnifiedProgressIntegrationTests(TestCase):
    def test_refresh_snapshot_carries_unified_percent(self):
        bundle = MigrationBundle.objects.create(
            label="snap",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="snap-1",
            status=BundleStatus.APPLYING,
        )
        mark_apply_run_start(bundle)
        from apps.migration_cloud.models import MigrationProgressEvent

        MigrationProgressEvent.objects.create(
            bundle=bundle,
            kind="artifact_progress",
            stage="APPLYING",
            detail={
                "pct": 50,
                "rows_processed": 100,
                "rows_expected": 400,
                "artifacts_done": 1,
                "artifacts_total": 4,
                "created": 5,
                "updated": 2,
                "quarantined": 0,
            },
        )
        snap = refresh_snapshot(bundle=bundle, persist=False)
        self.assertIsNotNone(snap.get("unified_percent"))
        self.assertGreater(float(snap["unified_percent"]), 35.0)

    @mock.patch("apps.migration_cloud.unified_progress.pulse_apply_progress")
    def test_apply_tracker_pulses_on_rows(self, pulse_mock):
        bundle = MigrationBundle.objects.create(
            label="tracker",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="tracker-1",
            status=BundleStatus.APPLYING,
        )
        tracker = ApplyProgressTracker(
            bundle=bundle,
            jobs_total=2,
            rows_expected=80,
            pulse_every_rows=10,
            min_pulse_seconds=0.01,
        )
        rows = tracker.wrap_rows(iter(range(25)), artifact_label="students.csv")
        list(rows)
        self.assertGreater(pulse_mock.call_count, 0)

    def test_compose_live_import_prefers_unified_percent(self):
        bundle = MigrationBundle.objects.create(
            label="live",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="live-1",
            status=BundleStatus.APPLYING,
        )
        snap = {
            "stages": [{"name": "APPLYING", "status": "current", "pct": 100}],
            "live_totals": {
                "rows_processed": 250,
                "rows_expected": 500,
                "artifacts_done": 1,
                "artifacts_total": 2,
                "created": 1,
                "updated": 0,
                "quarantined": 0,
            },
            "unified_percent": 68.5,
        }
        live = compose_live_import(
            bundle,
            snapshot=snap,
            flight={"in_flight": True, "phase": "running", "stuck": False},
        )
        self.assertGreaterEqual(live["percent"], 68.5)
