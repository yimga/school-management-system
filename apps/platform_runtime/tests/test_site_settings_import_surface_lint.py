"""Wave D: product code must not import get_effective_site_settings from helpers (use config_service)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
HELPERS_IMPORT_RE = re.compile(
    r"from\s+apps\.platform_runtime\.helpers\s+import\s+([^#\n]+)",
    re.MULTILINE,
)
FORBIDDEN = re.compile(
    r"(?:^|\s|,)get_effective_site_settings(?:\s|,|$)",
    re.MULTILINE,
)


class SiteSettingsHelpersImportSurfaceTests(unittest.TestCase):
    def test_no_product_module_imports_get_effective_from_helpers(self) -> None:
        bad: list[str] = []
        for path in (REPO / "apps").rglob("*.py"):
            rel = path.relative_to(REPO).as_posix()
            if "/migrations/" in rel or "/tests/" in rel:
                continue
            if rel in (
                "apps/platform_runtime/helpers.py",
                "apps/platform_runtime/site_settings_read_access.py",
                # config_resolver is the canonical single-key facade (Wave A); it
                # wraps get_effective_site_settings to build get_effective_config,
                # so it legitimately imports the raw helper like config_service.
                "apps/platform_runtime/config_resolver.py",
                "apps/siteconfig/config_service.py",
            ):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # Honor the same reviewed-exception marker the config-resolver
            # fragmentation scanner uses: a file that carries a
            # `# config-resolver-allow:` marker has a documented reason to read the
            # raw effective namespace (e.g. dynamic getattr projection over a
            # public_keys tuple) that config_service can't express.
            if "config-resolver-allow" in text:
                continue
            for m in HELPERS_IMPORT_RE.finditer(text):
                block = m.group(1) or ""
                if FORBIDDEN.search(block):
                    bad.append(f"{rel}: helpers import includes get_effective_site_settings")
        self.assertEqual(
            bad,
            [],
            "Import SiteSettings readers via apps.siteconfig.config_service",
        )
