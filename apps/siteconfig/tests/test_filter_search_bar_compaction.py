"""Platform filter/search-bar compaction contract (2026-06-22).

Same space-bug class as the Studio header: a bare full-width control
(Bootstrap .form-control/.form-select is width:100%) inside a
`role="search"` flex-wrap bar forces its button(s) onto a second row.
One CSS rule in design-system-phase2-enforcement.css (loaded by both the
control-plane and portal shells) caps + shrinks such inputs so the bar
stays one row. These static checks lock the rule and its targets.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parents[3]
ENFORCEMENT_CSS = REPO_ROOT / "static" / "css" / "design-system-phase2-enforcement.css"
TEMPLATES = REPO_ROOT / "templates"

# The genuine twins found by the platform audit (full-width search forcing a wrap).
# Broader re-audit (2026-06-22) confirmed every genuine case is a role="search"
# bar (covered by the rule); the only non-search candidates were benign
# div-wrapped labelled fields / standalone prompts, not naked toolbar controls.
TARGET_TEMPLATES = [
    "schools/super_fleet_wall.html",
    "schools/super_pulse.html",
    "schools/super_tenant_health.html",
    "schools/super_usage.html",
    "portal/operator/kb_docs_hub_body.html",
    "portal/kb_docs_hub.html",
]


class FilterSearchBarRuleTests(SimpleTestCase):
    def test_platform_rule_exists(self) -> None:
        css = ENFORCEMENT_CSS.read_text(encoding="utf-8")
        self.assertIn('form[role="search"].d-flex:has(.btn) > .form-control', css)
        # capped + shrinkable so it never claims a whole row
        self.assertIn("max-width: 28rem", css)
        self.assertIn("min-width: 0", css)

    def test_targets_match_the_rule_selector(self) -> None:
        """Each genuine template still has a role=search flex bar with a button
        and a full-width control — i.e. the rule actually applies to it."""
        for rel in TARGET_TEMPLATES:
            path = TEMPLATES / rel
            with self.subTest(template=rel):
                self.assertTrue(path.exists(), f"missing template: {rel}")
                src = path.read_text(encoding="utf-8")
                # Attribute order varies, so match the <form ...> tag then check
                # both markers independently.
                form_tags = [
                    m.group(0)
                    for m in re.finditer(r"<form\b[^>]*>", src)
                    if 'role="search"' in m.group(0) and "d-flex" in m.group(0)
                ]
                self.assertTrue(
                    form_tags,
                    f"{rel}: expected a <form role=search ... d-flex ...> filter bar",
                )
                self.assertIn("form-control", src, f"{rel}: expected a .form-control")
                self.assertRegex(
                    src, r'<(button|a)[^>]*\bbtn\b',
                    msg=f"{rel}: expected a button beside the search input",
                )
