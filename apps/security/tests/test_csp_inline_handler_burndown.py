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


_MODAL_JS = _REPO / "static" / "js" / "rmc-modal-intelligence.js"

# Templates whose inline on*= handlers were converted to declarative data-* markers
# in the STEP 2b burndown (all reach the shared module via one of the 4 shells).
_CONVERTED_TEMPLATES = [
    _TEMPLATES / "parent" / "finance.html",
    _TEMPLATES / "parent" / "results.html",
    _TEMPLATES / "maintenance.html",
    _TEMPLATES / "errors" / "500_control_plane.html",
    _TEMPLATES / "errors" / "503_control_plane.html",
    _TEMPLATES / "apicenter" / "api_keys.html",
    _TEMPLATES / "apicenter" / "webhook_docs.html",
    _TEMPLATES / "payroll" / "run_detail.html",
    _TEMPLATES / "accounts" / "tenant_identity_detail.html",
    _TEMPLATES / "accounts" / "tenant_join_codes.html",
    _TEMPLATES / "accounts" / "sso_connections.html",
    _TEMPLATES / "accounts" / "sessions_page.html",
    _TEMPLATES / "accounts" / "my_delegations.html",
    _TEMPLATES / "marketplace" / "blueprint_marketplace.html",
    _TEMPLATES / "marketplace" / "webhook_endpoints.html",
    _TEMPLATES / "marketplace" / "tenant_installed_apps.html",
    _TEMPLATES / "schools" / "advancement_donor_detail.html",
    _TEMPLATES / "schools" / "super_operator_team_detail.html",
    _TEMPLATES / "schools" / "super_support_auto_rules.html",
    _TEMPLATES / "schools" / "super_support_on_call.html",
    _TEMPLATES / "siteconfig" / "installed_packages_rollback.html",
    _TEMPLATES / "siteconfig" / "partials" / "tag_manager_edit_body.html",
    _TEMPLATES / "siteconfig" / "partials" / "maintenance_body.html",
]


class CspHandlerModuleTests(SimpleTestCase):
    def test_handler_module_exists_with_core_capabilities(self):
        self.assertTrue(_HANDLER_JS.exists(), str(_HANDLER_JS))
        src = _HANDLER_JS.read_text(encoding="utf-8")
        # Capabilities this module OWNS (async-CSS flip + delegated print/reload/img).
        for marker in (
            "data-rmc-async-style",
            "data-rmc-print",
            "data-rmc-reload",
            "data-rmc-img-fallback",
        ):
            self.assertIn(marker, src, marker)

    def test_module_does_not_double_handle_confirm(self):
        # data-rmc-confirm is owned by rmc-modal-intelligence.js (a rich sheet).
        # This module must NOT register a submit-confirm listener, or forms would
        # get BOTH the modal AND a native confirm().
        src = _HANDLER_JS.read_text(encoding="utf-8")
        self.assertNotIn("addEventListener('submit'", src)
        self.assertNotIn("window.confirm", src)

    def test_modal_engine_submits_forms_on_confirm(self):
        # The rich confirm handler re-dispatches via el.click(), a no-op on a
        # <form>. reRun must submit a form directly so form-level data-rmc-confirm
        # actually posts after the user confirms.
        src = _MODAL_JS.read_text(encoding="utf-8")
        self.assertIn("requestSubmit", src)
        self.assertIn('el.tagName === "FORM"', src)

    def test_shells_load_the_handler_module(self):
        for shell in _SHELLS:
            self.assertIn(
                "js/rmc-csp-handlers.js",
                shell.read_text(encoding="utf-8"),
                f"{shell} must load the CSP-safe handler module",
            )


class InlineHandlerConversionTests(SimpleTestCase):
    def test_no_inline_onsubmit_confirm_or_onclick_nav_in_converted_templates(self):
        # A strict script-src blocks these inline handlers; the burndown replaced
        # them with data-* markers. None may survive in a converted template.
        for path in _CONVERTED_TEMPLATES:
            body = path.read_text(encoding="utf-8")
            self.assertNotIn('onsubmit="return confirm', body, str(path))
            self.assertNotIn('onclick="window.print', body, str(path))
            self.assertNotIn('onclick="window.location.reload', body, str(path))


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
