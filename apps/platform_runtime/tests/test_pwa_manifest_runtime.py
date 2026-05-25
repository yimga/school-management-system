"""PWA manifest runtime tests (batch 1506 audit closure)."""

from __future__ import annotations

import json
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]


class PWAManifestRuntimeTests(SimpleTestCase):
    PLATFORM_MANIFEST = ROOT / "static" / "manifest.json"
    PORTAL_MANIFEST = ROOT / "static" / "manifest-portal.json"

    def test_platform_manifest_exists_and_parses(self) -> None:
        self.assertTrue(self.PLATFORM_MANIFEST.exists())
        data = json.loads(self.PLATFORM_MANIFEST.read_text(encoding="utf-8"))
        self.assertIn("name", data)
        self.assertIn("start_url", data)

    def test_platform_manifest_declares_icons(self) -> None:
        data = json.loads(self.PLATFORM_MANIFEST.read_text(encoding="utf-8"))
        self.assertIn("icons", data)
        self.assertGreater(len(data["icons"]), 0)

    def test_platform_manifest_display_mode_pwa_eligible(self) -> None:
        data = json.loads(self.PLATFORM_MANIFEST.read_text(encoding="utf-8"))
        self.assertIn(data.get("display"), {"standalone", "fullscreen", "minimal-ui"})

    def test_portal_manifest_exists_and_parses(self) -> None:
        self.assertTrue(self.PORTAL_MANIFEST.exists())
        data = json.loads(self.PORTAL_MANIFEST.read_text(encoding="utf-8"))
        self.assertIn("name", data)

    def test_manifest_no_secret_leak(self) -> None:
        for path in (self.PLATFORM_MANIFEST, self.PORTAL_MANIFEST):
            blob = path.read_text(encoding="utf-8")
            for needle in ("secret", "api_key", "password", "private_key", "ssn"):
                self.assertNotIn(needle, blob.lower(), f"{path.name} contains sensitive token {needle!r}")
