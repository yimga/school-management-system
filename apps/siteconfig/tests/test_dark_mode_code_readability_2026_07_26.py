"""Regression guard: inline <code>/<pre> must stay readable in dark mode.

The bug (reported platform-wide, both operator and tenant): the base
`code:not(pre code)` rule paints its background with `--surface-bg-subtle`, which
stays LIGHT on the tenant/admin/default planes in dark mode while the text token
`--admin-content-text` (=`--text-primary`) flips near-white — so every inline data
value wrapped in <code> (config values, feature-flag keys, module paths) rendered as
a WHITE-ON-WHITE box. Fix: a dark-scoped override repoints code/pre to
`--surface-elevated` (which flips) in both the source sheet and the safety-net
backstop. These source-level assertions fail if a future edit drops the seal.
"""

from __future__ import annotations

import os
import re

from django.test import SimpleTestCase

_HERE = os.path.dirname(os.path.abspath(__file__))
_CSS_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "static", "css"))
_DESIGN_TOKENS = os.path.join(_CSS_DIR, "design-tokens.css")
_SAFETY_NET = os.path.join(_CSS_DIR, "dark-mode-safety-net.css")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class DarkModeCodeReadabilityTests(SimpleTestCase):
    def test_design_tokens_has_dark_scoped_code_override(self):
        css = _read(_DESIGN_TOKENS)
        # A dark-scoped selector must target code:not(pre code) ...
        self.assertRegex(
            css,
            r'html\[data-theme="dark"\][^{]*code:not\(pre code\)',
            "design-tokens.css lost the dark-mode code override",
        )
        # ... and repaint it with a token that FLIPS in dark mode (not --surface-bg-subtle).
        block = css[css.index('code:not(pre code)') :]
        # Find the dark override block specifically.
        m = re.search(
            r'(html\[data-theme="dark"\][^}]*code:not\(pre code\)[^}]*\{[^}]*\})', css, re.S
        )
        self.assertIsNotNone(m, "no dark code override block found")
        self.assertIn("--surface-elevated", m.group(1))
        self.assertNotIn("--surface-bg-subtle", m.group(1))

    def test_safety_net_backstops_code_and_pre(self):
        css = _read(_SAFETY_NET)
        self.assertIn("code:not(pre code)", css)
        self.assertRegex(css, r'body\.portal-backend-dark[^{]*(code|pre)')
        self.assertIn("--surface-elevated", css)
