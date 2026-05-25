"""Service worker cache policy runtime tests (batch 1506 audit closure)."""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]
SW = ROOT / "static" / "js" / "service-worker.js"


class ServiceWorkerCachePolicyRuntimeTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.source = SW.read_text(encoding="utf-8")

    def test_cache_version_matches_sms_pattern(self) -> None:
        m = re.search(r'const CACHE_VERSION\s*=\s*"(sms-v[^"]+)"', self.source)
        self.assertIsNotNone(m)
        version = m.group(1)
        self.assertRegex(version, r"^sms-v\d+\.\d+\.\d+(-[a-z0-9-]+)?(-\d{4}-\d{2}-\d{2})?$")

    def test_skip_cache_routes_documented_in_offline_manifest(self) -> None:
        # SW skip-cache contract is documented at docs/generated/pwa_offline_storage_manifest.json
        from pathlib import Path
        import json
        manifest = Path(__file__).resolve().parents[3] / "docs" / "generated" / "pwa_offline_storage_manifest.json"
        self.assertTrue(manifest.exists())
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for needle in ("/admin/*", "/accounts/login/*", "/accounts/logout/*"):
            self.assertIn(needle, data.get("skip_cache_routes", []))

    def test_cache_buckets_share_version_suffix(self) -> None:
        # Each named cache should include the CACHE_VERSION via template literal.
        self.assertIn("${CACHE_VERSION}", self.source)

    def test_no_runtime_secret_assignment_in_service_worker(self) -> None:
        # Ensure no `password = "..."` or `apiKey = "..."` style assignment
        import re
        # Match obvious assignment patterns (variable + equals + string literal)
        for pattern in (
            r'\bpassword\s*[:=]\s*["\']',
            r'\bapi_?[Kk]ey\s*[:=]\s*["\']',
            r'\bprivate_?[Kk]ey\s*[:=]\s*["\']',
            r'\bsecret\s*[:=]\s*["\']',
        ):
            matches = re.findall(pattern, self.source)
            self.assertEqual(matches, [], f"service-worker contains assignment matching {pattern!r}: {matches[:3]}")

    def test_service_worker_registers_install_and_activate_handlers(self) -> None:
        self.assertIn('addEventListener("install"', self.source)
        self.assertIn('addEventListener("activate"', self.source)

    def test_service_worker_handles_fetch_event(self) -> None:
        self.assertIn('addEventListener("fetch"', self.source)
