"""Phase 8: registry matches Phase 7 template list; inclusion tag renders for every path."""

from __future__ import annotations

from django.template import Context, Template
from django.test import SimpleTestCase

from apps.dashboard.phase7_dashboard_templates import PHASE7_DASHBOARD_TEMPLATES
from apps.dashboard.phase8_declarations import (
    PHASE8_DECLARATION_KEYS,
    assert_phase8_registry_complete,
    get_phase8_declaration,
)


class Phase8RegistryFullCoverageTests(SimpleTestCase):
    def test_registry_matches_phase7_list(self) -> None:
        assert_phase8_registry_complete()
        self.assertEqual(
            frozenset(PHASE7_DASHBOARD_TEMPLATES),
            PHASE8_DECLARATION_KEYS,
        )

    def test_no_default_fallback_for_canonical_paths(self) -> None:
        for path in PHASE7_DASHBOARD_TEMPLATES:
            with self.subTest(path=path):
                dec = get_phase8_declaration(path)
                self.assertFalse(dec["is_default"], path)

    def test_phase8_tag_renders_for_each_template(self) -> None:
        for path in PHASE7_DASHBOARD_TEMPLATES:
            with self.subTest(path=path):
                # Paths are registry literals only (no user input).
                tpl = Template(
                    "{% load phase8_tags %}{% phase8_dashboard_declaration \""
                    + path
                    + "\" %}"
                )
                html = tpl.render(Context({}))
                self.assertIn("phase8-declaration-strip", html)
                self.assertIn("data-phase8-declaration", html)
