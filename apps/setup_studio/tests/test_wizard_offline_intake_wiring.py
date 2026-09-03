from pathlib import Path

from django.test import SimpleTestCase

from apps.platform_runtime.offline_mode_bundle import (
    OFFLINE_MODE_BACKEND_FLAG_UPDATES,
)
from apps.siteconfig.tests._template_nodes import assert_markup


ROOT = Path(__file__).resolve().parents[3]
TENANT_WIZARD = Path(__file__).resolve().parents[3] / "templates/setup_studio/tenant_wizard.html"


class WizardOfflineIntakeWiringTests(SimpleTestCase):
    def test_offline_bundle_enables_wizard_intake(self):
        self.assertTrue(
            OFFLINE_MODE_BACKEND_FLAG_UPDATES["enable_offline_intake_wizard"]
        )

    def test_tenant_wizard_loads_encrypted_indexeddb_draft_runtime(self):
        template = (ROOT / "templates/setup_studio/tenant_wizard.html").read_text(
            encoding="utf-8"
        )
        # rmc-wizard-offline-intake.js mounts by querying for this attribute, so
        # it has to be on the emitted element; the two .js names below are
        # {% static %} arguments and stay reads.
        assert_markup(self, TENANT_WIZARD, "data-rmc-offline-intake")
        self.assertIn("data-rmc-offline-intake", template)
        self.assertIn("offline-crypto-wrapper.js", template)
        self.assertIn("rmc-wizard-offline-intake.js", template)

    def test_offline_database_has_wizard_draft_store(self):
        source = (ROOT / "static/js/offline-db.js").read_text(encoding="utf-8")
        self.assertIn("wizard_drafts:", source)
        self.assertIn("putWizardDraft", source)
        self.assertIn("deleteWizardDraft", source)
