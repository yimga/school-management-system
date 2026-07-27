"""Tenant-admin chrome consistency: copilot + Tools rails (2026-07-27).

The single 56px right rail (copilot icons + folded "Tools" tab) must render
correctly on BOTH tenant-admin surfaces — the portal-shell Admin Home
(/backend/) and the Unfold Django admin (/admin/). This guards the backend
Tools-tab visibility hardening; the /admin/ chrome port is covered by the
tenant/operator tools-tray shell tests once wired.
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]
TOOLS_TRAY_CSS = ROOT / "static" / "css" / "rmc-operator-tools-tray.css"


class BackendToolsTabVisibilityTests(SimpleTestCase):
    def test_backend_shell_folded_tools_tab_has_visible_fallback(self):
        """The folded tenant Tools tab renders transparent (shows the dark
        copilot column through). On the backend console shell that column is not
        guaranteed dark, which would make the tab invisible. A backend-scoped
        self-contained fallback background keeps "Tools" visible there."""
        css = TOOLS_TRAY_CSS.read_text(encoding="utf-8")
        self.assertIn("body.backend-shell[data-rmc-tenant-copilot-rail=\"1\"]", css)
        # The fallback targets the folded edge-tab specifically.
        self.assertIn(".rmc-operator-tools__edge-tab", css)
        # Backend fallback is scoped so it cannot alter the teacher surface's
        # seamless transparency (which requires the tenant workspace-tools attr).
        self.assertIn(
            'body.backend-shell[data-rmc-tenant-copilot-rail="1"][data-rmc-workspace-tools="tenant"]',
            css,
        )
