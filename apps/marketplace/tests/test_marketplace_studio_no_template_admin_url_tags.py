"""
1093: No Django `{% url 'admin:...' %}` links in marketplace / studio_os templates.

Product Python: `apps/marketplace` has no `admin:` reverse strings this sweep;
`apps/studio_os` uses `admin:` only for routing maps and intentional Advanced fallbacks
(deep_links, experience-pack admin URL), not for unsafe template `{% url %}` usage.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
_ADMIN_URL_TAG = re.compile(r"{%\s*url\s+['\"]admin:")


class MarketplaceStudioTemplateAdminUrlTagTests(unittest.TestCase):
    def test_marketplace_templates_have_no_admin_url_tag(self) -> None:
        root = REPO / "templates" / "marketplace"
        self.assertTrue(root.is_dir(), msg="templates/marketplace missing")
        for p in sorted(root.rglob("*.html")):
            text = p.read_text(encoding="utf-8", errors="replace")
            m = _ADMIN_URL_TAG.search(text)
            self.assertIsNone(
                m,
                msg="Django url tag to admin: namespace in " + p.relative_to(REPO).as_posix(),
            )

    def test_studio_os_templates_have_no_admin_url_tag(self) -> None:
        root = REPO / "templates" / "studio_os"
        self.assertTrue(root.is_dir(), msg="templates/studio_os missing")
        for p in sorted(root.rglob("*.html")):
            text = p.read_text(encoding="utf-8", errors="replace")
            m = _ADMIN_URL_TAG.search(text)
            self.assertIsNone(
                m,
                msg="Django url tag to admin: namespace in " + p.relative_to(REPO).as_posix(),
            )
