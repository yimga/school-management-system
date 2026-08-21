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

    def test_safety_net_backstops_bespoke_surface_bg_subtle_classes(self):
        """§12: the platform-wide audit found the same white-on-white class in the
        account/security surface (MFA backup codes), the file-upload button, status
        pills, the LTI pill/callout, and the filter row. The safety net must backstop
        the security-critical ones in dark mode, and keep the QR wrapper light."""
        css = _read(_SAFETY_NET)
        # Security-critical: MFA backup recovery codes panel is repainted in dark mode.
        self.assertIn(".rmc-account-backup-codes", css)
        # File-upload button pseudo-element is covered.
        self.assertIn("::file-selector-button", css)
        # QR wrapper is explicitly carved out to stay light (must scan).
        self.assertRegex(
            css, r'\.rmc-account-mfa-qr-wrap[^{]*\{[^}]*#ffffff',
        )
