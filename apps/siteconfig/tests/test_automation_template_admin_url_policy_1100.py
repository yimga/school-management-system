"""1100: Product templates under templates/automation — no {% url 'admin:…' %}."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
_ROOT = REPO / "templates" / "automation"
_ADMIN_URL_TAG = re.compile(r"{%\s*url\s+['\"]admin:")


class AutomationTemplateAdminUrlPolicyTests(unittest.TestCase):
    def test_automation_templates_have_no_admin_url_tag(self) -> None:
        if not _ROOT.is_dir():
            self.skipTest("templates/automation not present")
        for p in sorted(_ROOT.rglob("*.html")):
            text = p.read_text(encoding="utf-8", errors="replace")
            m = _ADMIN_URL_TAG.search(text)
            self.assertIsNone(
                m,
                msg="Django url tag to admin: in " + p.relative_to(REPO).as_posix(),
            )
