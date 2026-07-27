"""M9 STEP 2a — deferred-CSS inline-onload burndown + shared CSP-safe handler module.

A strict `script-src` (no 'unsafe-inline') blocks inline `on*=` handlers, including
the `onload="this.media='all'"` used to promote non-render-blocking stylesheets. This
wave replaced that pattern with a `data-rmc-async-style` marker flipped by the shared
`static/js/rmc-csp-handlers.js` module (loaded from 'self' — no nonce needed) and
wired the module into the 4 non-admin shells.

These are static-content assertions (SimpleTestCase, no DB): they seal the template +
module wiring so a regression — re-adding an inline `onload`, or dropping the handler
script from a shell — fails CI. The browser behaviour of the flipper itself is a
runtime concern outside this gate's scope.
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

import apps.security as _security_pkg

_REPO = Path(_security_pkg.__file__).resolve().parents[2]
_TEMPLATES = _REPO / "templates"
_HANDLER_JS = _REPO / "static" / "js" / "rmc-csp-handlers.js"

# The 4 non-admin shells that load the shared module. admin/base_site.html is
# CSP-bypassed by ContentSecurityPolicyMiddleware, so it is intentionally excluded
# (its inline onload stays, and never ships a CSP header).
_SHELLS = [
    _TEMPLATES / "base.html",
    _TEMPLATES / "portal_base.html",
    _TEMPLATES / "control_plane_skeleton.html",
    _TEMPLATES / "marketing" / "base_marketing.html",
]
_DEFERRED_PARTIALS = [
    _TEMPLATES / "partials" / "rmc_deferred_stylesheet.html",
    _TEMPLATES / "marketing" / "partials" / "mkt_deferred_stylesheet.html",
]


class CspHandlerModuleTests(SimpleTestCase):
    def test_handler_module_exists_with_core_capabilities(self):
        self.assertTrue(_HANDLER_JS.exists(), str(_HANDLER_JS))
        src = _HANDLER_JS.read_text(encoding="utf-8")
        for marker in (
            "data-rmc-async-style",
            "data-rmc-print",
            "data-rmc-reload",
            "data-rmc-confirm",
            "data-rmc-img-fallback",
        ):
            self.assertIn(marker, src, marker)

    def test_shells_load_the_handler_module(self):
        for shell in _SHELLS:
            self.assertIn(
                "js/rmc-csp-handlers.js",
                shell.read_text(encoding="utf-8"),
                f"{shell} must load the CSP-safe handler module",
            )


class DeferredCssBurndownTests(SimpleTestCase):
    def test_no_inline_onload_media_flip_in_shells_or_partials(self):
        for path in _SHELLS + _DEFERRED_PARTIALS:
            self.assertNotIn(
                'onload="this.media',
                path.read_text(encoding="utf-8"),
                f"{path} still ships an inline onload media flip (blocked by strict script-src)",
            )

    def test_deferred_partials_use_data_attribute(self):
        for path in _DEFERRED_PARTIALS:
            self.assertIn(
                "data-rmc-async-style",
                path.read_text(encoding="utf-8"),
                f"{path} must mark async stylesheets with data-rmc-async-style",
            )
