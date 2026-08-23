"""Tests for verify_operator_landing_header_order.py."""

from __future__ import annotations

import unittest
from pathlib import Path

from scripts.verify_operator_landing_header_order import scan


class OperatorLandingHeaderOrderTests(unittest.TestCase):
    def test_clean_tree_has_no_findings(self):
        root = str(Path(__file__).resolve().parents[2])
        self.assertEqual(scan(root), [])

    def test_detects_chrome_before_header(self):
        root = Path(__file__).resolve().parents[2]
        bad = root / "templates" / "_test_fixtures" / "landing_header_order_bad.html"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text(
            '<div data-rmc-founder-dashboard="1"></div>'
            '{% include "partials/cockpit/_collapsable_section.html" %}'
            '<header class="rmc-page-header-glow"></header>',
            encoding="utf-8",
        )
        try:
            rel = str(bad.relative_to(root)).replace("\\", "/")
            hits = [f for f in scan(str(root)) if f["file"] == rel]
            self.assertEqual(len(hits), 1)
        finally:
            bad.unlink(missing_ok=True)
            try:
                bad.parent.rmdir()
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
