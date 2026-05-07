from django.test import SimpleTestCase

from apps.platform_runtime.app_catalog_governance import build_scope_consent


class AppScopeConsentTests(SimpleTestCase):
    def test_scope_consent_exposes_data_billing_webhook_and_uninstall_impact(self):
        consent = build_scope_consent(
            {
                "app_key": "attendance-recovery",
                "scopes": ["attendance:read", "students:write"],
                "billing_model": "usage",
                "webhooks": ["attendance.absent"],
            }
        )

        self.assertTrue(consent["consent_required"])
        self.assertEqual(consent["data_access"], ["attendance", "students"])
        self.assertEqual(consent["billing_impact"], "usage")
        self.assertIn("attendance.absent", consent["webhook_impact"])
        self.assertEqual(consent["uninstall_posture"], "revoke_scopes_disable_webhooks_preserve_audit")
