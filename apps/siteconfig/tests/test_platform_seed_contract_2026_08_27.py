from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from apps.siteconfig.management.commands.bootstrap_platform_catalog import (
    BOOTSTRAP_STEPS,
)
from apps.siteconfig.management.commands.seed_platform_complete import (
    _ACCOUNT_STEPS,
    _TENANT_RECONCILIATION_STEPS,
    _VERIFY_STEPS,
)


class PlatformSeedOrchestrationContractTests(SimpleTestCase):
    def test_standard_bootstrap_contains_foundational_catalogs(self):
        commands = {row[0] for row in BOOTSTRAP_STEPS}
        self.assertTrue(
            {
                "seed_platform_registries",
                "seed_country_profiles",
                "seed_country_grading_profiles",
                "seed_subscription_catalog",
            }.issubset(commands)
        )

    def test_complete_seed_reconciles_every_tenant_and_fails_closed(self):
        tenant_commands = {row[0] for row in _TENANT_RECONCILIATION_STEPS}
        self.assertEqual(
            tenant_commands,
            {
                "reconcile_tenant_seed_baseline",
                "align_tenant_config",
                "backfill_country_baseline",
            },
        )
        self.assertIn(
            "verify_platform_seed_completeness",
            {row[0] for row in _VERIFY_STEPS},
        )

    def test_catalog_seed_never_resets_default_account_passwords(self):
        account_commands = {row[0] for row in _ACCOUNT_STEPS}
        self.assertNotIn("ensure_superadmin", account_commands)
        self.assertNotIn("ensure_default_tenant_admin", account_commands)
        self.assertEqual(account_commands, {"reconcile_access_catalog"})


class AccessCatalogReconciliationTests(TestCase):
    def test_repair_command_restores_role_templates_and_superadmin_coverage(self):
        from django.core.management import call_command

        from apps.accounts.models import AccessRole, Permission
        from apps.accounts.signals import ROLE_TEMPLATES

        AccessRole.objects.all().delete()
        Permission.objects.all().delete()
        call_command("reconcile_access_catalog", verbosity=0)

        expected_roles = {
            code for codes in ROLE_TEMPLATES.values() for code in codes
        }
        actual_roles = set(
            AccessRole.objects.filter(school__isnull=True).values_list(
                "code", flat=True
            )
        )
        self.assertTrue(expected_roles.issubset(actual_roles))
        superadmin = AccessRole.objects.get(code="SUPERADMIN", school__isnull=True)
        self.assertEqual(
            set(superadmin.permissions.values_list("id", flat=True)),
            set(Permission.objects.values_list("id", flat=True)),
        )
        self.assertGreaterEqual(Permission.objects.count(), 40)


class KnowledgeSeedIsolationTests(SimpleTestCase):
    @patch(
        "apps.portal.management.commands.seed_kb_articles.Command._handle_seed",
        return_value="ok",
    )
    def test_embedding_auto_refresh_is_disabled_only_during_seed(self, mocked_seed):
        from django.conf import settings
        from apps.portal.management.commands.seed_kb_articles import Command

        original = getattr(settings, "KB_EMBEDDING_AUTO_REFRESH", True)

        def assertion(*args, **kwargs):
            self.assertFalse(settings.KB_EMBEDDING_AUTO_REFRESH)
            return "ok"

        mocked_seed.side_effect = assertion
        self.assertEqual(Command().handle(), "ok")
        self.assertEqual(settings.KB_EMBEDDING_AUTO_REFRESH, original)
