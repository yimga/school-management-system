"""1100: Automation app product Python — avoid reverse('admin:…') outside tests/migrations."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
AUTOMATION = REPO / "apps" / "automation"
_ADMIN_REVERSE = re.compile(r'reverse\s*\(\s*["\']admin:')
_SKIP = frozenset({"migrations", "tests"})


class AutomationProductAdminBridgePolicyTests(unittest.TestCase):
    def test_product_python_modules_avoid_admin_reverse(self) -> None:
        for p in sorted(AUTOMATION.rglob("*.py")):
            rel = p.relative_to(AUTOMATION).parts
            if rel and rel[0] in _SKIP:
                continue
            if p.name.startswith("test_"):
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            m = _ADMIN_REVERSE.search(text)
            self.assertIsNone(
                m,
                msg="reverse('admin:…') disallowed in "
                + p.relative_to(REPO).as_posix(),
            )
