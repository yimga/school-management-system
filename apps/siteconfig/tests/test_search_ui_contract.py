"""Static contract tests for header/operator typeahead vs fullscreen cmdk."""

from __future__ import annotations

from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[3]


class SearchUiContractTests(TestCase):
    def test_tenant_header_does_not_advertise_ctrl_k_for_typeahead(self):
        portal = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
        # Typeahead kbd chip is "/" — Ctrl+K belongs to #rmc-cmdk Spotlight.
        self.assertIn('id="headerSearchInput"', portal)
        self.assertIn('id="headerSearchResults"', portal)
        self.assertIn("header-search-dropdown--hidden", portal)
        # The kbd near the input must not claim Ctrl+K.
        search_block_start = portal.index("headerSearchInput")
        search_block = portal[search_block_start : search_block_start + 800]
        self.assertNotIn("Ctrl+K", search_block)
        self.assertIn(">/", search_block.replace(" ", "") or "/")

    def test_operator_topbar_anchors_results_under_input(self):
        topbar = (
            ROOT / "templates/partials/manager_operator_topbar.html"
        ).read_text(encoding="utf-8")
        self.assertIn('id="cpSearchResults"', topbar)
        self.assertIn("top-100", topbar)
        self.assertIn("position-relative", topbar)

    def test_admin_bridge_has_results_panel(self):
        bridge = (
            ROOT / "templates/components/admin_nav_bridge.html"
        ).read_text(encoding="utf-8")
        self.assertIn('id="cpSearchInputAdmin"', bridge)
        self.assertIn('id="cpSearchResultsAdmin"', bridge)

    def test_typeahead_css_caps_height_under_input(self):
        portal_css = (
            ROOT / "static/css/portal-base-shell.css"
        ).read_text(encoding="utf-8")
        manager_css = (
            ROOT / "static/css/manager-control-plane.css"
        ).read_text(encoding="utf-8")
        self.assertIn("header-search-dropdown--hidden", portal_css)
        self.assertIn("max-height: min(320px, 45vh)", portal_css)
        self.assertIn("inset: auto", portal_css)
        self.assertIn("max-height: min(360px, 45vh)", manager_css)
        # Fullscreen cmdk remains a separate surface.
        cmdk = (ROOT / "static/css/rmc-long-page-grammar.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(".rmc-cmdk {", cmdk)
        self.assertIn("inset: 0", cmdk)
        self.assertIn("z-index: 2080", cmdk)

    def test_typeahead_js_uses_class_api_not_inline_display(self):
        js = (ROOT / "static/js/portal-shell-bootstrap.js").read_text(encoding="utf-8")
        self.assertIn("header-search-dropdown--hidden", js)
        self.assertNotIn("resultsEl.style.display", js)
        self.assertIn("ArrowDown", js)
        self.assertIn("aria-activedescendant", js)

    def test_backend_themes_has_no_circular_admin_vars(self):
        css = (ROOT / "static/css/backend-themes.css").read_text(encoding="utf-8")
        import re

        self.assertEqual(
            len(re.findall(r"--([a-z0-9-]+):\s*var\(\s*--\1\s*,", css)),
            0,
        )

    def test_blueprint_audit_uses_final_conflicts_after_pack_merge(self):
        src = (
            ROOT / "apps/platform_runtime/blueprint_preview.py"
        ).read_text(encoding="utf-8")
        # Must audit from result["conflicts"] / result["can_apply"] after pack merge.
        self.assertIn('result="blocked" if result["conflicts"] else "ok"', src)
        self.assertIn('payload={"can_apply": result["can_apply"]}', src)
        self.assertNotIn('result="blocked" if conflicts else "ok"', src)

    def test_pressing_issues_overdue_is_school_scoped(self):
        src = (ROOT / "apps/dashboard/pressing_issues.py").read_text(encoding="utf-8")
        self.assertIn('school=school, status="OVERDUE"', src)
        self.assertIn('"churn_risk"', src)
        tenant_fn = src.split("def build_tenant_pressing_issues")[1]
        self.assertNotIn("super:", tenant_fn)

    def test_mobile_operator_search_has_dedicated_results_panel(self):
        topbar = (
            ROOT / "templates/partials/manager_operator_topbar.html"
        ).read_text(encoding="utf-8")
        js = (
            ROOT / "static/js/authenticated-shell-manager.js"
        ).read_text(encoding="utf-8")
        self.assertIn("cpSearchResultsMobile", topbar)
        self.assertIn("cpSearchResultsMobile", js)
