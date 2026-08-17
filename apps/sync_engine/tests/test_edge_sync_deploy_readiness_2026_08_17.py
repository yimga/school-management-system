"""The edge-sync anchor columns must really exist in the database, not just in models.

Waves 2-5 added ``client_offline_id`` + a partial-unique constraint to four tables, two of
which (``evals_evaluation``, ``finance_invoice``) are the platform's marks and money tables
and live in TENANT_APPS — so under ``USE_DJANGO_TENANTS=1`` they exist once per tenant
schema and the columns arrive via ``migrate_schemas``, which applies per schema and can
succeed for some tenants and not others. A tenant missing the column does not fail loudly;
it fails the first time that tenant's box syncs.

``makemigrations --check`` only proves model state and migration state AGREE. It cannot
prove the migration ran, and it cannot see a constraint dropped from a hand-edited
migration file. This suite runs against the fully-migrated test database and asserts the
DDL is really there — so an edit that silently loses a constraint turns CI red instead of
turning up as duplicated offline records in production.

It also locks the readiness command itself, which is what an operator runs against
production Postgres to answer the same question there.
"""
from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.test import TestCase


def _columns(table):
    with connection.cursor() as cur:
        if connection.vendor == "postgresql":
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
                [table],
            )
            return {r[0] for r in cur.fetchall()}
        cur.execute(f"PRAGMA table_info({table})")
        return {r[1] for r in cur.fetchall()}


def _index_names(table):
    with connection.cursor() as cur:
        if connection.vendor == "postgresql":
            cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = %s", [table])
            return {r[0] for r in cur.fetchall()}
        cur.execute(f"PRAGMA index_list({table})")
        return {r[1] for r in cur.fetchall()}


class AnchorColumnsExistInTheDatabaseTests(TestCase):
    def test_evaluation_carries_the_anchor_column(self):
        """Wave 3 — the marks table."""
        self.assertIn("client_offline_id", _columns("evals_evaluation"))

    def test_invoice_carries_the_anchor_column(self):
        """Wave 4 — the money table."""
        self.assertIn("client_offline_id", _columns("finance_invoice"))

    def test_subject_assignment_carries_the_anchor_column(self):
        """Wave 2 — the teaching grid."""
        self.assertIn("client_offline_id", _columns("academics_subjectassignment"))

    def test_teacher_profile_carries_the_anchor_column(self):
        """Wave 5 — the staff roster."""
        self.assertIn("client_offline_id", _columns("people_teacherprofile"))


class AnchorConstraintsExistInTheDatabaseTests(TestCase):
    """Without the constraint the column is not an upsert key.

    ``apply_edge_inserts`` upserts by ``(school, client_offline_id)``. If duplicates are
    permitted, one offline record can land as several rows and the ``get_or_create`` lookup
    becomes ambiguous — a silent data-duplication bug, not an error.
    """

    def test_evaluation_partial_unique_constraint_exists(self):
        self.assertIn("uniq_evaluation_school_offline_id", _index_names("evals_evaluation"))

    def test_invoice_partial_unique_constraint_exists(self):
        self.assertIn("uniq_invoice_school_offline_id", _index_names("finance_invoice"))

    def test_subject_assignment_partial_unique_constraint_exists(self):
        self.assertIn(
            "uniq_subjectassignment_school_offline_id",
            _index_names("academics_subjectassignment"),
        )

    def test_teacher_profile_partial_unique_constraint_exists(self):
        self.assertIn(
            "uniq_teacherprofile_school_offline_id", _index_names("people_teacherprofile")
        )


class ReadinessCommandTests(TestCase):
    """The command an operator runs against production to answer the same question."""

    def test_it_passes_on_a_fully_migrated_database(self):
        out, err = StringIO(), StringIO()
        try:
            call_command("check_edge_sync_deploy_readiness", stdout=out, stderr=err)
        except SystemExit as exc:  # pragma: no cover - only on a real schema problem
            self.fail(f"readiness check failed on a migrated DB:\n{err.getvalue()}\n{exc}")
        self.assertIn("OK", out.getvalue())

    def test_it_reports_the_accessrole_row_count(self):
        """The empty-AccessRole failure mode is invisible without being counted.

        Granular RBAC resolves through ``accounts_accessrole``; an empty table denies every
        gated surface while looking like a permissions misconfiguration. Migration
        ``accounts.0029`` seeds it idempotently but is recorded as applied, so a plain
        ``migrate`` will not repair a table that was emptied afterwards — which is exactly
        the state a persisted test database ends up in.
        """
        out = StringIO()
        try:
            call_command("check_edge_sync_deploy_readiness", stdout=out, stderr=StringIO())
        except SystemExit:
            pass
        self.assertIn("accounts_accessrole", out.getvalue())
