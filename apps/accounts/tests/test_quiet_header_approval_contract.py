"""Quiet-header approval v2: navy tile Utilities on tenant, operator, and admin."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.accounts.header_utilities import is_finance_primary_role
from apps.accounts.models import User
from apps.siteconfig.tests._template_nodes import assert_markup, assert_wires

_BASE = Path(settings.BASE_DIR)
TENANT_UTILITIES = _BASE / "templates/components/rmc_tenant_header_utilities.html"
OPERATOR_DROPDOWN = _BASE / "templates/components/rmc_operator_workspace_dropdown.html"
ADMIN_NAV_BRIDGE = _BASE / "templates/components/admin_nav_bridge.html"
PORTAL_BASE = _BASE / "templates/portal_base.html"
HELP_PANEL = _BASE / "templates/partials/rmc_tools_help_panel.html"


class QuietHeaderApprovalContractTests(SimpleTestCase):
    def test_utilities_menus_are_tiled_not_bootstrap_grey(self):
        base = Path(settings.BASE_DIR)
        tenant = (base / "templates/components/rmc_tenant_header_utilities.html").read_text(encoding="utf-8")
        operator = (base / "templates/components/rmc_operator_workspace_dropdown.html").read_text(encoding="utf-8")
        css = (base / "static/css/rmc-header-utilities.css").read_text(encoding="utf-8")
        for text in (tenant, operator):
            self.assertIn("rmc-header-utilities__trigger", text)
            self.assertIn("rmc-header-utilities__tile", text)
            self.assertIn('trans "Utilities"', text)
            self.assertIn("data-rmc-util-search", text)
            self.assertIn('trans "Recent tools"', text)
            self.assertIn('trans "Copilot"', text)
            self.assertNotIn("dropdown-menu-dark", text)
            self.assertNotIn("btn-outline-light", text)
        # The trans-tag assertions above are template CODE and stay reads. The
        # trigger, the tiles and the search box are markup, and a tile that only
        # exists in the bytes is not a tile -- so both menus are asked of the
        # engine as well.
        for path in (TENANT_UTILITIES, OPERATOR_DROPDOWN):
            assert_markup(
                self,
                path,
                "rmc-header-utilities__trigger",
                "rmc-header-utilities__tile",
                "data-rmc-util-search",
            )
        self.assertIn('trans "Workspace tools"', tenant)
        self.assertIn('trans "All modules"', tenant)
        self.assertIn('trans "Operator tools"', operator)
        self.assertIn('trans "All platform tools"', operator)
        self.assertIn(".rmc-header-utilities__tile--sync", css)
        self.assertIn(".rmc-header-utilities__tile--alert", css)
        self.assertIn(".rmc-tools-help-panel", css)
        self.assertIn(".rmc-header-utilities__search", css)

    def test_quiet_header_is_wired_on_tenant_operator_and_admin(self):
        base = Path(settings.BASE_DIR)
        portal = (base / "templates/portal_base.html").read_text(encoding="utf-8")
        admin = (base / "templates/components/admin_nav_bridge.html").read_text(encoding="utf-8")
        operator_nav = (base / "templates/partials/control_plane_primary_nav.html").read_text(encoding="utf-8")
        # "wired" is an {% include %}, so ask the parser: a commented-out include
        # leaves the byte string in place and mounts nothing.
        assert_wires(self, ADMIN_NAV_BRIDGE, "components/rmc_tenant_header_utilities.html")
        assert_wires(
            self,
            PORTAL_BASE,
            "components/rmc_tenant_header_utilities.html",
            "partials/rmc_tools_help_panel.html",
        )
        self.assertIn('include "components/rmc_tenant_header_utilities.html"', portal)
        self.assertIn('include "components/rmc_tenant_header_utilities.html"', admin)
        self.assertIn("data-rmc-quiet-header", operator_nav)
        self.assertIn("data-rmc-quiet-header-root", portal)
        self.assertIn("rmc-header-utilities.js", portal)
        self.assertIn('include "partials/rmc_tools_help_panel.html"', portal)
        self.assertIn("rmc-quiet-header-role", portal)

    def test_finance_primary_and_help_panel_contract(self):
        base = Path(settings.BASE_DIR)
        nav = (base / "templates/partials/tenant_primary_nav.html").read_text(encoding="utf-8")
        help_panel = (base / "templates/partials/rmc_tools_help_panel.html").read_text(encoding="utf-8")
        js = (base / "static/js/rmc-header-utilities.js").read_text(encoding="utf-8")
        self.assertIn("QUIET_HEADER_FINANCE_PRIMARY", nav)
        self.assertIn('trans "Finance"', nav)
        self.assertIn('trans "Ask Copilot"', help_panel)
        self.assertIn('trans "Guided walkthrough"', help_panel)
        self.assertIn('trans "Contact support"', help_panel)
        # Those three are {% trans %} tags -- template code a parse cannot see,
        # and the panel is behind an {% if %} so it renders empty standalone.
        # What IS visible is the markup of the three actions the labels sit on,
        # which is also what rmc-header-utilities.js binds to.
        assert_markup(
            self,
            HELP_PANEL,
            "data-rmc-tools-help-copilot",
            "data-rmc-tools-help-tour",
            "data-rmc-tools-help-support",
        )
        self.assertIn("trapTab", js)
        self.assertTrue(is_finance_primary_role(User.Role.BURSAR))
        self.assertTrue(is_finance_primary_role(User.Role.FINANCE_STAFF))
        self.assertFalse(is_finance_primary_role(User.Role.TEACHER))
        self.assertFalse(is_finance_primary_role(User.Role.ADMIN))
