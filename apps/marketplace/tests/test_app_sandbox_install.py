from django.test import SimpleTestCase

from apps.platform_runtime.app_catalog_governance import sandbox_install_plan


class AppSandboxInstallTests(SimpleTestCase):
    def test_sandbox_install_requires_payload_webhook_usage_and_audit_posture(self):
        plan = sandbox_install_plan(
            {
                "slug": "sms-connector",
                "billing_model": "usage",
                "webhooks": ["message.sent"],
                "test_payloads": ["message.sent.sample"],
            },
            tenant_id="school-a",
        )

        self.assertTrue(plan["sandbox_install"])
        self.assertTrue(plan["webhook_test_required"])
        self.assertTrue(plan["usage_test_required"])
        self.assertTrue(plan["audit_required"])
        self.assertEqual(plan["tenant_id"], "school-a")
