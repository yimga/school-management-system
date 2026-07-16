"""Regression guard: the studio_os ExperienceRegionApproval RLS migration must
ENABLE *and* FORCE row-level security.

Live FORCE enforcement is Postgres-only (proven in the tenants-rls CI lane); this
repo-side test drives the migration's RunPython with a fake cursor to assert it
issues the FORCE statement, so a future edit that drops FORCE (re-opening the
table-owner bypass the audit flagged) fails here rather than silently.
"""

import importlib
from pathlib import Path

from django.test import SimpleTestCase

_MOD = "apps.studio_os.migrations.0003_enable_rls_postgresql"


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


class StudioOsForceRlsMigrationTests(SimpleTestCase):
    def test_enable_migration_issues_force_and_enable(self):
        mod = importlib.import_module(_MOD)
        executed: list[str] = []
        orig_should, orig_conn = mod.should_apply_rls, mod.connection
        mod.should_apply_rls = lambda conn: True  # force the Postgres branch
        mod.connection = _FakeConn(executed)
        try:
            mod.enable_and_force_rls(None, None)
        finally:
            mod.should_apply_rls, mod.connection = orig_should, orig_conn
        joined = " ".join(executed).upper()
        self.assertIn("ENABLE ROW LEVEL SECURITY", joined)
        self.assertIn("FORCE ROW LEVEL SECURITY", joined)
        self.assertIn("STUDIO_OS_EXPERIENCEREGIONAPPROVAL", joined)

    def test_convention_migration_filenames_present(self):
        import apps.studio_os as pkg

        names = [p.name for p in (Path(pkg.__file__).parent / "migrations").glob("*.py")]
        # scan_rls_force_coverage keys on these substrings to consider the app covered.
        self.assertTrue(any("enable_rls" in n for n in names), names)
        self.assertTrue(
            any("rls_policy_default_deny" in n for n in names), names
        )
