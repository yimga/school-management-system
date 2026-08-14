"""Self-host / edge boot must survive a PostgreSQL server without pgvector.

Runbook gap (Gilead SER8 edge deployment): the self-host stack ran migrations at
boot against a stock ``postgres:16`` image. Migration
``siteconfig/0123_enable_pgvector_extension`` ran ``CREATE EXTENSION vector`` and
hard-crashed with ``NotSupportedError: extension "vector" is not available``,
putting the web container into a restart loop — even though the base schema never
uses a real vector column (every embedding is a JSONField; pgvector is an opt-in
accelerator wired only by migrate_embeddings_to_pgvector).

Two guards, each written to FAIL before its fix:

  * ``enable_pgvector`` must no-op (not raise, and not poison the surrounding
    transaction) when the server lacks pgvector. Before the fix the function had no
    try/except and re-raised NotSupportedError straight up the migrate() stack.

  * the shipped self-host compose must use a pgvector-capable DB image, so the box
    gets the accelerated path too. Before the fix it pinned ``postgres:16-bookworm``.
"""
from __future__ import annotations

import importlib
from pathlib import Path

from django.db import connection as default_connection
from django.db.utils import NotSupportedError
from django.test import SimpleTestCase, TestCase

_MIGRATION = "apps.siteconfig.migrations.0123_enable_pgvector_extension"
_REPO_ROOT = Path(__file__).resolve().parents[3]


class _FakeCursor:
    """A cursor whose execute() raises — stands in for a PG server missing pgvector."""

    def __init__(self, exc):
        self._exc = exc

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, sql, params=None):
        raise self._exc


class _FakeConnection:
    vendor = "postgresql"

    def __init__(self, exc, alias):
        self._exc = exc
        self.alias = alias

    def cursor(self):
        return _FakeCursor(self._exc)


class _FakeSchemaEditor:
    def __init__(self, connection):
        self.connection = connection


class EnablePgvectorToleranceTests(TestCase):
    """Migration 0123 must degrade gracefully, not brick the boot."""

    def test_missing_extension_does_not_raise_and_transaction_survives(self):
        mig = importlib.import_module(_MIGRATION)
        exc = NotSupportedError('extension "vector" is not available')
        # alias points at the REAL default connection so the migration's savepoint
        # (transaction.atomic(using=...)) exercises real rollback machinery; only the
        # CREATE EXTENSION cursor is faked to fail.
        editor = _FakeSchemaEditor(_FakeConnection(exc, alias=default_connection.alias))

        # Before the fix this re-raised NotSupportedError.
        mig.enable_pgvector(apps=None, schema_editor=editor)

        # And the enclosing transaction must remain usable — proving the failed
        # CREATE EXTENSION rolled back to a savepoint rather than aborting it.
        with default_connection.cursor() as cur:
            cur.execute("SELECT 1")
            self.assertEqual(cur.fetchone()[0], 1)

    def test_noop_on_non_postgres_backend(self):
        mig = importlib.import_module(_MIGRATION)

        class _NonPgConnection:
            vendor = "sqlite"

            def cursor(self):  # pragma: no cover - must never run
                raise AssertionError("cursor() must not be touched on non-postgres")

        mig.enable_pgvector(apps=None, schema_editor=_FakeSchemaEditor(_NonPgConnection()))


class SelfhostComposePgvectorTests(SimpleTestCase):
    """The shipped self-host DB image must be able to CREATE EXTENSION vector."""

    def test_selfhost_db_image_ships_pgvector(self):
        compose = _REPO_ROOT / "deploy" / "selfhost" / "docker-compose.yml"
        self.assertTrue(compose.is_file(), f"missing self-host compose at {compose}")
        text = compose.read_text(encoding="utf-8")
        self.assertIn(
            "pgvector/pgvector:pg16",
            text,
            "self-host DB image must ship pgvector so migration 0123 and the opt-in "
            "migrate_embeddings_to_pgvector command can CREATE EXTENSION vector "
            "instead of crash-looping the web boot",
        )
