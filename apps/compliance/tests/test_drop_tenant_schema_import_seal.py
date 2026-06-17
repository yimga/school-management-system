"""Regression seal: drop_tenant_schema_for_school must reach the real tenant-mode helper.

Bug (2026-06-17 gap analysis): the function imported ``use_django_tenants`` from a
PHANTOM module ``apps.platform_runtime.tenant_mode`` inside a ``try/except ImportError``
that silently ``return None`` — so on hard-purge the tenant Postgres schema was NEVER
dropped in production. The import-reference-integrity CI gate cannot catch this class
because it deliberately excuses imports guarded by ``try/except ImportError``. Hence this
behavioural regression test.
"""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings


class DropTenantSchemaImportSealTests(SimpleTestCase):
    def test_use_django_tenants_resolves_from_domain_sync(self):
        # The canonical helper lives here; the old phantom module does not define it.
        from apps.schools.domain_sync import use_django_tenants

        self.assertTrue(callable(use_django_tenants))
        with self.assertRaises(ModuleNotFoundError):
            __import__("apps.platform_runtime.tenant_mode")

    @override_settings(USE_DJANGO_TENANTS=True)
    def test_drop_schema_passes_the_import_guard(self):
        """With tenant mode ON, the function must get PAST the import guard.

        Pre-fix it returned None at the import line (ImportError on the phantom module).
        Post-fix it proceeds to the Client lookup; we mock Client to have no row, so it
        returns None for the *no-client* reason — proving the import resolved.
        """
        from apps.compliance import tenant_offboarding_inventory as mod

        school = MagicMock(pk=123, tenant_client=None)
        fake_client_mgr = MagicMock()
        fake_client_mgr.objects.filter.return_value.first.return_value = None
        with patch("apps.customers.models.Client", fake_client_mgr):
            result = mod.drop_tenant_schema_for_school(school)
        # Reached the client lookup (no row) -> None, NOT the import-failure None.
        self.assertIsNone(result)
        fake_client_mgr.objects.filter.assert_called_once()
