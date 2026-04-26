"""
1040: Portal and control-plane surfaces resolve platform settings through the same
approved read-access module (``site_settings_read_access`` + shared message chrome core).
"""

from __future__ import annotations

import unittest
from pathlib import Path


class SiteSettingsRuntimeReadParityTests(unittest.TestCase):
    def test_context_processors_use_access_layer_not_direct_model_import(self) -> None:
        root = Path(__file__).resolve().parent.parent.parent.parent
        for rel in (
            "apps/siteconfig/context_processors.py",
            "apps/accounts/context_processors.py",
        ):
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
            self.assertIn(
                "site_settings_read_access",
                text,
                f"{rel} should import runtime reads via site_settings_read_access",
            )
            self.assertNotIn(
                "from apps.siteconfig.models import SiteSettings",
                text,
                rel,
            )

    def test_message_chrome_wrappers_share_core_partial(self) -> None:
        root = Path(__file__).resolve().parent.parent.parent.parent
        core = "partials/shell_chrome_django_messages.html"
        for rel in (
            "templates/partials/shell_chrome_django_messages_tenant_portal.html",
            "templates/partials/shell_chrome_django_messages_control_plane.html",
            "templates/partials/shell_chrome_django_messages_base_bootstrap.html",
        ):
            t = (root / rel).read_text(encoding="utf-8", errors="replace")
            self.assertIn(core, t, rel)

    def test_base_layout_uses_bootstrap_message_wrapper(self) -> None:
        root = Path(__file__).resolve().parent.parent.parent.parent
        b = (root / "templates" / "base.html").read_text(encoding="utf-8", errors="replace")
        self.assertIn("shell_chrome_django_messages_base_bootstrap", b)
        self.assertNotIn('include "partials/shell_chrome_django_messages.html"', b)

    def test_portal_and_control_plane_use_wrappers_only(self) -> None:
        root = Path(__file__).resolve().parent.parent.parent.parent
        for rel in ("templates/portal_base.html", "templates/control_plane_base.html"):
            t = (root / rel).read_text(encoding="utf-8", errors="replace")
            self.assertNotIn('include "partials/shell_chrome_django_messages.html"', t, rel)
