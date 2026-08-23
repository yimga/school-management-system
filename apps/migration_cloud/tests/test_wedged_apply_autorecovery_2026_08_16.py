"""A worker-crash-wedged apply must AUTO-recover on the durable retry.

Feature ④ (Migration Cloud → 100% infallible), finding #2.

When the apply worker dies mid-run (SIGKILL / OOM / deploy restart) it never
reaches the orchestrator's except-handler, so the bundle stays APPLYING. The
HeavyWorkOutbox reclaims the stale PROCESSING row and re-dispatches ``apply_bundle``
— but the re-entry hit the ``must be MAPPED`` guard and raised ``ValueError``, so
the retry dead-lettered and the import was stranded at APPLYING forever (only a
manual repair click could rescue it — ``repair.repair_readiness`` already reclaims
that case, but nothing did so automatically).

The fix makes ``_apply_bundle_inner`` self-heal: an APPLYING bundle whose
``updated_at`` is stale past the threshold (its worker stopped heartbeating) is
reclaimed to MAPPED and re-applied. A LIVE apply heartbeats ``updated_at`` every
wave/artifact, so a *fresh* APPLYING bundle is still refused — the concurrency
guard is preserved.

Each test FAILS before the fix:
  * the stale-wedge test raises ``ValueError`` (no reclaim);
  * the heartbeat test raises ``AttributeError`` (no ``_heartbeat_apply``).
"""
from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.migration_cloud import orchestrator
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.migration_cloud.repair import _APPLYING_STALE_SECONDS, applying_stale_by_time


class _BundleFactory(TestCase):
    def _bundle(self, key, status, school=None):
        return MigrationBundle.objects.create(
            label="wedge-auto", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"wedge-auto-{key}", status=status, school=school,
        )

    def _age(self, bundle, seconds):
        """Backdate updated_at without tripping auto_now (direct UPDATE)."""
        old = timezone.now() - timedelta(seconds=seconds)
        MigrationBundle.objects.filter(pk=bundle.pk).update(updated_at=old)
        bundle.refresh_from_db()


class WedgedApplyAutoRecoveryTests(_BundleFactory):
    def test_stale_wedged_applying_self_heals_on_retry(self):
        # An empty (artifact-less, school-less) bundle applies straight through — so a
        # durable retry that RECLAIMS it must LAND, not raise. A live apply now ends by
        # reconciling (run_post_apply_verification), so the settled status is
        # RECONCILED; the ApplyResult still reports APPLIED, which is the status the
        # apply itself reached before the verification step ran.
        b = self._bundle("stale", BundleStatus.APPLYING, school=None)
        self._age(b, _APPLYING_STALE_SECONDS + 600)  # worker died; no heartbeat

        # Before the fix this raised ValueError ("must be MAPPED"); now it recovers.
        result = orchestrator._apply_bundle_inner(bundle_id=b.pk, dry_run=False)

        b.refresh_from_db()
        self.assertEqual(b.status, BundleStatus.RECONCILED)  # reclaimed -> applied -> reconciled
        self.assertIn("reclaimed_wedged_apply_at", b.size_summary)
        self.assertEqual(result.status, BundleStatus.APPLIED)

    def test_fresh_applying_is_still_refused(self):
        # A freshly-flipped APPLYING bundle = a real apply may be running RIGHT NOW.
        # The reclaim must NOT fire (updated_at is fresh) — the concurrency guard
        # (two applies cannot both proceed) is preserved.
        b = self._bundle("fresh", BundleStatus.APPLYING, school=None)
        self.assertFalse(applying_stale_by_time(b))  # fresh -> not stale

        with self.assertRaises(ValueError):
            orchestrator._apply_bundle_inner(bundle_id=b.pk, dry_run=False)

        b.refresh_from_db()
        self.assertEqual(b.status, BundleStatus.APPLYING)  # untouched by the refusal
        self.assertNotIn("reclaimed_wedged_apply_at", b.size_summary)


class ApplyHeartbeatTests(_BundleFactory):
    def test_heartbeat_clears_staleness_for_a_live_apply(self):
        # Prove the liveness mechanism: a stale-looking APPLYING bundle becomes
        # fresh after a heartbeat, so a live-but-slow apply is never reclaimed.
        b = self._bundle("beat", BundleStatus.APPLYING, school=None)
        self._age(b, _APPLYING_STALE_SECONDS + 600)
        self.assertTrue(applying_stale_by_time(b))  # looks dead...

        orchestrator._heartbeat_apply(b.pk)  # ...until the live worker pulses

        b.refresh_from_db()
        self.assertFalse(applying_stale_by_time(b))  # fresh again -> not reclaimable

    def test_heartbeat_only_touches_an_applying_bundle(self):
        # The heartbeat is scoped to status=APPLYING, so it can never resurrect the
        # updated_at of a bundle in any other state (e.g. a MAPPED one awaiting apply).
        b = self._bundle("mapped", BundleStatus.MAPPED, school=None)
        self._age(b, _APPLYING_STALE_SECONDS + 600)
        before = MigrationBundle.objects.get(pk=b.pk).updated_at

        orchestrator._heartbeat_apply(b.pk)  # no-op: bundle is MAPPED, not APPLYING

        after = MigrationBundle.objects.get(pk=b.pk).updated_at
        self.assertEqual(before, after)
