"""HeavyWorkOutbox reclaim window must exceed each kind's own run time.

``_reclaim_stale_processing`` resets a PROCESSING row to PENDING (re-dispatch) once
it has been claimed longer than the reclaim window. The window was a single 900s
for ALL kinds — but an MC apply legitimately runs up to 1800s
(migration_cloud.celery_tasks expected_duration_seconds), so a still-running apply
at 900-1800s got reset + re-dispatched into a DUPLICATE apply. MC apply now has a
window past its own duration; the fast kinds keep 900s.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.platform_runtime.heavy_work_outbox import _reclaim_stale_processing
from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox


class ReclaimWindowTests(TestCase):
    def _processing(self, kind, claimed_secs_ago):
        row = HeavyWorkOutbox.objects.create(
            kind=kind, status=HeavyWorkOutbox.Status.PROCESSING
        )
        HeavyWorkOutbox.objects.filter(pk=row.pk).update(
            claimed_at=timezone.now() - timedelta(seconds=claimed_secs_ago)
        )
        return row

    def test_running_mc_apply_not_reclaimed_before_its_window(self):
        # 1200s: past the 900s default but WITHIN the MC apply window (2400s) -> a
        # still-running apply must NOT be reset + re-dispatched into a duplicate.
        row = self._processing(HeavyWorkOutbox.Kind.MC_APPLY_BUNDLE, 1200)
        _reclaim_stale_processing()
        row.refresh_from_db()
        self.assertEqual(row.status, HeavyWorkOutbox.Status.PROCESSING)

    def test_dead_mc_apply_reclaimed_past_its_window(self):
        row = self._processing(HeavyWorkOutbox.Kind.MC_APPLY_BUNDLE, 3000)  # > 2400s
        _reclaim_stale_processing()
        row.refresh_from_db()
        self.assertEqual(row.status, HeavyWorkOutbox.Status.PENDING)

    def test_fast_kind_still_reclaims_at_default_window(self):
        # A fast kind at 1200s (> 900s) is still reclaimed -> unchanged fast recovery.
        row = self._processing(HeavyWorkOutbox.Kind.PROVISION_SCHOOL, 1200)
        _reclaim_stale_processing()
        row.refresh_from_db()
        self.assertEqual(row.status, HeavyWorkOutbox.Status.PENDING)
