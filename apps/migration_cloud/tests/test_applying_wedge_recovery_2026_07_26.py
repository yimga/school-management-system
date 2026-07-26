"""A Migration Cloud apply must never WEDGE the bundle in APPLYING.

Two failure modes left an import stuck at APPLYING forever — repair refused it
("still running") and re-apply requires MAPPED, so it was unrecoverable without
DB surgery (this is a root cause of the "repair does nothing / import stuck"
reports):

  1. The apply raised a NON-financial exception mid-run. ``orchestrator`` only
     caught ``FinancialMismatchError``, so anything else propagated with the
     bundle still APPLYING. Fix: a catch-all marks the bundle FAILED (which
     ``repair_readiness`` treats as repairable) before re-raising.
  2. The worker DIED mid-apply (SIGKILL / OOM / deploy restart) — no exception
     ran at all, so no handler could fire. Fix: ``repair_readiness`` reclaims a
     STALE APPLYING (no apply in flight + past the threshold) as repairable.
"""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.migration_cloud import orchestrator
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.migration_cloud.repair import repair_readiness
from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox
from apps.schools.models import School


class _BundleFactory(TestCase):
    def _school(self, key):
        return School.objects.create(
            name=f"Wedge {key}", slug=f"wedge-{key}", subdomain=f"wedge-{key}",
            is_active=True, country_code="CM",
        )

    def _bundle(self, key, status, school=None):
        return MigrationBundle.objects.create(
            label="wedge", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"wedge-{key}", status=status, school=school,
        )

    def _age(self, bundle, seconds):
        """Backdate updated_at without tripping auto_now."""
        old = timezone.now() - timedelta(seconds=seconds)
        MigrationBundle.objects.filter(pk=bundle.pk).update(updated_at=old)
        bundle.refresh_from_db()


class StaleApplyingReclaimTests(_BundleFactory):
    def test_stale_applying_no_inflight_is_repairable(self):
        b = self._bundle("stale", BundleStatus.APPLYING, self._school("stale"))
        self._age(b, 60 * 60)  # APPLYING for an hour, no apply queued/running
        rr = repair_readiness(b)
        self.assertTrue(rr.repairable, rr.reason)
        self.assertIn("stopped unexpectedly", rr.reason.lower())

    def test_recent_applying_is_not_repairable(self):
        b = self._bundle("recent", BundleStatus.APPLYING, self._school("recent"))
        # updated_at ~ now -> a real apply may still be running -> refuse.
        rr = repair_readiness(b)
        self.assertFalse(rr.repairable)
        self.assertIn("still running", rr.reason.lower())

    def test_stale_applying_with_inflight_outbox_is_not_repairable(self):
        b = self._bundle("inflight", BundleStatus.APPLYING, self._school("inflight"))
        self._age(b, 60 * 60)  # old timestamp, BUT...
        HeavyWorkOutbox.objects.create(  # ...a real apply job is queued -> genuinely in flight
            kind=HeavyWorkOutbox.Kind.MC_APPLY_BUNDLE,
            bundle_id=b.pk,
            status=HeavyWorkOutbox.Status.PENDING,
        )
        rr = repair_readiness(b)
        self.assertFalse(rr.repairable)
        self.assertIn("still running", rr.reason.lower())


class ApplyExceptionMarksFailedTests(_BundleFactory):
    def test_non_financial_apply_exception_marks_failed_not_applying(self):
        # A school-less, artifact-less MAPPED bundle applies through to the
        # financial-guardrail call with an empty outcome set; patching that to
        # raise a NON-financial error exercises the orchestrator's catch-all.
        b = self._bundle("orch", BundleStatus.MAPPED, school=None)
        with mock.patch.object(
            orchestrator, "_maybe_check_financial_guardrail", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                orchestrator.apply_bundle(bundle_id=b.pk, dry_run=False)
        b.refresh_from_db()
        self.assertEqual(b.status, BundleStatus.FAILED)  # NOT wedged at APPLYING
