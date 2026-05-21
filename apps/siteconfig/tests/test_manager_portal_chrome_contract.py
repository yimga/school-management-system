"""Manager corporate footer + tenant portal chrome template contracts."""

from pathlib import Path

from django.test import SimpleTestCase


class ManagerPortalChromeContractTests(SimpleTestCase):
    def test_control_plane_skeleton_wires_compact_operator_footer(self):
        text = Path("templates/control_plane_skeleton.html").read_text(encoding="utf-8")
        self.assertIn("SHOW_MANAGER_CORPORATE_FOOTER", text)
        self.assertIn("cp-corporate-footer", text)
        self.assertIn("rmc_operator_footer_compact.html", text)
        self.assertNotIn("corporate_footer_bundle.html", text)
        self.assertIn("cp_shell_page", text)
        self.assertIn("cp_shell_footer", text)
        self.assertIn("cp-shell-content--with-public-footer", text)
        self.assertIn("rmc-footer-surfaces.css", text)

    def test_control_plane_base_uses_skeleton_shell_blocks(self):
        text = Path("templates/control_plane_base.html").read_text(encoding="utf-8")
        self.assertIn("block cp_shell_page", text)
        self.assertIn("block cp_shell_after", text)
        self.assertNotIn("cp-corporate-footer", text)

    def test_manager_admin_shell_includes_operator_footer(self):
        text = Path("templates/admin/base.html").read_text(encoding="utf-8")
        self.assertIn("is_manager_host", text)
        self.assertIn("block admin_operator_steering", text)
        self.assertIn("admin_operator_steering_strip.html", text)
        self.assertIn("rmc_operator_surface_strip.html", text)
        self.assertNotIn("operator_path_banner.html", text)
        self.assertIn("rmc_operator_footer_compact.html", text)
        self.assertIn("cp-corporate-footer", text)

    def test_manager_admin_scroll_contract_in_css_and_templates(self):
        css = Path("static/css/admin-cp-parity.css").read_text(encoding="utf-8")
        base = Path("templates/admin/base.html").read_text(encoding="utf-8")
        base_site = Path("templates/admin/base_site.html").read_text(encoding="utf-8")
        self.assertIn("data-rmc-cp-scroll', 'document'", base_site)
        self.assertIn("cp-admin-page-body", base)
        self.assertIn("<main id=\"cp-main-content\"", base)
        self.assertIn("overflow-y: visible !important", css)
        self.assertIn('data-rmc-cp-scroll="document"]', css)
        self.assertIn(".cp-platform-admin-app-tree", css)
        change_list = Path("templates/admin/change_list.html").read_text(encoding="utf-8")
        change_form = Path("templates/admin/change_form.html").read_text(encoding="utf-8")
        self.assertIn("block.super", change_list)
        self.assertIn("block.super", change_form)
        self.assertIn("admin_changelist_header.html", change_list)
        self.assertIn("admin_change_form_header.html", change_form)
        sidebar = Path("templates/partials/manager_platform_admin_sidebar.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("overflow-auto", sidebar)
        self.assertIn("guided_links", sidebar)
        self.assertIn("Guided setup", sidebar)
        offcanvas = Path("templates/admin/manager_cp_offcanvas.html").read_text(encoding="utf-8")
        self.assertIn("manager_platform_admin_sidebar.html", offcanvas)

    def test_portal_base_excludes_marketing_corporate_footer(self):
        text = Path("templates/portal_base.html").read_text(encoding="utf-8")
        self.assertNotIn("corporate_footer_bundle.html", text)
        self.assertNotIn("marketing_footer.html", text)
        self.assertIn("PORTAL_FOOTER_PARTIAL", text)
        self.assertIn("SHOW_MANAGER_CORPORATE_FOOTER", text)
        self.assertIn("rmc_operator_footer_compact.html", text)
        self.assertIn('data-rmc-footer-surface="operator-compact"', text)
        self.assertIn("manager-corporate-footer.css", text)

    def test_control_plane_skeleton_document_scroll_contract(self):
        text = Path("templates/control_plane_skeleton.html").read_text(encoding="utf-8")
        self.assertIn('data-rmc-cp-scroll="document"', text)
        self.assertIn("authenticated-shell-manager.js", text)

    def test_ai_guided_assistant_card_semantic_surface(self):
        text = Path("templates/components/ai_guided_assistant_card.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("rmc-ai-guided-assistant-card", text)
        self.assertNotIn('class="card ', text)

    def test_manager_topbar_uses_unified_control_row_toolbar(self):
        text = Path("templates/partials/manager_operator_topbar.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('data-rmc-platform-header="manager"', text)
        self.assertIn("rmc-platform-header__toolbar", text)
        self.assertIn('lockup_layout="inline"', text)
        self.assertIn("rmc-platform-header__command", text)
        self.assertIn("rmc-platform-header__actions", text)
