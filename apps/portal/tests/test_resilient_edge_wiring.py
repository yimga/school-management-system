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
        self.assertIn("<details", text)
        self.assertIn('dir="auto"', text)
        idx_lib = text.index("form-draft-save.js")
        idx_init = text.index("FormDraftSave.init")
        self.assertLess(idx_lib, idx_init)

    def test_contact_school_loads_form_draft_script_before_init(self):
        text = self._read("templates", "parent", "contact_school.html")
        self.assertIn("form-draft-save.js", text)
        self.assertIn("<details", text)
        self.assertIn('dir="auto"', text)
        idx_lib = text.index("form-draft-save.js")
        idx_init = text.index("FormDraftSave.init")
        self.assertLess(idx_lib, idx_init)

    def test_link_child_legacy_loads_form_draft_script_before_init(self):
        text = self._read("templates", "parent", "link_child.html")
        self.assertIn("form-draft-save.js", text)
        self.assertIn("link-child-legacy-form", text)
        self.assertIn("data-draft-key", text)
        idx_lib = text.index("form-draft-save.js")
        idx_init = text.index("FormDraftSave.init")
        self.assertLess(idx_lib, idx_init)

    def test_link_child_wizard_loads_form_draft_script_before_init(self):
        text = self._read("templates", "parent", "link_child_wizard.html")
        self.assertIn("form-draft-save.js", text)
        self.assertIn("link-child-wizard-form", text)
        self.assertIn("data-draft-key", text)
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

    def test_roll_call_student_loads_form_draft_script_before_init(self):
        text = self._read("templates", "portal", "roll_call_student.html")
        self.assertIn("form-draft-save.js", text)
        idx_lib = text.index("form-draft-save.js")
        idx_init = text.index("FormDraftSave.init")
        self.assertLess(idx_lib, idx_init)

    def test_roll_call_teacher_loads_form_draft_script_before_init(self):
        text = self._read("templates", "portal", "roll_call_teacher.html")
        self.assertIn("form-draft-save.js", text)
        idx_lib = text.index("form-draft-save.js")
        idx_init = text.index("FormDraftSave.init")
        self.assertLess(idx_lib, idx_init)

    def test_marks_entry_loads_form_draft_script_before_init(self):
        text = self._read("templates", "teacher", "marks_entry.html")
        self.assertIn("form-draft-save.js", text)
        idx_lib = text.index("form-draft-save.js")
        idx_init = text.index("FormDraftSave.init")
        self.assertLess(idx_lib, idx_init)

    def test_claim_invite_loads_form_draft_script_before_init(self):
        text = self._read("templates", "parent", "claim_invite.html")
        self.assertIn("form-draft-save.js", text)
        self.assertIn("claim-invite-form", text)
        self.assertIn("data-draft-key", text)
        self.assertIn('dir="auto"', text)
        idx_lib = text.index("form-draft-save.js")
        idx_init = text.index("FormDraftSave.init")
        self.assertLess(idx_lib, idx_init)

    def test_attendance_discipline_justification_loads_form_draft_script_before_init(self):
        text = self._read("templates", "parent", "attendance_discipline.html")
        self.assertIn("form-draft-save.js", text)
        self.assertIn("parent-attendance-justification-form", text)
        self.assertIn("data-draft-key", text)
        self.assertIn('scope="col"', text)
        self.assertIn('dir="auto"', text)
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
        self.assertIn("/kb/article/", text)
        self.assertIn("/kb/search", text)
        self.assertIn("/kb/category/", text)
        self.assertIn('path === "/kb"', text)
        self.assertIn("kb-article", text)
        self.assertIn("kb-search", text)
        self.assertIn("kb-category", text)
        self.assertIn("kb-home", text)
        self.assertIn("kb-hub", text)

    def test_teacher_timetable_has_offline_cache_key(self):
        text = self._read("templates", "teacher", "timetable.html")
        self.assertIn("data-sms-offline-read-cache-key", text)
        self.assertIn("teacher_timetable_", text)
        self.assertIn('scope="col"', text)

    def test_parent_dashboard_widgets_timetable_and_contacts_cache_keys(self):
        text = self._read("templates", "widgets", "parent_dashboard_widgets.html")
        self.assertIn('data-sms-offline-read-cache-key="parent_timetable_', text)
        self.assertIn('data-sms-offline-read-cache-key="parent_contacts_', text)

    def test_support_ticket_detail_has_critical_read_cache_key(self):
        text = self._read("templates", "portal", "support_ticket_detail.html")
        self.assertIn("data-sms-offline-read-cache-key", text)
        self.assertIn("portal_support_ticket", text)
        self.assertIn("data-page-critical-read", text)
        self.assertIn("support-ticket-heading", text)

    def test_support_request_has_critical_read_cache_key(self):
        text = self._read("templates", "portal", "support_request.html")
        self.assertIn("data-sms-offline-read-cache-key", text)
        self.assertIn("portal_support_request", text)
        self.assertIn("data-page-critical-read", text)
        self.assertIn("support-request-heading", text)

    def test_kb_article_has_critical_read_cache_key(self):
        text = self._read("templates", "portal", "kb_article.html")
        self.assertIn("data-sms-offline-read-cache-key", text)
        self.assertIn("portal_kb_article", text)
        self.assertIn("data-page-critical-read", text)
        self.assertIn("kb-article-heading", text)
        self.assertIn("page_archetype", text)
        self.assertIn("kb-article", text)

    def test_kb_home_has_critical_read_cache_key(self):
        text = self._read("templates", "portal", "kb_home.html")
        self.assertIn("portal_kb_home", text)
        self.assertIn("data-page-critical-read", text)
        self.assertIn("kb-home-heading", text)
        self.assertIn("kb-home", text)

    def test_kb_search_has_critical_read_cache_key(self):
        text = self._read("templates", "portal", "kb_search.html")
        self.assertIn("portal_kb_search", text)
        self.assertIn("data-page-critical-read", text)
        self.assertIn("kb-search-heading", text)

    def test_kb_category_has_critical_read_cache_key(self):
        text = self._read("templates", "portal", "kb_category.html")
        self.assertIn("portal_kb_category", text)
        self.assertIn("data-page-critical-read", text)
        self.assertIn("kb-category-heading", text)

    def test_ops_pos_template_has_tax_and_form_draft(self):
        text = self._read("templates", "schoolops", "ops_pos.html")
        self.assertIn("tax_rate_percent", text)
        self.assertIn("form-draft-save.js", text)
        self.assertIn('data-draft-key="pos_sale_line_', text)
        self.assertIn('scope="col"', text)
        self.assertIn("export=json", text)
