"""Regression: sync_engine tenant tables have ENABLE + FORCE + default-deny.

scan_rls_force_coverage keys on convention filenames. The FORCE statement is
asserted here so a later edit cannot drop it and re-open the table-owner bypass.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from django.test import SimpleTestCase

_ENABLE_MOD = "apps.sync_engine.migrations.0008_enable_rls_postgresql"
_DENY_MOD = "apps.sync_engine.migrations.0009_rls_policy_default_deny"

_EXPECTED_TABLES = (
    "sync_engine_syncapplyledger",
    "sync_engine_edgesyncrun",
    "sync_engine_edgesynccursor",
    "sync_engine_edgesyncdirective",
    "sync_engine_synctombstone",
    "sync_engine_syncbundlereceipt",
    "sync_engine_syncfiletransfer",
)


class _FakeCursor:
    def __init__(self, sink):
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, *args):
        self._sink.append(sql)


class _FakeConn:
    def __init__(self, sink):
        self._sink = sink

    def cursor(self):
        return _FakeCursor(self._sink)


class SyncEngineRlsCoverageTests(SimpleTestCase):
    def test_convention_migration_filenames_present(self):
        import apps.sync_engine as pkg

        names = [p.name for p in (Path(pkg.__file__).parent / "migrations").glob("*.py")]
        self.assertTrue(any("enable_rls" in n for n in names), names)
        self.assertTrue(any("rls_policy_default_deny" in n for n in names), names)

    def test_enable_migration_issues_force_and_enable_for_all_tenant_tables(self):
        mod = importlib.import_module(_ENABLE_MOD)
        executed: list[str] = []
        orig_should, orig_conn = mod.should_apply_rls, mod.connection
        mod.should_apply_rls = lambda conn: True
        mod.connection = _FakeConn(executed)
        try:
            mod.enable_and_force_rls(None, None)
        finally:
            mod.should_apply_rls, mod.connection = orig_should, orig_conn
        joined = " ".join(executed).upper()
        self.assertIn("ENABLE ROW LEVEL SECURITY", joined)
        self.assertIn("FORCE ROW LEVEL SECURITY", joined)
        for table in _EXPECTED_TABLES:
            self.assertIn(table.upper(), joined, table)

    def test_default_deny_creates_a_policy_per_table(self):
        mod = importlib.import_module(_DENY_MOD)
        executed: list[str] = []
        orig_should, orig_conn = mod.should_apply_rls, mod.connection
        mod.should_apply_rls = lambda conn: True
        mod.connection = _FakeConn(executed)
        try:
            mod.apply_default_deny(None, None)
        finally:
            mod.should_apply_rls, mod.connection = orig_should, orig_conn
        joined = " ".join(executed).upper()
        self.assertIn("CREATE POLICY", joined)
        for table in _EXPECTED_TABLES:
            self.assertIn(table.upper(), joined, table)
            self.assertIn(f"SYNC_ENGINE_TENANT_{table.replace('sync_engine_', '').upper()}", joined)
