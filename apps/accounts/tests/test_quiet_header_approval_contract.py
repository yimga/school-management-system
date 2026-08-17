"""Quiet-header approval v2: navy tile Utilities on tenant, operator, and admin."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.accounts.header_utilities import is_finance_primary_role
from apps.accounts.models import User


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
        self.assertIn("trapTab", js)
        self.assertTrue(is_finance_primary_role(User.Role.BURSAR))
        self.assertTrue(is_finance_primary_role(User.Role.FINANCE_STAFF))
        self.assertFalse(is_finance_primary_role(User.Role.TEACHER))
        self.assertFalse(is_finance_primary_role(User.Role.ADMIN))
