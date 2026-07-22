"""Fix D — tenant migrate lock_timeout wiring + session hygiene."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings


class TenantMigrateLockTimeoutTests(SimpleTestCase):
    def test_settings_default_is_positive(self):
        from apps.schools.onboarding_service import _tenant_migrate_lock_timeout_ms

        with override_settings(TENANT_MIGRATE_LOCK_TIMEOUT_MS=45000):
            self.assertEqual(_tenant_migrate_lock_timeout_ms(), 45000)

    def test_zero_disables(self):
        from apps.schools.onboarding_service import _tenant_migrate_lock_timeout_ms

        with override_settings(TENANT_MIGRATE_LOCK_TIMEOUT_MS=0):
            self.assertEqual(_tenant_migrate_lock_timeout_ms(), 0)

    def test_set_lock_timeout_postgres_executes_set(self):
        from apps.schools.onboarding_service import _set_lock_timeout

        cursor = MagicMock()
        conn = MagicMock()
        conn.vendor = "postgresql"
        conn.cursor.return_value.__enter__.return_value = cursor
        conn.cursor.return_value.__exit__.return_value = False

        with patch("django.db.connection", conn):
            _set_lock_timeout(30000)
            cursor.execute.assert_called_once_with("SET lock_timeout = 30000")

            cursor.reset_mock()
            _set_lock_timeout(None)
            cursor.execute.assert_called_once_with("SET lock_timeout = DEFAULT")

    def test_set_lock_timeout_noop_on_sqlite(self):
        from apps.schools.onboarding_service import _set_lock_timeout

        cursor = MagicMock()
        conn = MagicMock()
        conn.vendor = "sqlite"
        conn.cursor.return_value.__enter__.return_value = cursor

        with patch("django.db.connection", conn):
            _set_lock_timeout(30000)
            cursor.execute.assert_not_called()

    def test_run_tenant_migrations_sets_and_resets_on_success(self):
        from apps.schools import onboarding_service as obs

        client = MagicMock()
        client.schema_name = "demo"

        with (
            patch.object(obs, "use_django_tenants", return_value=True),
            patch("django_tenants.utils.tenant_context") as tc,
            patch("django.core.management.call_command") as call_cmd,
            patch.object(obs, "_tenant_migrate_lock_timeout_ms", return_value=12000),
            patch.object(obs, "_set_lock_timeout") as set_lock,
            patch.object(obs, "_discard_connection") as discard,
        ):
            tc.return_value.__enter__.return_value = None
            tc.return_value.__exit__.return_value = False
            obs._run_tenant_migrations(client)

        call_cmd.assert_called_once()
        self.assertEqual(set_lock.call_args_list[0].args, (12000,))
        self.assertEqual(set_lock.call_args_list[1].args, (None,))
        discard.assert_not_called()

    def test_run_tenant_migrations_discards_connection_on_failure(self):
        from apps.schools import onboarding_service as obs
        from django.db import DatabaseError

        client = MagicMock()
        client.schema_name = "demo"

        with (
            patch.object(obs, "use_django_tenants", return_value=True),
            patch("django_tenants.utils.tenant_context") as tc,
            patch(
                "django.core.management.call_command",
                side_effect=DatabaseError("lock timeout"),
            ),
            patch.object(obs, "_tenant_migrate_lock_timeout_ms", return_value=5000),
            patch.object(obs, "_set_lock_timeout") as set_lock,
            patch.object(obs, "_discard_connection") as discard,
        ):
            tc.return_value.__enter__.return_value = None
            tc.return_value.__exit__.return_value = False
            with self.assertRaises(DatabaseError):
                obs._run_tenant_migrations(client)

        self.assertEqual(set_lock.call_args_list[0].args, (5000,))
        discard.assert_called_once()
