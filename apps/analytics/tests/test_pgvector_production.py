"""Tests for production-scale pgvector tooling: hardened migrate cmd +
verify_pgvector_index + rebuild_pgvector_index.

These don't actually run pgvector SQL — the test DB is sqlite. Tests
cover: refusal-when-not-postgres, auto-tune math, dim-mismatch
detection (mocked), batched backfill loop (mocked cursor).
"""

from __future__ import annotations

import unittest.mock as mock
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase


class AutoTuneListsMathTests(SimpleTestCase):
    def test_migrate_cmd_auto_lists_math(self):
        from apps.analytics.management.commands import (
            migrate_embeddings_to_pgvector as mod,
        )
        cmd = mod.Command()
        self.assertEqual(cmd._auto_lists(0), 50)        # floor
        self.assertEqual(cmd._auto_lists(2500), 50)     # sqrt(2500)=50
        self.assertEqual(cmd._auto_lists(5000), 71)     # ceil(sqrt(5000))
        self.assertEqual(cmd._auto_lists(50_000), 224)
        self.assertEqual(cmd._auto_lists(1_000_000), 1000)
        self.assertEqual(cmd._auto_lists(100_000_000), 5000)  # capped

    def test_rebuild_cmd_auto_lists_math(self):
        from apps.analytics.management.commands import (
            rebuild_pgvector_index as mod,
        )
        cmd = mod.Command()
        self.assertEqual(cmd._auto_lists(0), 50)
        self.assertEqual(cmd._auto_lists(5000), 71)
        self.assertEqual(cmd._auto_lists(100_000_000), 5000)


class SkipEmptyStoreTests(TestCase):
    """Fresh deploys with no embeddings must not fail predeploy."""

    def test_migrate_skips_when_no_rows_and_no_dimensions(self):
        from apps.analytics.management.commands import (
            migrate_embeddings_to_pgvector as mod,
        )
        out = StringIO()
        with mock.patch.object(mod.connection, "vendor", "postgresql"), \
             mock.patch.object(
                 mod.Command, "_count_indexable_rows", return_value=0,
             ), \
             mock.patch.object(
                 mod.Command, "_detect_dimensions", return_value=None,
             ):
            call_command("migrate_embeddings_to_pgvector", stdout=out)
        self.assertIn("Skipping pgvector migration", out.getvalue())

    def test_verify_strict_passes_when_no_rows(self):
        from apps.analytics.management.commands import (
            verify_pgvector_index as mod,
        )
        out = StringIO()
        with mock.patch.object(mod.connection, "vendor", "postgresql"), \
             mock.patch.object(
                 mod.Command, "_indexable_row_count", return_value=0,
             ):
            call_command(
                "verify_pgvector_index", "--strict", stdout=out,
            )
        self.assertIn("skipped", out.getvalue())


class VendorRefusalTests(TestCase):
    """All three commands must refuse when not running on PostgreSQL."""

    def test_migrate_refuses_on_sqlite(self):
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "migrate_embeddings_to_pgvector",
                "--dimensions", "384",
                stdout=StringIO(),
            )
        self.assertIn("pgvector requires PostgreSQL", str(ctx.exception))

    def test_verify_refuses_on_sqlite(self):
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "verify_pgvector_index",
                stdout=StringIO(),
            )
        self.assertIn("pgvector verification requires PostgreSQL", str(ctx.exception))

    def test_rebuild_refuses_on_sqlite(self):
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "rebuild_pgvector_index",
                stdout=StringIO(),
            )
        self.assertIn("pgvector requires PostgreSQL", str(ctx.exception))


