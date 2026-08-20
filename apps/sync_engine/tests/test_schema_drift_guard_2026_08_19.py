"""A deployment behind on migrations must SAY SO, not throw a column name at a page.

Reported from a box on 2026-08-19: a bare branded 500 on ``/authentication/backend/``.
The cause was ``OperationalError: no such column: academics_academicyear.is_soft_closed``
— the box had pulled code carrying migrations ``academics.0082`` and ``0083`` and had
never run ``migrate``. Nothing anywhere named that. The operator saw "Service
interrupted." and had no path from there to the fix.

It is worse on the sync rail. An inbound bundle carries whatever columns the CLOUD's
registry declares, so a box behind on migrations cannot apply those rows at all — and
``OperationalError`` was in none of the per-row except tuples, so it escaped
``apply_changes`` and took the entire bundle down. That is the same wedge the
referential-integrity pass closed for foreign keys, arriving through a different door:
one un-appliable row costs every good row in the bundle, the cursor never advances, and
the identical bundle replays forever.

Two halves, both tested here: the row degrades alone, and the operator is told the actual
cause with the actual remedy.
"""
from __future__ import annotations

from unittest import mock

from django.db import OperationalError
from django.test import TestCase

from apps.academics.models import Department
from apps.accounts.models import User
from apps.api.sync_services import apply_changes
from apps.schools.models import School
from apps.sync_engine import schema_guard


def _row(entity_type, pk, changes):
    return {
        "entity_type": entity_type,
        "id": pk,
        "client_offline_id": "",
        "changes": changes,
        "updated_at": "2026-08-19T10:00:00+00:00",
    }


class SchemaGuardTests(TestCase):
    def setUp(self):
        schema_guard.reset()

    def tearDown(self):
        schema_guard.reset()

    def test_a_migrated_deployment_reports_current(self):
        """The test database is migrated by definition, so this is the honest baseline."""
        self.assertEqual(schema_guard.pending_migrations(force=True), [])
        self.assertTrue(schema_guard.schema_is_current(force=True))
        self.assertEqual(schema_guard.drift_note(), "")

    def test_summary_shape_when_current(self):
        summary = schema_guard.summary(force=True)
        self.assertTrue(summary["current"])
        self.assertEqual(summary["pending_count"], 0)
        self.assertEqual(summary["pending"], [])
        self.assertFalse(summary["truncated"])

    def test_a_behind_deployment_names_the_migrations_and_the_remedy(self):
        """"2 migrations behind" sends someone to Slack; naming `migrate` sends them to
        the fix."""
        with mock.patch.object(
            schema_guard,
            "pending_migrations",
            return_value=["academics.0082_academicyear_lock_provenance",
                          "academics.0083_academicyear_soft_close"],
        ):
            note = schema_guard.drift_note()
        self.assertIn("2 migration(s) behind", note)
        self.assertIn("academics.0083_academicyear_soft_close", note)
        self.assertIn("migrate", note)

    def test_a_long_pending_list_is_truncated_for_the_poll(self):
        many = ["app.%04d_m" % i for i in range(60)]
        with mock.patch.object(schema_guard, "pending_migrations", return_value=many):
            summary = schema_guard.summary()
        self.assertEqual(summary["pending_count"], 60)
        self.assertTrue(summary["truncated"])
        self.assertLess(len(summary["pending"]), 60)

    def test_the_answer_is_cached_and_reset_clears_it(self):
        """Building the migration graph is far too expensive to do per request."""
        schema_guard.pending_migrations(force=True)
        with mock.patch("django.db.migrations.executor.MigrationExecutor") as exe:
            schema_guard.pending_migrations()
            exe.assert_not_called()
        schema_guard.reset()
        with mock.patch("django.db.migrations.executor.MigrationExecutor") as exe:
            schema_guard.pending_migrations()
            exe.assert_called()

    def test_a_broken_check_degrades_instead_of_raising(self):
        """A diagnostic that can raise is worse than no diagnostic at all."""
        with mock.patch(
            "django.db.migrations.executor.MigrationExecutor",
            side_effect=RuntimeError("graph exploded"),
        ):
            self.assertEqual(schema_guard.pending_migrations(force=True), [])
        self.assertEqual(schema_guard.drift_note(), "")


class SchemaErrorContainmentTests(TestCase):
    """The half that matters most: a column this box does not have costs ONE row."""

    def setUp(self):
        self.school = School.objects.create(
            name="Drift School", slug="drift-school", subdomain="drift-school"
        )
        self.admin = User.objects.create_user(
            username="drift-admin", password="x" * 12, role=User.Role.ADMIN, is_staff=True
        )
        base = (Department.objects.order_by("-pk").values_list("pk", flat=True).first() or 0)
        self.poison_pk = base + 500
        self.good_pk = base + 501

    def _pull(self, rows):
        return apply_changes(
            str(self.school.id), self.admin, rows,
            persist_conflicts=False, sync_origin="cloud-pull",
        )

    def test_a_missing_column_degrades_the_row_not_the_bundle(self):
        real_save = Department.save

        def flaky_save(self_obj, *a, **kw):
            if getattr(self_obj, "code", "") == "PSN":
                raise OperationalError("no such column: academics_department.blood_type")
            return real_save(self_obj, *a, **kw)

        rows = [
            _row("department", self.poison_pk, {"name": "Poison", "code": "PSN"}),
            _row("department", self.good_pk, {"name": "Fine", "code": "FIN"}),
        ]
        with mock.patch.object(Department, "save", flaky_save):
            out = self._pull(rows)

        self.assertEqual(out["results"][0]["status"], 422)
        self.assertEqual(out["results"][0]["data"]["error"], "create_failed")
        self.assertEqual(
            out["results"][1]["status"], 201,
            "a column this box lacks must not cost the rest of the bundle",
        )
        self.assertTrue(Department.objects.filter(pk=self.good_pk).exists())
        self.assertFalse(Department.objects.filter(pk=self.poison_pk).exists())

    def test_the_detail_carries_the_column_so_the_cause_is_recoverable(self):
        real_save = Department.save

        def flaky_save(self_obj, *a, **kw):
            raise OperationalError("no such column: academics_department.blood_type")

        with mock.patch.object(Department, "save", flaky_save):
            out = self._pull([_row("department", self.poison_pk, {"name": "P", "code": "P1"})])
        self.assertIn("blood_type", out["results"][0]["data"]["detail"])
