"""The RLS policy shape has to match the column, and no scanner can check that.

``scan_rls_table_coverage`` answers one question: is this table NAMED in an enable_rls
migration. It cannot tell a correct policy from a policy that silently hides every row,
and the difference here is one nullable column.

``EdgePairingRequest.school`` is nullable by design -- a box naming a slug the cloud does
not recognise still produces a request row so the operator sees a real attempt instead of
silence. Under the ordinary predicate ``school_id = current_setting(...)`` a NULL never
compares equal, so those rows would be invisible to everyone, and the claim path
(``pairing_service.claim_by_code``, a lookup BY USER_CODE) is precisely the query that
would then return nothing. Pairing would break in RLS mode, and no SQLite test can show it
because ``should_apply_rls`` is False there.

So these tests assert the INVARIANT rather than the SQL: every table in the strict list
has a NOT NULL school, every table in the nullable list has a nullable one, and the two
lists together are exactly the tenant-scoped tables the migration claims to cover. A new
nullable tenant-scoped table added to the strict list fails here instead of silently
hiding its own rows in production.
"""
from __future__ import annotations

import importlib

from django.apps import apps as django_apps
from django.test import SimpleTestCase

MIGRATION = "apps.sync_engine.migrations.0017_pairing_rls"


def _migration():
    return importlib.import_module(MIGRATION)


def _school_is_nullable(table: str) -> bool:
    for model in django_apps.get_app_config("sync_engine").get_models():
        if model._meta.db_table == table:
            return model._meta.get_field("school").null
    raise AssertionError(f"no sync_engine model maps to {table}")


class PairingRlsPolicyShapeTests(SimpleTestCase):
    def test_01_every_strict_table_has_a_not_null_school(self):
        """A strict policy on a nullable column hides rows nobody can get back."""
        mig = _migration()
        for table in mig.STRICT_TABLES:
            self.assertFalse(
                _school_is_nullable(table),
                f"{table} has a NULLABLE school but is on the strict policy, so its "
                "unclaimed rows would be invisible to every caller",
            )

    def test_02_every_nullable_listed_table_really_is_nullable(self):
        """The NULL allowance is a real exception, not a blanket loosening."""
        mig = _migration()
        for table in mig.NULLABLE_SCHOOL_TABLES:
            self.assertTrue(
                _school_is_nullable(table),
                f"{table} has a NOT NULL school, so admitting school_id IS NULL widens "
                "the policy for no reason",
            )

    def test_03_the_two_lists_are_disjoint_and_complete(self):
        mig = _migration()
        self.assertEqual(
            set(mig.STRICT_TABLES) & set(mig.NULLABLE_SCHOOL_TABLES),
            set(),
            "a table cannot carry both policy shapes",
        )
        self.assertEqual(
            sorted(mig.TABLES),
            sorted(set(mig.STRICT_TABLES) | set(mig.NULLABLE_SCHOOL_TABLES)),
            "TABLES is what the migration iterates; a table missing from it gets no policy",
        )

    def test_04_the_nullable_clause_admits_null_and_the_strict_one_does_not(self):
        mig = _migration()
        self.assertIn("school_id IS NULL", mig._TENANT_MATCH_OR_UNCLAIMED)
        self.assertNotIn("school_id IS NULL", mig._TENANT_MATCH)
        # Both must still honour the bypass, or platform staff tooling loses the table.
        for clause in (mig._TENANT_MATCH, mig._TENANT_MATCH_OR_UNCLAIMED):
            self.assertIn("app.rls_bypass", clause)
            self.assertIn("app.current_school_id", clause)

    def test_05_policy_names_are_unique_per_table(self):
        mig = _migration()
        names = [mig._policy_name(t) for t in mig.TABLES]
        self.assertEqual(len(names), len(set(names)), "a reused policy name overwrites")

    def test_06_it_is_a_no_op_off_postgres_so_the_sqlite_suite_proves_nothing(self):
        """Stated in a test so nobody reads a green local run as proof of RLS."""
        from django.db import connection

        from apps.schools.rls import should_apply_rls

        if connection.vendor != "postgresql":
            self.assertFalse(should_apply_rls(connection))

    def test_07_every_tenant_scoped_sync_engine_table_is_enumerated_somewhere(self):
        """The app-local seal for the class of regression PR #184 shipped.

        ``scan_rls_table_coverage`` covers the whole repo and is wired into ci.yml -- but
        GitHub Actions has run no jobs since 2026-08-15, so during that window this test
        is the thing that actually runs.
        """
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[3]
        enumerated: set[str] = set()
        for path in (root / "apps" / "sync_engine" / "migrations").glob("*rls*.py"):
            enumerated.update(
                re.findall(r"[\"'](sync_engine_[a-z0-9_]+)[\"']",
                           path.read_text(encoding="utf-8", errors="replace"))
            )
        missing = []
        for model in django_apps.get_app_config("sync_engine").get_models():
            names = {f.name for f in model._meta.get_fields() if hasattr(f, "name")}
            if "school" not in names:
                continue
            if model._meta.db_table not in enumerated:
                missing.append(model._meta.db_table)
        self.assertEqual(
            sorted(missing), [], "tenant-scoped sync_engine tables with no RLS policy"
        )
