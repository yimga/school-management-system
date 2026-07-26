"""Per-row savepoint isolation under the forced-atomic finance apply.

Finance forces the orchestrator to wrap the WHOLE apply in one
``transaction.atomic()`` (money must be all-or-nothing vs the control totals).
Before ``row_savepoint``, a single bad row's ``IntegrityError`` marked the whole
connection ``needs_rollback``, so the lander's per-row ``try/except`` could not
continue — the next query raised ``TransactionManagementError`` and EVERY good row
rolled back with the one bad one. The savepoint isolates each write so the per-row
quarantine actually works.

These tests exercise the mechanism directly against a real unique constraint
(``MigrationBundle.idempotency_key``): the positive test proves a failing write
inside ``row_savepoint`` leaves the outer transaction usable; the control proves
the savepoint is load-bearing (the same failure WITHOUT it poisons the txn).
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.migration_cloud.landers._helpers import row_savepoint
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle


class RowSavepointAtomicTests(TestCase):
    def _bundle(self, key):
        return MigrationBundle.objects.create(
            label="sp",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=key,
            status=BundleStatus.MAPPED,
        )

    def test_savepoint_isolates_failure_inside_outer_atomic(self):
        self._bundle("dup-key")  # occupy the unique key
        with transaction.atomic():  # simulate the forced-atomic apply
            try:
                with row_savepoint():
                    # Collides on the unique idempotency_key -> IntegrityError.
                    MigrationBundle.objects.create(
                        label="bad",
                        intake_method=IntakeMethod.FILE_UPLOAD,
                        idempotency_key="dup-key",
                        status=BundleStatus.MAPPED,
                    )
            except IntegrityError:
                pass  # the lander's per-row quarantine
            # The outer transaction must still be usable — a good write succeeds.
            good = self._bundle("fresh-key")
            self.assertIsNotNone(good.pk)
        self.assertTrue(
            MigrationBundle.objects.filter(idempotency_key="fresh-key").exists()
        )

    def test_without_savepoint_the_failure_poisons_the_outer_atomic(self):
        # Control: the SAME caught failure WITHOUT a savepoint poisons the txn, so
        # the next query raises. This is exactly the bug the savepoint fixes.
        self._bundle("dup-key2")
        with self.assertRaises(Exception):
            with transaction.atomic():
                try:
                    MigrationBundle.objects.create(
                        label="bad",
                        intake_method=IntakeMethod.FILE_UPLOAD,
                        idempotency_key="dup-key2",
                        status=BundleStatus.MAPPED,
                    )
                except IntegrityError:
                    pass
                # Poisoned transaction -> TransactionManagementError here.
                MigrationBundle.objects.filter(idempotency_key="x").exists()


class SwallowPoisonSiteCoverageTests(TestCase):
    """Regression lock: every best-effort swallow-write that runs INSIDE the atomic
    apply must be savepoint-wrapped. These sites have no observable happy-path
    behaviour, so only a real DB poison would catch a regression — a source lock is
    the pragmatic guard that a future edit doesn't quietly drop the savepoint.
    """

    def _src(self, dotted):
        import importlib
        import inspect

        return inspect.getsource(importlib.import_module(dotted))

    def test_orchestrator_quarantine_write_is_savepointed(self):
        src = self._src("apps.migration_cloud.orchestrator")
        # _quarantine_errors creates MigrationQuarantineRecord per error, swallowing.
        self.assertIn("with transaction.atomic():", src)
        self.assertIn("MigrationQuarantineRecord.objects.create", src)

    def test_pulse_workflow_step_is_savepointed(self):
        src = self._src("apps.platform_runtime.workflow_tracker")
        # The pulse writes WorkflowStep/WorkflowRun and swallows internally; it can
        # fire from inside an outer atomic() (the MC finance apply) via ensure_workflow_run.
        self.assertIn("with transaction.atomic():", src)

    def test_finance_colanders_savepoint_their_inline_upsert(self):
        # Students + enrollment land in earlier waves of the SAME atomic finance txn
        # and do their own inline upsert (not via the shared helper).
        for mod in (
            "apps.migration_cloud.landers.student_lander",
            "apps.migration_cloud.landers.enrollment_lander",
        ):
            self.assertIn("row_savepoint", self._src(mod), mod)
