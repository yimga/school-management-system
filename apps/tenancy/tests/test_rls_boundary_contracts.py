"""RLS boundary contracts: FORCE migration, session GUC helpers, engine differences."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.db import connection
from django.test import SimpleTestCase, TestCase, tag

from apps.schools.rls import should_apply_rls
from apps.schools.rls_context import rls_bypass, rls_school


@tag("tenants_rls")
class RlsBoundaryContractTests(SimpleTestCase):
    def test_force_rls_migration_present(self):
        mig_dir = Path(settings.BASE_DIR) / "apps" / "schools" / "migrations"
        names = {p.name for p in mig_dir.glob("*.py")}
        self.assertTrue(
            any(n.startswith("0048_force_rls") for n in names),
            "expected apps/schools/migrations/0048_force_rls_on_all_enabled_tables.py",
        )

    def test_tenancy_mode_documented_in_settings(self):
        mode = getattr(settings, "TENANCY_MODE", None)
        self.assertIn(mode, ("SCHEMA", "RLS"))

    def test_sqlite_skips_rls_session_gucs(self):
        """Local SQLite dev does not set Postgres GUCs — documented proof difference."""
        if connection.vendor == "sqlite":
            with rls_school(1):
                pass
            self.assertFalse(should_apply_rls(connection))

    def test_postgres_rls_applies_only_when_not_schema_per_tenant(self):
        if connection.vendor != "postgresql":
            self.skipTest("Postgres-only RLS contract check")
        expected = not getattr(settings, "USE_DJANGO_TENANTS", False)
        self.assertEqual(should_apply_rls(connection), expected)


@tag("tenants_rls")
class RlsSessionGucTests(TestCase):
    databases = {"default"}

    def test_rls_bypass_context_manager_exits_cleanly(self):
        with rls_bypass():
            pass

    def test_rls_school_rejects_forged_tenant_id_string(self):
        from django.db import connection

        from apps.schools.rls_context import set_rls_school_id

        if connection.vendor != "postgresql":
            self.skipTest("Postgres-only GUC validation")
        with self.assertRaises(ValueError):
            set_rls_school_id("  ")
