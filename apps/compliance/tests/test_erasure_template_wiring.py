"""Compliance erasure form: draft-save + i18n wiring (template regression)."""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class ErasureRequestTemplateTests(SimpleTestCase):
    def test_template_loads_form_draft_and_draft_key(self):
        text = (
            Path(settings.BASE_DIR)
            / "templates"
            / "compliance"
            / "erasure_request.html"
        ).read_text(encoding="utf-8")
        self.assertIn("form-draft-save.js", text)
        self.assertIn('data-draft-key="compliance_erasure_', text)
        self.assertIn("FormDraftSave.init", text)
        idx_lib = text.index("form-draft-save.js")
        idx_init = text.index("FormDraftSave.init")
        self.assertLess(idx_lib, idx_init)
