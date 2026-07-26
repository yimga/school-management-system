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