class DimMismatchTests(TestCase):
    """When connection.vendor=postgresql and existing_dim != current_dim, refuse."""

    def test_refuses_without_force_drop(self):
        from apps.analytics.management.commands import (
            migrate_embeddings_to_pgvector as mod,
        )
        with mock.patch.object(mod.connection, "vendor", "postgresql"), \
             mock.patch.object(
                 mod.Command, "_detect_dimensions", return_value=768,
             ), \
             mock.patch.object(
                 mod.Command, "_count_indexable_rows", return_value=10_000,
             ), \
             mock.patch.object(
                 mod.Command, "_existing_column_dim", return_value=384,
             ):
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "migrate_embeddings_to_pgvector",
                    stdout=StringIO(),
                )
        self.assertIn("dim=384", str(ctx.exception))
        self.assertIn("dim=768", str(ctx.exception))
        self.assertIn("--force-drop-column", str(ctx.exception))

    def test_proceeds_with_force_drop(self):
        from apps.analytics.management.commands import (
            migrate_embeddings_to_pgvector as mod,
        )
        with mock.patch.object(mod.connection, "vendor", "postgresql"), \
             mock.patch.object(
                 mod.Command, "_detect_dimensions", return_value=768,
             ), \
             mock.patch.object(
                 mod.Command, "_count_indexable_rows", return_value=10_000,
             ), \
             mock.patch.object(
                 mod.Command, "_existing_column_dim", return_value=384,
             ), \
             mock.patch.object(mod.Command, "_exec") as exec_mock, \
             mock.patch.object(mod.Command, "_exec_each"), \
             mock.patch.object(mod.Command, "_batched_backfill"):
            call_command(
                "migrate_embeddings_to_pgvector",
                "--force-drop-column", "--dimensions", "768",
                stdout=StringIO(),
            )
        # Two _exec calls expected for the drop sequence (DROP INDEX + DROP COLUMN).
        sql_strs = " | ".join(c.args[0] for c in exec_mock.call_args_list)
        self.assertIn("DROP INDEX", sql_strs)
        self.assertIn("DROP COLUMN", sql_strs)


class BatchedBackfillLoopTests(TestCase):
    """Exercise the batch loop logic without touching a real DB."""

    def test_loop_stops_when_rowcount_below_batch(self):
        from apps.analytics.management.commands import (
            migrate_embeddings_to_pgvector as mod,
        )
        # Two iterations: first returns 1000 rows, second returns 250.
        cursor_mock = mock.MagicMock()
        cursor_mock.rowcount = 1000

        def _exec_side_effect(sql):
            cursor_mock.rowcount = 1000 if _exec_side_effect.calls == 0 else 250
            _exec_side_effect.calls += 1
        _exec_side_effect.calls = 0
        cursor_mock.execute.side_effect = _exec_side_effect

        ctx_mock = mock.MagicMock()
        ctx_mock.__enter__ = mock.MagicMock(return_value=cursor_mock)
        ctx_mock.__exit__ = mock.MagicMock(return_value=False)

        with mock.patch.object(
            mod.connection, "cursor", return_value=ctx_mock,
        ), mock.patch.object(mod, "transaction") as tx_mock:
            atomic_ctx = mock.MagicMock()
            atomic_ctx.__enter__ = mock.MagicMock(return_value=None)
            atomic_ctx.__exit__ = mock.MagicMock(return_value=False)
            tx_mock.atomic.return_value = atomic_ctx
            cmd = mod.Command()
            cmd.stdout = StringIO()
            cmd._batched_backfill(batch_size=1000)
        # Loop should have run exactly twice (1000 then 250 < batch_size → stop).
        self.assertEqual(_exec_side_effect.calls, 2)


