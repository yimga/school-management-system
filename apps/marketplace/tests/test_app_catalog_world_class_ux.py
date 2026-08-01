from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class AppCatalogWorldClassUXTests(SimpleTestCase):
    def test_platform_and_tenant_catalogs_show_governed_install_context(self):
        for rel in ("templates/marketplace/app_catalog.html", "templates/marketplace/tenant_app_catalog.html"):
            with self.subTest(rel=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                # Both catalogs now use the shared operational-center frame; the
                # retired marketing-style hero is not the product shell owner.
                self.assertIn("rmc_operational_center_frame.html", text)
                self.assertRegex(text, "scopes|Scopes|Permission|permission")
                self.assertRegex(text, "sandbox|Sandbox")
                self.assertRegex(text, "billing|Billing")
                self.assertRegex(text, "install impact|Install impact|impact")
                self.assertRegex(text, "webhook|Webhook")
                self.assertRegex(text, "rollback|Rollback|uninstall|Uninstall")
                self.assertIn("external", text.lower())
