"""
Tests for run_tenant_migrations management command (deploy flow).

Single entry point for tenant schema migrations: ensure_tenant_schemas then
migrate_schemas --tenant. See docs/MASTER_TABLE_LIST.md.
Uses SimpleTestCase + mocks; no database or real tenant required.
"""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase


class RunTenantMigrationsCommandTests(SimpleTestCase):
    """Regression tests for run_tenant_migrations deploy flow."""

    def test_skips_when_not_postgresql(self):
        with patch(
            "apps.schools.management.commands.run_tenant_migrations.connection"
        ) as conn:
            conn.vendor = "sqlite"
            out = StringIO()
            call_command("run_tenant_migrations", stdout=out, no_input=True)
            self.assertIn("PostgreSQL only", out.getvalue())
            # Should not have attempted ensure_tenant_schemas or migrate_schemas
            conn.cursor.assert_not_called()

    def test_skips_when_use_django_tenants_false(self):
        with (
            patch(
                "apps.schools.management.commands.run_tenant_migrations.connection"
            ) as conn,
            patch(
                "apps.schools.management.commands.run_tenant_migrations.settings"
            ) as settings,
        ):
            conn.vendor = "postgresql"
            settings.USE_DJANGO_TENANTS = False
            out = StringIO()
            call_command("run_tenant_migrations", stdout=out, no_input=True)
            self.assertIn("USE_DJANGO_TENANTS", out.getvalue())

    def test_calls_ensure_then_migrate_schemas_when_enabled(self):
        with (
            patch(
                "apps.schools.management.commands.run_tenant_migrations.connection"
            ) as conn,
            patch(
                "apps.schools.management.commands.run_tenant_migrations.settings"
            ) as settings,
            patch(
                "apps.schools.management.commands.run_tenant_migrations.call_command"
            ) as mock_call,
        ):
            conn.vendor = "postgresql"
            settings.USE_DJANGO_TENANTS = True
            out = StringIO()
            call_command("run_tenant_migrations", stdout=out, no_input=True)
            self.assertIn("Done.", out.getvalue())
            # First ensure_tenant_schemas, then migrate_schemas --tenant
            self.assertGreaterEqual(mock_call.call_count, 2)
            calls = [c[0][0] for c in mock_call.call_args_list]
            self.assertIn("ensure_tenant_schemas", calls)
            self.assertIn("migrate_schemas", calls)
            migrate_call = next(
                c for c in mock_call.call_args_list if c[0][0] == "migrate_schemas"
            )
            self.assertIn("--tenant", migrate_call[0])

    def test_skip_ensure_schemas_only_runs_migrate_schemas(self):
        with (
            patch(
                "apps.schools.management.commands.run_tenant_migrations.connection"
            ) as conn,
            patch(
                "apps.schools.management.commands.run_tenant_migrations.settings"
            ) as settings,
            patch(
                "apps.schools.management.commands.run_tenant_migrations.call_command"
            ) as mock_call,
        ):
            conn.vendor = "postgresql"
            settings.USE_DJANGO_TENANTS = True
            out = StringIO()
            call_command(
                "run_tenant_migrations",
                "--skip-ensure-schemas",
                stdout=out,
                no_input=True,
            )
            self.assertIn("Done.", out.getvalue())
            # Only migrate_schemas, not ensure_tenant_schemas
            self.assertEqual(mock_call.call_count, 1)
            self.assertEqual(mock_call.call_args[0][0], "migrate_schemas")
