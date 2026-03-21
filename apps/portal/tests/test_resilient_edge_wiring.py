"""RESILIENT_EDGE: form-draft-save.js must load where FormDraftSave.init is used; critical-read JS + timetable/contacts hooks."""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class ResilientEdgeFormDraftTemplateTests(SimpleTestCase):
    """Regression: init() without the library script was a silent no-op."""

    def _read(self, *parts: str) -> str:
        return (Path(settings.BASE_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_support_request_loads_form_draft_script_before_init(self):
        text = self._read("templates", "portal", "support_request.html")
        self.assertIn("form-draft-save.js", text)
        self.assertIn("FormDraftSave.init", text)
        idx_lib = text.index("form-draft-save.js")
        idx_init = text.index("FormDraftSave.init")
        self.assertLess(idx_lib, idx_init)

    def test_contact_school_loads_form_draft_script_before_init(self):
        text = self._read("templates", "parent", "contact_school.html")
        self.assertIn("form-draft-save.js", text)
        idx_lib = text.index("form-draft-save.js")
        idx_init = text.index("FormDraftSave.init")
        self.assertLess(idx_lib, idx_init)

    def test_request_detail_loads_form_draft_script_before_init(self):
        text = self._read("templates", "requests", "detail.html")
        self.assertIn("form-draft-save.js", text)
        idx_lib = text.index("form-draft-save.js")
        idx_init = text.index("FormDraftSave.init")
        self.assertLess(idx_lib, idx_init)

    def test_access_denied_loads_form_draft_script_before_init(self):
        text = self._read("templates", "requests", "access_denied.html")
        self.assertIn("form-draft-save.js", text)
        idx_lib = text.index("form-draft-save.js")
        idx_init = text.index("FormDraftSave.init")
        self.assertLess(idx_lib, idx_init)

    def test_super_audit_export_loads_form_draft_script_before_init(self):
        text = self._read("templates", "schools", "super_audit_export.html")
        self.assertIn("form-draft-save.js", text)
        self.assertIn("FormDraftSave.init", text)
        self.assertIn('data-draft-key="super_audit_export_', text)
        idx_lib = text.index("form-draft-save.js")
        idx_init = text.index("FormDraftSave.init")
        self.assertLess(idx_lib, idx_init)


class ResilientEdgeCriticalReadTests(SimpleTestCase):
    def _read(self, *parts: str) -> str:
        return (Path(settings.BASE_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_critical_read_js_exists(self):
        p = Path(settings.BASE_DIR) / "static" / "js" / "critical-read-degraded.js"
        self.assertTrue(p.is_file())
        body = p.read_text(encoding="utf-8")
        self.assertIn("data-sms-offline-read-cache-key", body)

    def test_portal_base_includes_critical_read_script(self):
        text = self._read("templates", "portal_base.html")
        self.assertIn("critical-read-degraded.js", text)

    def test_teacher_timetable_has_offline_cache_key(self):
        text = self._read("templates", "teacher", "timetable.html")
        self.assertIn("data-sms-offline-read-cache-key", text)
        self.assertIn("teacher_timetable_", text)
        self.assertIn('scope="col"', text)

    def test_parent_dashboard_widgets_timetable_and_contacts_cache_keys(self):
        text = self._read("templates", "widgets", "parent_dashboard_widgets.html")
        self.assertIn('data-sms-offline-read-cache-key="parent_timetable_', text)
        self.assertIn('data-sms-offline-read-cache-key="parent_contacts_', text)

    def test_ops_pos_template_has_tax_and_form_draft(self):
        text = self._read("templates", "schoolops", "ops_pos.html")
        self.assertIn("tax_rate_percent", text)
        self.assertIn("form-draft-save.js", text)
        self.assertIn('data-draft-key="pos_sale_line_', text)
        self.assertIn('scope="col"', text)
