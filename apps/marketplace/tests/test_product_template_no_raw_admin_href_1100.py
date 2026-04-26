"""
1100: No raw <a href=\"/admin/...\"> in product marketplace / studio_os / automation templates.
CP-first surfaces must not hard-code admin paths (use reverse/CP or Advanced strip).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
_RE_HREF_ADMIN = re.compile(r'href\s*=\s*["\']/admin/')


class ProductTemplateNoRawAdminHrefTests(unittest.TestCase):
    def _scan(self, subdir: str) -> None:
        root = REPO / "templates" / subdir
        self.assertTrue(root.is_dir(), msg=f"templates/{subdir} missing")
        for p in sorted(root.rglob("*.html")):
            text = p.read_text(encoding="utf-8", errors="replace")
            m = _RE_HREF_ADMIN.search(text)
            self.assertIsNone(
                m,
                msg="Raw /admin/ href in "
                + p.relative_to(REPO).as_posix()
                + " — use CP or {% url %}/context URL",
            )

    def test_marketplace_templates(self) -> None:
        self._scan("marketplace")

    def test_studio_os_templates(self) -> None:
        self._scan("studio_os")

    def test_automation_templates(self) -> None:
        self._scan("automation")
