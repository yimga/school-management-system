"""Tenant footer must be sized to /super/ operator-footer parity (2026-07-27).

The tenant civic footer shipped the full padded 4-tier stack (12/10px pad,
13-14px type) while /super/ compacts to a ~55-60px band. This guards the
compaction contract in BOTH homes: the stylesheet (rmc-tenant-chrome-finish.css)
and the load-bearing inline pin in portal_base.html (which must survive a stale
SW/CDN of the sheet — the recurring "still wrong = stale cache" trap on this
chrome).
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import (
    assert_markup,
)

_TN_ROOT = Path(__file__).resolve().parents[3]

ROOT = Path(__file__).resolve().parents[3]
FINISH_CSS = ROOT / "static" / "css" / "rmc-tenant-chrome-finish.css"
PORTAL_BASE = ROOT / "templates" / "portal_base.html"


class TenantFooterOperatorParityTests(SimpleTestCase):
    def test_stylesheet_carries_tenant_footer_compaction(self):
        css = FINISH_CSS.read_text(encoding="utf-8")
        self.assertIn('[data-rmc-footer-surface="tenant-standard"].rmc-civic-footer', css)
        # Container padding compacted toward the operator rhythm (was 12px/10px).
        self.assertIn("padding: 6px clamp(14px, 2vw, 20px) 6px", css)
        # Operator 10.5px micro-type mirrored onto the tenant pills/legal.
        self.assertIn("font-size: 10.5px", css)

    def test_inline_pin_mirrors_footer_size_for_stale_cache(self):
        html = PORTAL_BASE.read_text(encoding="utf-8")
        # The critical pin must carry the footer-size drivers so a stale cached
        # rmc-tenant-chrome-finish.css cannot leave the footer at the old height.
        self.assertIn('id="rmc-tenant-chrome-critical"', html)
        self.assertIn(
            '[data-rmc-footer-surface="tenant-standard"].rmc-civic-footer{padding:6px clamp(14px,2vw,20px) 6px!important',
            html,
        )
        # The pin is an inline <style> block, so it IS emitted text -- which
        # means the engine can be asked for it rather than the file.
        assert_markup(self, _TN_ROOT / "templates/portal_base.html",
                      'id="rmc-tenant-chrome-critical"')
