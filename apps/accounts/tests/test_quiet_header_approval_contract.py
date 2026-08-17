"""Quiet-header approval v2: navy tile Utilities on tenant, operator, and admin."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


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
            self.assertNotIn("dropdown-menu-dark", text)
            self.assertNotIn("btn-outline-light", text)
        self.assertIn('trans "Workspace tools"', tenant)
        self.assertIn('trans "Operator tools"', operator)
        self.assertIn(".rmc-header-utilities__tile--sync", css)
        self.assertIn(".rmc-header-utilities__tile--alert", css)

    def test_quiet_header_is_wired_on_tenant_operator_and_admin(self):
        base = Path(settings.BASE_DIR)
        portal = (base / "templates/portal_base.html").read_text(encoding="utf-8")
        admin = (base / "templates/components/admin_nav_bridge.html").read_text(encoding="utf-8")
        operator_nav = (base / "templates/partials/control_plane_primary_nav.html").read_text(encoding="utf-8")
        self.assertIn('include "components/rmc_tenant_header_utilities.html"', portal)
        self.assertIn('include "components/rmc_tenant_header_utilities.html"', admin)
        self.assertIn("data-rmc-quiet-header", operator_nav)
