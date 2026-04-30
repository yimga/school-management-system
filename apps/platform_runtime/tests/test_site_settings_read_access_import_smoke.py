"""1041: product modules resolve get_effective_site_settings from config_service."""

from __future__ import annotations

import importlib
import unittest
from pathlib import Path


class SiteSettingsReadAccessImportSmokeTests(unittest.TestCase):
    def test_sample_modules_import_from_read_access_not_helpers_line(self) -> None:
        for modname in (
            "apps.accounts.middleware",
            "apps.siteconfig.middleware.maintenance_mode",
            "apps.dashboard.context",
        ):
            m = importlib.import_module(modname)
            path = getattr(m, "__file__", None)
            self.assertIsInstance(path, str, modname)
            src = Path(path).read_text(encoding="utf-8", errors="replace")
            self.assertIn(
                "config_service",
                src,
                f"{modname} should import runtime reads via apps.siteconfig.config_service (1041)",
            )
