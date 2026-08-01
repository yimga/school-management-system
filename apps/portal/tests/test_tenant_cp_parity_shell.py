"""Tenant cp-sidebar v8 groups (batch — tenant-wide operator parity)."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]


class TenantSidebarV8GroupsTests(SimpleTestCase):
    def test_v8_groups_partial_uses_collapsible_details(self):
        text = (ROOT / "templates/partials/portal_sidebar_v8_groups.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("cp-sidebar__group", text)
        self.assertIn("PORTAL_SIDEBAR_GROUPS", text)
        self.assertNotIn("{% regroup", text)
        self.assertIn("cp-sidebar__item", text)

    def test_portal_sidebar_wires_v8_when_tenant_shell(self):
        text = (ROOT / "templates/partials/portal_sidebar.html").read_text(encoding="utf-8")
        self.assertIn("portal_sidebar_v8_groups.html", text)
        self.assertIn("data-rmc-cp-sidebar-v8", text)

    def test_portal_base_loads_tenant_cp_parity_css(self):
        text = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
        self.assertIn("rmc-tenant-cp-parity.css", text)
        self.assertIn("cp-header--tenant", text)
        self.assertIn("rmc_nav_sidebar_page_data.html", text)

    def test_portal_base_defaults_canvas_scroll_for_v3_shell(self):
        text = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
        self.assertIn("tp_v3_tenant_shell %}canvas", text.replace("\n", " "))
        self.assertIn("rmc-tenant-workspace-canvas.css", text)
        self.assertIn("tp-v3-shell-footer", text)

    def test_v3_footer_is_shell_chrome_not_main_scroll_content(self):
        text = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
        footer_idx = text.find('class="tp-v3-shell-footer"')
        self.assertGreater(footer_idx, 0)
        main_close_idx = text.find('{% include "partials/_remote_support_banner.html" %}')
        self.assertGreater(main_close_idx, footer_idx)
        content_window = text[text.find('id="main-content"') : footer_idx]
        self.assertIn("</div>\n    </div>\n", content_window)
        self.assertNotIn("footer scrolls inside #main-content", content_window)

    def test_viewport_canvas_css_locks_header_and_main(self):
        text = (ROOT / "static/css/rmc-tenant-workspace-canvas.css").read_text(encoding="utf-8")
        self.assertIn("overflow: hidden", text)
        self.assertIn("#main-content", text)
        self.assertIn("overflow-y: auto", text)
        self.assertIn("portal-sidebar-col", text)
        self.assertIn("display: flex !important", text)
        self.assertIn("body[data-rmc-cp-scroll=\"canvas\"] > .tp-v3-shell-footer", text)
        self.assertIn(".portal-page-body", text)
        self.assertIn(".tp-canvas-body", text)
        self.assertIn("overflow: visible !important", text)

    def test_shell_layout_wrap_compact_for_v3(self):
        text = (ROOT / "templates/partials/shell_portal_layout_wrap_open.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("tp-v3-shell-workspace", text)
        self.assertIn("g-0 h-100", text)

    def test_sidebar_intelligence_supports_tenant_v8_markup(self):
        text = (ROOT / "static/js/rmc-sidebar-intelligence.js").read_text(encoding="utf-8")
        self.assertIn("data-rmc-cp-sidebar-v8", text)
        self.assertIn("cp-sidebar__item[href]", text)

    def test_copilot_rail_uses_tenant_portal_endpoints(self):
        text = (ROOT / "templates/partials/cockpit/_ai_copilot_rail.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("portal:copilot_rail_context", text)
        self.assertIn("experience", text)

    def test_tenant_copilot_horizontal_collapse_contract(self):
        compact = (ROOT / "static/css/rmc-platform-vertical-compact.css").read_text(
            encoding="utf-8"
        )
        canvas = (ROOT / "static/css/rmc-tenant-workspace-canvas.css").read_text(
            encoding="utf-8"
        )
        cp200 = (ROOT / "static/css/rmc-cp-200x.css").read_text(encoding="utf-8")
        portal = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
        rail = (ROOT / "templates/partials/cockpit/_ai_copilot_rail.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("data-rmc-copilot-mount", portal)
        self.assertIn("data-rmc-copilot-toggle", rail)
        self.assertIn("transition: width var(--motion-slow", compact)
        self.assertIn("var(--rmc-copilot-rail-z", compact)
        # v4.05.89: the copilot gutter that reserves space for the rail lives on
        # the MAIN canvas (it sits beside the rail), NOT the header — the header is
        # full-bleed because the rail anchors BELOW it. Assert the retained gutter
        # on .portal-main-col in the compact sheet (the header gutter was removed).
        self.assertIn("padding-right: calc(var(--rmc-app-shell-copilot-w", compact)
        # canvas sheet still loaded by the shell (read above to keep it pinned)
        self.assertIn('data-rmc-cp-scroll="canvas"', canvas)
        self.assertIn(
            'body[data-copilot="collapsed"] .rmc-tenant-portal-copilot-mount .lx-copilot__expanded',
            cp200,
        )
        self.assertIn("rmc-copilot-rail.js", portal)

    def test_mission_strip_is_tenant_school_only(self):
        portal = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
        idx = portal.find("tp_mission_strip.html")
        self.assertGreater(idx, 0)
        window = portal[max(0, idx - 500) : idx + 50]
        self.assertIn("tp_v3_tenant_shell", window)
        mission = (ROOT / "templates/partials/tenant/tp_mission_strip.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("TENANT SCHOOL SURFACE ONLY", mission)

