"""1095: tenant app catalog — template markers and primary-before-secondary action order."""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
TEMPLATE = REPO / "templates" / "marketplace" / "tenant_app_catalog.html"


class TenantAppCatalogTemplateHierarchyTests(unittest.TestCase):
    def test_template_has_compact_catalog_markers(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8", errors="replace")
        self.assertIn('data-rmc-mkt-catalog-surface="1"', text)
        self.assertIn('data-rmc-mkt-app-card="1"', text)
        self.assertIn('data-rmc-mkt-lifecycle-badges="1"', text)
        self.assertIn("data-rmc-mkt-lifecycle", text)
        self.assertIn('href="', text)
        self.assertIn("static 'css/marketplace-tenant-app-catalog.css'", text)

    def test_install_flow_primary_action_before_scope_consent(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8", errors="replace")
        # Not-installed branch: primary install control precedes scope consent link.
        i_install = text.find("data-rmc-mkt-action-tier-order=\"install-flow\"")
        self.assertNotEqual(i_install, -1)
        chunk = text[i_install : i_install + 1200]
        p_btn = chunk.find("data-rmc-mkt-primary-action")
        p_scope = chunk.find("tenant_scope_consent")
        self.assertNotEqual(p_btn, -1, msg="missing primary action on install flow")
        self.assertNotEqual(p_scope, -1, msg="missing scope consent on install flow")
        self.assertLess(
            p_btn,
            p_scope,
            msg="Primary install action should appear before scope consent link",
        )

    def test_manage_flow_primary_before_secondary_when_sandbox(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8", errors="replace")
        i = text.find("listing.tenant_install_phase == 'sandbox'")
        self.assertNotEqual(i, -1)
        j = text.find("data-rmc-mkt-primary-action", i)
        k = text.find("btn-outline-primary", j)
        self.assertNotEqual(j, -1)
        self.assertNotEqual(k, -1)
        self.assertLess(j, k, msg="Activate (primary) should precede Configure (outline)")
