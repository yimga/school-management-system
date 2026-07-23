"""Regression: `_run_tenant_migrations` must migrate ONLY the target tenant schema.

``django_tenants`` shadows Django's ``migrate`` command, so a flag-less
``call_command("migrate", "--run-syncdb")`` is actually ``MigrateSchemasCommand``
with no ``--tenant``/``--schema`` → its ``SyncCommon.handle`` expands to "sync
both", migrating ``public`` AND EVERY tenant schema in the database, inline, on
every provision. That is O(N tenants) of blocking DDL per school and — because the
standard executor has no per-tenant isolation — one broken sibling schema fails
every school's ``tenant_schema`` step deterministically (the "stuck at
tenant_schema, requeue loops forever" symptom). The fix scopes the migrate to the
single schema being provisioned.

These run in ANY tenancy mode (the helper's ``use_django_tenants`` guard is
patched), because the real single-schema behaviour only exercises under
``USE_DJANGO_TENANTS=1`` which CI never sets — so this call-shape regression is
the only automated guard against reintroducing the fan-out footgun.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.schools import onboarding_service


class RunTenantMigrationsSingleSchemaTests(SimpleTestCase):
    def _drive(self):
        client = MagicMock()
        client.schema_name = "s_deadbeefdeadbeefdeadbeefdeadbeef"
        with (
            patch.object(onboarding_service, "use_django_tenants", return_value=True),
            patch("django_tenants.utils.tenant_context"),
            patch.object(onboarding_service, "_set_lock_timeout"),
            patch.object(onboarding_service, "_discard_connection"),
            patch("django.core.management.call_command") as mock_call,
        ):
            onboarding_service._run_tenant_migrations(client)
        return mock_call, client

    def test_scopes_migrate_to_single_tenant_schema(self):
        mock_call, client = self._drive()
        self.assertTrue(mock_call.called, "migrate must be invoked in schema mode")
        # The command is migrate_schemas (django_tenants), scoped to THIS schema.
        self.assertEqual(mock_call.call_args[0][0], "migrate_schemas")
        kwargs = mock_call.call_args.kwargs
        self.assertEqual(kwargs.get("schema_name"), client.schema_name)
        self.assertTrue(kwargs.get("tenant"), "must pass tenant=True (single-tenant scope)")
        self.assertTrue(kwargs.get("run_syncdb"), "run_syncdb creates tables for app-less apps")

    def test_never_uses_flagless_migrate(self):
        mock_call, _ = self._drive()
        for call in mock_call.call_args_list:
            self.assertNotEqual(
                call[0][0],
                "migrate",
                "flag-less migrate fans out over public + ALL tenant schemas — "
                "the sibling-poison / O(N) regression this test guards against",
            )

    def test_noop_when_not_schema_mode(self):
        # RLS / CI mode (USE_DJANGO_TENANTS=0): the helper must not migrate at all.
        client = MagicMock()
        client.schema_name = "s_x"
        with (
            patch.object(onboarding_service, "use_django_tenants", return_value=False),
            patch("django.core.management.call_command") as mock_call,
        ):
            onboarding_service._run_tenant_migrations(client)
        mock_call.assert_not_called()
