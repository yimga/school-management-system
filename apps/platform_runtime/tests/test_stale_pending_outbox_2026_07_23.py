"""A non-draining provision outbox must become VISIBLE, not silently PENDING.

A PROVISION_SCHOOL row stuck PENDING (broker up, no worker consuming, /health/
drain disabled/unpinged) never becomes a WorkflowRun, so every provisioning
watchdog is blind to it. reconcile_stale_pending_provisions surfaces it (WARNING)
and kicks a drain as belt-and-suspenders.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.platform_runtime import heavy_work_outbox as hwo
from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox


class StalePendingOutboxTests(TestCase):
    def _pending_row(self, *, age_seconds: int) -> HeavyWorkOutbox:
        row = HeavyWorkOutbox.objects.create(
            kind=HeavyWorkOutbox.Kind.PROVISION_SCHOOL,
            school_id="s-1",
            status=HeavyWorkOutbox.Status.PENDING,
        )
        HeavyWorkOutbox.objects.filter(pk=row.pk).update(
            created_at=timezone.now() - timedelta(seconds=age_seconds)
        )
        return row

    def test_fresh_pending_is_not_stale(self):
        self._pending_row(age_seconds=5)
        self.assertEqual(hwo.stale_pending_provision_count(), 0)

    def test_old_pending_is_counted_and_reconcile_alerts_and_kicks(self):
        self._pending_row(age_seconds=hwo._STALE_PENDING_ALERT_SECONDS + 120)
        self.assertEqual(hwo.stale_pending_provision_count(), 1)
        # (The WARNING log is a side effect; the test suite globally disables
        # logging, so assert the return contract + the belt-and-suspenders kick.)
        with patch.object(hwo, "kick_heavy_work_drain") as kick:
            result = hwo.reconcile_stale_pending_provisions()
        self.assertEqual(result["stale_pending"], 1)
        self.assertTrue(result["kicked"])
        kick.assert_called_once()

    def test_processing_and_succeeded_rows_are_not_flagged(self):
        # Only PENDING provision rows are the stalled-queue signal.
        for status in (
            HeavyWorkOutbox.Status.PROCESSING,
            HeavyWorkOutbox.Status.SUCCEEDED,
            HeavyWorkOutbox.Status.FAILED,
        ):
            row = HeavyWorkOutbox.objects.create(
                kind=HeavyWorkOutbox.Kind.PROVISION_SCHOOL, school_id="s-x", status=status
            )
            HeavyWorkOutbox.objects.filter(pk=row.pk).update(
                created_at=timezone.now() - timedelta(seconds=3600)
            )
        self.assertEqual(hwo.stale_pending_provision_count(), 0)
        self.assertEqual(hwo.reconcile_stale_pending_provisions()["stale_pending"], 0)
