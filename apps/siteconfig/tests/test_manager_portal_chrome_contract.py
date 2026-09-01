"""Manager corporate footer + tenant portal chrome template contracts."""

from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import (
    assert_markup,
    assert_wires,
)

ROOT = Path(__file__).resolve().parents[3]

SKELETON = ROOT / "templates/control_plane_skeleton.html"
ADMIN_BASE = ROOT / "templates/admin/base.html"
PORTAL_BASE = ROOT / "templates/portal_base.html"
AI_CARD = ROOT / "templates/components/ai_guided_assistant_card.html"
MANAGER_TOPBAR = ROOT / "templates/partials/manager_operator_topbar.html"
EXPERIENCE_CANVAS = (
    ROOT / "templates/studio_os/partials/workspace/experience_inpage_canvas.html"
)


class ManagerPortalChromeContractTests(SimpleTestCase):
    def test_control_plane_skeleton_wires_civic_operator_footer(self):
        text = Path("templates/control_plane_skeleton.html").read_text(encoding="utf-8")
        self.assertIn("SHOW_MANAGER_CORPORATE_FOOTER", text)
        assert_wires(
            self,
            SKELETON,
            "rmc_operator_footer_civic.html",
            "control_plane_unified_header.html",
        )
        self.assertNotIn("corporate_footer_bundle.html", text)
        self.assertIn("cp_shell_page", text)
        self.assertIn("cp_shell_footer", text)
        assert_markup(self, SKELETON, "cp-shell-content--with-public-footer")
        self.assertIn("rmc-footer-surfaces.css", text)

    def test_control_plane_base_uses_skeleton_shell_blocks(self):
        text = Path("templates/control_plane_base.html").read_text(encoding="utf-8")
        self.assertTrue(
            "block cp_shell_page" in text or "block cp_shell_canvas_body" in text,
            "control_plane_base must extend skeleton canvas blocks",
        )
        self.assertIn("block cp_shell_after", text)
        self.assertNotIn("cp-corporate-footer", text)

    def test_manager_admin_shell_uses_control_plane_chrome(self):
        # v15.8 admin OS (data-rmc-admin-approval-build 2026-07-24-v15.8): the /admin/
        # shell adopts the control-plane unified header + operator drawers
        # (manager_cp_offcanvas + activity ticker) on the manager host, and delegates
        # the viewport-pinned civic footer + operator steering strips to the control
        # plane — those are removed from the model workbench (see the rationale comment
        # in templates/admin/base.html).
        text = Path("templates/admin/base.html").read_text(encoding="utf-8")
        self.assertIn("is_manager_host", text)
        assert_wires(
            self,
            ADMIN_BASE,
            "control_plane_unified_header.html",
            "manager_cp_offcanvas.html",
        )
        self.assertNotIn("operator_path_banner.html", text)
        self.assertNotIn("rmc_operator_footer_civic.html", text)
        self.assertNotIn("admin_operator_steering_strip.html", text)

    def test_manager_admin_scroll_contract_in_css_and_templates(self):
        css = Path("static/css/admin-cp-parity.css").read_text(encoding="utf-8")
        canvas_css = Path("static/css/rmc-admin-django-canvas-contract.css").read_text(
            encoding="utf-8"
        )
        base = Path("templates/admin/base.html").read_text(encoding="utf-8")
        base_site = Path("templates/admin/base_site.html").read_text(encoding="utf-8")
        self.assertTrue(
            "data-rmc-cp-scroll', 'canvas'" in base_site
            or "data-rmc-cp-scroll', 'document'" in base_site,
            "manager admin must declare cp scroll mode",
        )
        self.assertIn("cp-admin-page-body", base)
        self.assertIn("<main id=\"cp-main-content\"", base)
        self.assertIn("overflow-y: visible !important", css)
        self.assertTrue(
            'data-rmc-cp-scroll="canvas"]' in css
            or 'data-rmc-cp-scroll="document"]' in css,
            "admin-cp-parity must scope scroll contract",
        )
        self.assertIn(".cp-platform-admin-app-tree", css)
        change_list = Path("templates/admin/change_list.html").read_text(encoding="utf-8")
        change_form = Path("templates/admin/change_form.html").read_text(encoding="utf-8")
        self.assertIn("block.super", change_list)
        self.assertIn("block.super", change_form)
        # v15 admin OS: the list/form header include was replaced by the inline
        # rmc-django-command-band (single band per the v15 Scan/Form archetype).
        self.assertIn("rmc-django-command-band", change_list)
        self.assertIn("rmc-django-command-band", change_form)
        # Versioned admin-canvas cache-bust marker (bumped per admin-OS wave, e.g.
        # 20260724-admin-os-v158); assert the stable admin-OS version prefix so a
        # routine version bump doesn't trip this contract.
        self.assertIn("admin-os-v", base_site)
        self.assertIn('data-rmc-admin-surface="smart-form"', change_form)
        self.assertIn('data-rmc-admin-surface="smart-changelist"', change_list)
        self.assertIn("real-admin-canvas: terminal production contract", canvas_css)
        self.assertIn("[data-rmc-django-workspace=\"change-form\"]", canvas_css)
        self.assertIn("[data-rmc-admin-table-contract=\"native-table-scroll\"]", canvas_css)
        sidebar = Path("templates/partials/manager_platform_admin_sidebar.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("cp-sidebar-inner", sidebar)
        self.assertIn("manager_complete_sidebar_nav.html", sidebar)
        complete_nav = Path(
            "templates/partials/manager_complete_sidebar_nav.html"
        ).read_text(encoding="utf-8")
        self.assertTrue(
            "guided" in complete_nav.lower() or "Guided" in complete_nav,
            "complete sidebar nav must expose guided setup links",
        )
        offcanvas = Path("templates/admin/manager_cp_offcanvas.html").read_text(encoding="utf-8")
        self.assertIn("manager_platform_admin_sidebar.html", offcanvas)

    def test_portal_base_excludes_marketing_corporate_footer(self):
        text = Path("templates/portal_base.html").read_text(encoding="utf-8")
        self.assertNotIn("corporate_footer_bundle.html", text)
        self.assertNotIn("marketing_footer.html", text)
        self.assertIn("PORTAL_FOOTER_PARTIAL", text)
        self.assertIn("SHOW_MANAGER_CORPORATE_FOOTER", text)
        assert_wires(
            self,
            PORTAL_BASE,
            "rmc_operator_footer_civic.html",
            "control_plane_unified_header.html",
        )
        self.assertIn("rmc-footer-surfaces.css", text)
        self.assertIn("rmc-civic-footer.css", text)
        self.assertIn("rmc-surface-overlay-guard.js", text)
        tenant_nav = Path("templates/partials/tenant_primary_nav.html").read_text(
            encoding="utf-8"
        )
        assert_wires(self, PORTAL_BASE, "help_contextual_drawer.html")
        self.assertNotIn("tp-primary-nav__item--help", tenant_nav)

    def test_control_plane_skeleton_document_scroll_contract(self):
        text = Path("templates/control_plane_skeleton.html").read_text(encoding="utf-8")
        self.assertTrue(
            'data-rmc-cp-scroll="canvas"' in text
            or 'data-rmc-cp-scroll="document"' in text
            or "cp_scroll_mode" in text,
            "control plane skeleton must declare scroll contract",
        )
        self.assertIn("authenticated-shell-manager.js", text)

    def test_ai_guided_assistant_card_semantic_surface(self):
        text = Path("templates/components/ai_guided_assistant_card.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("rmc-ai-guided-assistant-card", text)
        assert_markup(self, AI_CARD, "rmc-ai-guided-assistant-card")
        self.assertNotIn('class="card ', text)

    def test_manager_topbar_uses_unified_control_row_toolbar(self):
        text = Path("templates/partials/manager_operator_topbar.html").read_text(
            encoding="utf-8"
        )
        assert_markup(
            self,
            MANAGER_TOPBAR,
            'data-rmc-platform-header="manager"',
            "rmc-platform-header__toolbar",
            "rmc-platform-header__command",
            "rmc-platform-header__actions",
        )
        self.assertIn('lockup_layout="inline"', text)

    def test_studio_experience_real_canvas_contract_is_terminal(self):
        workspace_css = Path("static/css/studio-workspace.css").read_text(encoding="utf-8")
        experience_css = Path("static/css/studio-experience-mode.css").read_text(
            encoding="utf-8"
        )
        body = Path("templates/studio_os/partials/studio_experience_mode_body.html").read_text(
            encoding="utf-8"
        )
        canvas = Path(
            "templates/studio_os/partials/workspace/experience_inpage_canvas.html"
        ).read_text(encoding="utf-8")

        self.assertIn("experience_inpage_canvas.html", body)
        self.assertIn("suppress_theme_inline_preview=1", canvas)
        assert_wires(
            self,
            EXPERIENCE_CANVAS,
            "experience_live_preview_pane.html",
            "experience_role_filmstrip.html",
            "experience_compare_fold.html",
            "theme_colors_content.html",
        )
        assert_markup(
            self, EXPERIENCE_CANVAS, 'data-rmc-studio-experience-canvas="inpage"'
        )
        self.assertIn("real-admin-canvas: Studio Experience production hardening", workspace_css)
        self.assertIn("real-admin-canvas: terminal Studio Experience fix", experience_css)
        self.assertIn(".theme-experience-grid", experience_css)
        self.assertIn("max-height: min(78vh, 56rem)", experience_css)
