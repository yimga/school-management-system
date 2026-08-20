"""A pulled bundle with one dangling FK must not destroy the whole pull.

Reported from the box (2026-08-20)::

    pull failed: insert or update on table "academics_specialty" violates
    foreign key constraint "academics_specialty_department_id_..._fk_academics"
    DETAIL: Key (department_id)=(2) is not present in table "academics_department".

The pull was not losing one specialty — it was losing EVERYTHING, every cycle,
forever. ``_apply_changes_inner`` applies the whole batch inside one
``transaction.atomic()`` and relies on per-row savepoints to "roll back ONLY
this row, never the whole bundle". On PostgreSQL that guarantee does not hold:
Django emits every FK as ``DEFERRABLE INITIALLY DEFERRED``
(``connection.ops.deferrable_sql()``), so the violation is not raised at the
offending statement — it is raised when the OUTERMOST transaction commits, after
every row has been processed, and it takes the entire batch down. Nothing
applied, the sync cursor never advanced, and the next cycle re-pulled the same
doomed bundle.

``_force_immediate_constraints`` switches the constraints to IMMEDIATE for that
transaction so the savepoints behave the way the code already assumes. It runs in
its own savepoint and swallows failures: a hardening step must never be the thing
that aborts an apply.

NOTE ON COVERAGE: this suite runs on SQLite, which checks FKs eagerly anyway, so
it CANNOT demonstrate the Postgres failure or its repair. What it pins is the
wiring — that the guard is issued on Postgres, skipped elsewhere, and actually
invoked inside the batch transaction — so the fix cannot be silently dropped.
Behavioural proof requires a Postgres-backed run.
"""
from __future__ import annotations

import uuid
from contextlib import nullcontext
from unittest import mock

from django.test import SimpleTestCase, TestCase

from apps.schools.models import School

from apps.api.sync_services import _force_immediate_constraints


def _no_atomic():
    """The guard wraps itself in a savepoint; these cases assert on the SQL only."""
    return mock.patch("django.db.transaction.atomic", lambda *a, **k: nullcontext())


class DeferredConstraintGuardTests(SimpleTestCase):
    def test_postgres_switches_constraints_to_immediate(self):
        conn = mock.MagicMock()
        conn.vendor = "postgresql"
        with mock.patch("django.db.connection", conn), _no_atomic():
            _force_immediate_constraints()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.execute.assert_called_once_with("SET CONSTRAINTS ALL IMMEDIATE")

    def test_non_postgres_is_a_no_op(self):
        """SQLite already checks eagerly; issuing the statement there would error."""
        conn = mock.MagicMock()
        conn.vendor = "sqlite"
        with mock.patch("django.db.connection", conn), _no_atomic():
            _force_immediate_constraints()
        conn.cursor.assert_not_called()

    def test_django_still_defers_foreign_keys_on_postgres(self):
        """The premise of the fix. If Django ever stops deferring, revisit this."""
        from django.db.backends.postgresql.operations import DatabaseOperations

        self.assertEqual(
            DatabaseOperations.deferrable_sql(None),
            " DEFERRABLE INITIALLY DEFERRED",
            "the deferred-FK premise this guard exists for no longer holds",
        )


class BatchApplyArmsTheGuardTests(TestCase):
    """The guard is worthless if the batch transaction stops arming it."""

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Deferred {uid}", slug=f"deferred-{uid}",
            subdomain=f"def{uid}", is_active=True,
        )

    def test_batch_transaction_arms_the_guard(self):
        import apps.api.sync_services as svc

        with mock.patch.object(svc, "_force_immediate_constraints") as guard:
            svc.apply_changes(
                str(self.school.id), None, [], persist_conflicts=False,
                sync_origin="cloud-pull",
            )
        guard.assert_called_once_with()

    def test_guard_is_skipped_when_there_is_no_tenant_context(self):
        """No school -> no batch transaction -> nothing to arm."""
        import apps.api.sync_services as svc

        with mock.patch.object(svc, "_force_immediate_constraints") as guard:
            svc.apply_changes(None, None, [], persist_conflicts=False, sync_origin="cloud-pull")
        guard.assert_not_called()