class VerifyPgvectorTests(TestCase):
    """Exercise verify command on a sqlite DB via mocked vendor."""

    def test_strict_exits_on_missing_extension(self):
        from apps.analytics.management.commands import (
            verify_pgvector_index as mod,
        )
        # Mock cursor to return None for extension query.
        cursor_mock = mock.MagicMock()
        cursor_mock.fetchone.return_value = None
        cursor_mock.fetchall.return_value = []
        ctx_mock = mock.MagicMock()
        ctx_mock.__enter__ = mock.MagicMock(return_value=cursor_mock)
        ctx_mock.__exit__ = mock.MagicMock(return_value=False)

        with mock.patch.object(mod.connection, "vendor", "postgresql"), \
             mock.patch.object(mod.connection, "cursor", return_value=ctx_mock), \
             mock.patch.object(
                 mod.Command, "_indexable_row_count", return_value=1,
             ):
            with self.assertRaises(SystemExit) as cm:
                call_command(
                    "verify_pgvector_index", "--strict",
                    stdout=StringIO(),
                )
            self.assertEqual(cm.exception.code, 1)

    def test_json_output_shape(self):
        from apps.analytics.management.commands import (
            verify_pgvector_index as mod,
        )
        cursor_mock = mock.MagicMock()
        cursor_mock.fetchone.side_effect = [
            ("0.5.0",),       # extension
            (768,),            # column atttypmod
            ("idx", "CREATE INDEX idx ON ..."),  # index
            (768,),            # column atttypmod (re-read in _check_explain)
            (10000,),          # row count
            (0,),              # null_vec_with_json
        ]
        cursor_mock.fetchall.return_value = [
            ("Index Scan using aiembedding_vec_ivfflat",),
        ]
        ctx_mock = mock.MagicMock()
        ctx_mock.__enter__ = mock.MagicMock(return_value=cursor_mock)
        ctx_mock.__exit__ = mock.MagicMock(return_value=False)

        out = StringIO()
        with mock.patch.object(mod.connection, "vendor", "postgresql"), \
             mock.patch.object(mod.connection, "cursor", return_value=ctx_mock):
            call_command(
                "verify_pgvector_index", "--json", stdout=out,
            )
        import json
        payload = json.loads(out.getvalue())
        names = [r["check"] for r in payload]
        self.assertEqual(names, [
            "extension_loaded", "vector_column", "ivfflat_index",
            "explain_uses_index", "row_stats",
        ])


class RebuildPgvectorTests(TestCase):
    def test_refuses_when_column_missing(self):
        from apps.analytics.management.commands import (
            rebuild_pgvector_index as mod,
        )
        cursor_mock = mock.MagicMock()
        cursor_mock.fetchone.return_value = None  # column query returns nothing
        ctx_mock = mock.MagicMock()
        ctx_mock.__enter__ = mock.MagicMock(return_value=cursor_mock)
        ctx_mock.__exit__ = mock.MagicMock(return_value=False)

        with mock.patch.object(mod.connection, "vendor", "postgresql"), \
             mock.patch.object(mod.connection, "cursor", return_value=ctx_mock):
            with self.assertRaises(CommandError) as ctx:
                call_command("rebuild_pgvector_index", stdout=StringIO())
        self.assertIn("embedding_vec column doesn't exist", str(ctx.exception))

    def test_dry_run_emits_drop_and_create(self):
        from apps.analytics.management.commands import (
            rebuild_pgvector_index as mod,
        )
        cursor_mock = mock.MagicMock()
        cursor_mock.fetchone.side_effect = [
            (1,),        # column exists
            (5000,),     # row count
        ]
        ctx_mock = mock.MagicMock()
        ctx_mock.__enter__ = mock.MagicMock(return_value=cursor_mock)
        ctx_mock.__exit__ = mock.MagicMock(return_value=False)

        out = StringIO()
        with mock.patch.object(mod.connection, "vendor", "postgresql"), \
             mock.patch.object(mod.connection, "cursor", return_value=ctx_mock):
            call_command(
                "rebuild_pgvector_index", "--dry-run",
                stdout=out,
            )
        text = out.getvalue()
        self.assertIn("DROP INDEX", text)
        self.assertIn("CREATE INDEX", text)
        # For 5000 rows, lists=ceil(sqrt(5000))=71.
        self.assertIn("lists = 71", text)
