from django.test import SimpleTestCase

from apps.platform_runtime.app_catalog_governance import uninstall_plan


class AppUninstallRollbackTests(SimpleTestCase):
    def test_uninstall_revokes_scopes_disables_webhooks_and_preserves_audit(self):
        plan = uninstall_plan({"slug": "sms-connector"}, tenant_id="school-a")

        self.assertTrue(plan["rollback_supported"])
        self.assertIn("revoke_scopes", plan["steps"])
        self.assertIn("disable_webhooks", plan["steps"])
        self.assertIn("stop_usage_meter", plan["steps"])
        self.assertIn("preserve_audit", plan["steps"])
