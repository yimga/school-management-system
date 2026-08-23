"""A finished import must be re-appliable as a no-op, not a ValueError.

``_apply_bundle_inner`` short-circuits a repeat apply:

    if bundle.status == BundleStatus.APPLIED and not dry_run:
        return _empty_result(bundle, dry_run, BundleStatus.APPLIED)

That guard names ONE terminal state. ``_apply_bundle_inner`` now ends a
successful live apply by calling ``run_post_apply_verification``, which
reconciles the bundle -- so the finish line moved to RECONCILED and the
short-circuit stopped matching it. The next apply falls through to

    if bundle.status != BundleStatus.MAPPED:
        raise ValueError(f"Bundle {id} is in status {status}; must be MAPPED to apply.")

Who hits it: the HeavyWorkOutbox durable retry re-dispatching an apply that in
fact completed, a double-dispatch racing the outbox, and an operator clicking
apply twice. The comment above the guard says a concurrent apply is "refused
below" -- refused, not crashed. A raise here dead-letters the retry and strands
the import, which is precisely the failure the wedged-apply reclaim block
directly beneath it exists to prevent.
"""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.migration_cloud.orchestrator import apply_bundle
from apps.schools.models import School


class ReapplyAfterReconcileTests(TestCase):
    def _bundle(self, status):
        tag = uuid.uuid4().hex[:8]
        school = School.objects.create(
            name=f"Reapply {tag}", slug=f"reapply-{tag}", subdomain=f"reapply-{tag}"
        )
        return MigrationBundle.objects.create(
            label=f"reapply-{tag}",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"reapply-{tag}",
            status=status,
            school=school,
        )

    def test_reapplying_an_applied_bundle_is_a_no_op(self):
        # Calibration: the branch this test is about has always worked for
        # APPLIED. If this ever fails, the short-circuit itself is gone and the
        # RECONCILED assertion below would be testing the wrong thing.
        bundle = self._bundle(BundleStatus.APPLIED)
        result = apply_bundle(bundle_id=bundle.pk, workers=1)
        self.assertEqual(result.status, BundleStatus.APPLIED)
        self.assertEqual(result.total_created, 0)

    def test_reapplying_a_reconciled_bundle_is_a_no_op_too(self):
        bundle = self._bundle(BundleStatus.RECONCILED)
        result = apply_bundle(bundle_id=bundle.pk, workers=1)
        self.assertEqual(
            result.status,
            BundleStatus.RECONCILED,
            "a reconciled bundle is FINISHED -- re-applying it must be a no-op, "
            "not a ValueError that dead-letters the durable retry",
        )
        self.assertEqual(result.total_created, 0)
        bundle.refresh_from_db()
        self.assertEqual(bundle.status, BundleStatus.RECONCILED)

    def test_a_genuinely_unappliable_bundle_is_still_refused(self):
        """The guard must not become a blanket 'anything goes'."""
        bundle = self._bundle(BundleStatus.PROFILED)
        with self.assertRaises(ValueError) as ctx:
            apply_bundle(bundle_id=bundle.pk, workers=1)
        self.assertIn("must be MAPPED to apply", str(ctx.exception))
