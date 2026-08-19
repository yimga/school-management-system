"""Tenant /admin/ header chrome must not depend on Bootstrap CSS.

`templates/admin/base_site.html` loads `vendor/bootstrap/css/bootstrap.min.css`
ONLY under ``{% if is_manager_host %}`` — deliberately, so Bootstrap's Reboot never
fights Unfold/Tailwind on the tenant backoffice. `bootstrap.bundle.min.js`, however,
loads on BOTH shells.

That asymmetry shipped a full-surface break: `components/rmc_tenant_header_utilities.html`
is written against Bootstrap's `.dropdown` primitives and carries neither ``hidden`` nor
``d-none``, so with the JS but not the CSS its ~600px panel rendered permanently OPEN and
IN NORMAL FLOW inside ``<header class="rmc-app-shell__header">``. The header's ``auto``
grid row grew to the panel's height (~80% of the viewport) and vertically centred the
brand / search / Home / avatar row inside it — on EVERY page under tenant /admin/.

These tests pin the two halves of the repair:
  * the Utilities component owns its own open/closed geometry, and
  * the tenant-only stylesheet supplies the Bootstrap LAYOUT utilities the shared
    header chrome references.

Static-source assertions are the honest seal here: the defect is a missing CSS
declaration, and no amount of Django-side rendering can observe layout.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

REPO_ROOT = Path(settings.BASE_DIR)
CSS_DIR = REPO_ROOT / "static" / "css"
TEMPLATES_DIR = REPO_ROOT / "templates"

UTILITIES_CSS = CSS_DIR / "rmc-header-utilities.css"
TENANT_ADMIN_CSS = CSS_DIR / "admin-nav-bridge-tenant.css"
BASE_SITE = TEMPLATES_DIR / "admin" / "base_site.html"
NAV_BRIDGE = TEMPLATES_DIR / "components" / "admin_nav_bridge.html"
UTILITIES_TPL = TEMPLATES_DIR / "components" / "rmc_tenant_header_utilities.html"


def _rule_body(css: str, selector: str) -> str:
    """Return the declaration block for an exact top-level ``selector``, or ""."""
    pattern = re.compile(
        r"(?:^|\})\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", re.MULTILINE
    )
    match = pattern.search(css)
    return match.group(1) if match else ""


class TenantAdminBootstrapAsymmetryTests(SimpleTestCase):
    """Document the shell invariant the rest of the file defends."""

    def test_bootstrap_css_is_manager_host_only_but_js_is_not(self):
        base_site = BASE_SITE.read_text(encoding="utf8")
        lines = base_site.splitlines()
        index = next(
            i
            for i, line in enumerate(lines)
            if "vendor/bootstrap/css/bootstrap.min.css" in line
        )
        preceding = "\n".join(lines[max(0, index - 3) : index])
        self.assertIn(
            "is_manager_host",
            preceding,
            "bootstrap.min.css is expected to stay manager-host-gated; if that "
            "changed, re-evaluate the compat layer this module defends.",
        )
        self.assertIn(
            "vendor/bootstrap/js/bootstrap.bundle.min.js",
            base_site,
            "Bootstrap JS drives the Utilities dropdown on both shells.",
        )

    def test_tenant_admin_header_includes_the_utilities_dropdown(self):
        nav_bridge = NAV_BRIDGE.read_text(encoding="utf8")
        self.assertIn("components/rmc_tenant_header_utilities.html", nav_bridge)


class UtilitiesMenuOwnsItsGeometryTests(SimpleTestCase):
    """The component must be correct on a shell with no Bootstrap CSS."""

    def setUp(self):
        self.css = UTILITIES_CSS.read_text(encoding="utf8")

    def test_menu_is_display_none_by_default(self):
        body = _rule_body(self.css, ".rmc-header-utilities__menu")
        self.assertTrue(body, "no top-level .rmc-header-utilities__menu rule found")
        self.assertRegex(
            body,
            r"display\s*:\s*none",
            "Closed state must not be borrowed from Bootstrap's .dropdown-menu — "
            "without it the panel renders in-flow and inflates the /admin/ header.",
        )

    def test_menu_is_taken_out_of_flow(self):
        body = _rule_body(self.css, ".rmc-header-utilities__menu")
        self.assertRegex(
            body,
            r"position\s*:\s*absolute",
            "An in-flow panel resizes the pinned shell header.",
        )

    def test_open_state_is_shown(self):
        body = _rule_body(self.css, ".rmc-header-utilities__menu.show")
        self.assertRegex(
            body,
            r"display\s*:\s*block",
            "Bootstrap JS toggles .show; the stylesheet must react to it.",
        )

    def test_template_relies_on_the_show_class_contract(self):
        markup = UTILITIES_TPL.read_text(encoding="utf8")
        self.assertIn('data-bs-toggle="dropdown"', markup)
        self.assertIn("rmc-header-utilities__menu", markup)


class TenantAdminBootstrapLayoutShimTests(SimpleTestCase):
    """Layout utilities the shared header markup references must exist."""

    #: Bootstrap classes used by the tenant /admin/ header that carry LAYOUT.
    REQUIRED = {
        "d-none": r"display\s*:\s*none",
        "position-relative": r"position\s*:\s*relative",
        "position-absolute": r"position\s*:\s*absolute",
        "start-0": r"left\s*:\s*0",
        "top-100": r"top\s*:\s*100%",
    }

    def test_shim_is_loaded_only_on_the_tenant_admin_shell(self):
        base_site = BASE_SITE.read_text(encoding="utf8")
        self.assertIn("css/admin-nav-bridge-tenant.css", base_site)
        lines = base_site.splitlines()
        index = next(
            i for i, line in enumerate(lines) if "admin-nav-bridge-tenant.css" in line
        )
        self.assertIn(
            "if not is_manager_host",
            "\n".join(lines[max(0, index - 2) : index]),
            "The shim must not double up with real Bootstrap on the manager shell.",
        )

    def test_every_referenced_layout_utility_is_defined(self):
        css = TENANT_ADMIN_CSS.read_text(encoding="utf8")
        missing = [
            name
            for name, declaration in self.REQUIRED.items()
            if not re.search(
                r"\." + re.escape(name) + r"\s*[,{][^}]*?" + declaration,
                css,
                re.DOTALL,
            )
        ]
        self.assertEqual(
            missing,
            [],
            f"Undefined on the tenant /admin/ shell (Bootstrap absent): {missing}",
        )

    def test_header_markup_uses_no_unshimmed_layout_utility(self):
        """A new Bootstrap layout class in the header must come with a shim."""
        known_elsewhere = {"visually-hidden", "dropdown-menu", "dropdown-toggle"}
        bootstrap_layout = {
            "d-none",
            "d-flex",
            "d-block",
            "d-grid",
            "d-inline-flex",
            "position-absolute",
            "position-relative",
            "position-fixed",
            "start-0",
            "end-0",
            "top-0",
            "top-100",
            "w-100",
            "h-100",
        }
        markup = NAV_BRIDGE.read_text(encoding="utf8")
        used = {
            token
            for match in re.finditer(r'class="([^"]+)"', markup)
            for token in match.group(1).split()
            if token in bootstrap_layout
        }
        unshimmed = sorted(used - set(self.REQUIRED) - known_elsewhere)
        self.assertEqual(
            unshimmed,
            [],
            "admin_nav_bridge.html gained Bootstrap layout classes with no tenant "
            f"shim: {unshimmed}. Add them to admin-nav-bridge-tenant.css + REQUIRED.",
        )
