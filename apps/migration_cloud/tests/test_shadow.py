"""Smoke tests for shadow-mode (`apps.migration_cloud.shadow`).

Verifies the state machine: start → refresh → drift compute → close
(accepted vs rejected). Uses operator-supplied source counts + a fake
tenant_counter so no tenant DB setup is required.
"""

from __future__ import annotations

from django.test import TestCase

from apps.migration_cloud import shadow
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle


class ShadowLifecycleTests(TestCase):
    def setUp(self) -> None:
        self.bundle = MigrationBundle.objects.create(
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="shadow-smoke-1",
            status=BundleStatus.APPLIED,
            mapping_summary={"apply_totals": {"created": 100}},
        )

    def test_start_requires_applied_status(self) -> None:
        self.bundle.status = BundleStatus.PROFILED
        self.bundle.save(update_fields=["status"])
        with self.assertRaises(ValueError):
            shadow.start_shadow_window(bundle_id=self.bundle.pk)

    def test_start_seeds_from_live_counts_when_no_source_pull(self) -> None:
        # With no source_pull the baseline is the immediately-post-apply LIVE
        # tenant count (forward-drift tracking), NOT the old misleading
        # {students: apply_totals.created, guardians:0, staff:0, ...} snapshot that
        # read ~100% drift on every 0-seeded domain and blocked auto-cutover.
        # In this empty test DB the live counts are 0.
        # See docs/MIGRATION_CLOUD_AUDIT_2026_07_24.md (D-1).
        state = shadow.start_shadow_window(bundle_id=self.bundle.pk)
        self.assertEqual(state.target_parity_pct, 99.0)
        self.assertEqual(state.source_mode, "manual")
        # Baseline is live tenant counts (all-zero here), never the apply_totals=100 shortcut.
        self.assertEqual(state.source_snapshot.get("students", 0), 0)
        self.assertEqual(state.ticks, [])
        self.assertFalse(state.auto_cutover_armed)

    def test_refresh_appends_tick_and_computes_drift(self) -> None:
        shadow.start_shadow_window(
            bundle_id=self.bundle.pk,
            source_pull=lambda: {"students": 100, "guardians": 50},
        )
        state = shadow.refresh_shadow(
            bundle_id=self.bundle.pk,
            source_pull=lambda: {"students": 100, "guardians": 50},
            tenant_counter=lambda b: {"students": 95, "guardians": 50},
        )
        self.assertEqual(len(state.ticks), 1)
        # diff=5, scale=150 → 100*5/150 ≈ 3.333
        self.assertAlmostEqual(state.ticks[0].drift_pct, 3.333, places=2)
        # Drift > (100 - 99) = 1, so trip=True
        self.assertTrue(state.ticks[0].trip)

    def test_close_accepted_advances_to_reconciled(self) -> None:
        shadow.start_shadow_window(bundle_id=self.bundle.pk)
        state = shadow.close_shadow(bundle_id=self.bundle.pk, accepted=True)
        self.assertTrue(state.accepted)
        self.bundle.refresh_from_db()
        self.assertEqual(self.bundle.status, BundleStatus.RECONCILED)

    def test_close_rejected_keeps_bundle_status(self) -> None:
        shadow.start_shadow_window(bundle_id=self.bundle.pk)
        state = shadow.close_shadow(bundle_id=self.bundle.pk, accepted=False)
        self.assertFalse(state.accepted)
        self.bundle.refresh_from_db()
        self.assertEqual(self.bundle.status, BundleStatus.APPLIED)

    def test_auto_cutover_fires_after_sustained_clean_ticks(self) -> None:
        shadow.start_shadow_window(
            bundle_id=self.bundle.pk,
            source_pull=lambda: {"students": 100},
            auto_cutover_armed=True,
        )
        clean = lambda b: {"students": 100}  # exact parity → drift 0, trip False
        for _ in range(3):
            shadow.refresh_shadow(
                bundle_id=self.bundle.pk,
                source_pull=lambda: {"students": 100},
                tenant_counter=clean,
            )
        self.bundle.refresh_from_db()
        self.assertEqual(self.bundle.status, BundleStatus.RECONCILED)


class ShadowDriftComputationTests(TestCase):
    def test_zero_drift_when_perfectly_synced(self) -> None:
        self.assertEqual(
            shadow._compute_drift_pct({"a": 10, "b": 5}, {"a": 10, "b": 5}),
            0.0,
        )

    def test_full_drift_when_one_side_empty(self) -> None:
        self.assertEqual(
            shadow._compute_drift_pct({"a": 10}, {}),
            100.0,
        )

    def test_partial_drift_is_symmetric(self) -> None:
        forward = shadow._compute_drift_pct({"a": 10}, {"a": 7})
        reverse = shadow._compute_drift_pct({"a": 7}, {"a": 10})
        self.assertAlmostEqual(forward, reverse, places=5)
