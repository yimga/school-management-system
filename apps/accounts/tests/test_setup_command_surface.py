"""Onboarding setup-command-surface (the hero + progress ring + "Configure" stage +
wizard step cards shown on the default v3 admin canvas while a school is still
onboarding).

Renders the partial directly (no DB / no HTTP — dodges the slow test-DB + MFA gate)
and pins the gate-safety + wiring invariants the surface depends on.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.template.loader import render_to_string
from django.test import SimpleTestCase

_ROOT = Path(__file__).resolve().parents[3]
_PARTIAL = "partials/tenant/setup_command_surface.html"
_CSS = _ROOT / "static" / "css" / "rmc-setup-surface.css"
_DASHBOARD = _ROOT / "templates" / "accounts" / "backend_dashboard.html"

_ONBOARDING = {
    "percent": 55,
    "completed": 3,
    "total": 9,
    "next_action": {"label": "Configure academic year", "url": "/onboarding/year/"},
    "display_steps": [
        {"label": "Create academic year", "done": True, "link": "/y/"},
        {"label": "Add classrooms", "done": False, "link": "/c/"},
        {"label": "Invite teachers", "done": False, "link": ""},
    ],
}


class SetupCommandSurfaceRenderTests(SimpleTestCase):
    def _render(self, **overrides) -> str:
        ctx = {
            "show_setup_landing": True,
            "backend_show_legacy_dashboard": False,
            "rmc_school_onboarding": _ONBOARDING,
        }
        ctx.update(overrides)
        return render_to_string(_PARTIAL, ctx)

    def test_renders_nothing_when_landing_not_engaged(self):
        self.assertEqual(self._render(show_setup_landing=False).strip(), "")

    def test_renders_nothing_in_legacy_simple_view(self):
        # The ?simple=1 legacy stack already carries the full readiness cards;
        # the surface must suppress itself there to avoid duplicate onboarding UI.
        self.assertEqual(self._render(backend_show_legacy_dashboard=True).strip(), "")

    def test_renders_nothing_without_onboarding_data(self):
        self.assertEqual(self._render(rmc_school_onboarding={"total": 0}).strip(), "")

    def test_happy_path_carries_real_onboarding_data(self):
        out = self._render()
        # progress ring fed the real percent via an inline custom property
        self.assertIn("rmc-setup-surface__ring", out)
        self.assertIn("--rmc-setup-ring-pct: 55%", out)
        # stage count is real completed/total, not a fabricated "0/15"
        self.assertIn("3/9", out)
        # step labels + next action come straight from onboarding data
        self.assertIn("Create academic year", out)
        self.assertIn("Configure academic year", out)
        # heading is terminology-aware ("school" by default, tenant term otherwise)
        self.assertIn("Set up your", out)


class SetupCommandSurfaceContractTests(SimpleTestCase):
    def test_css_has_no_hardcoded_hex_or_rgb_colour(self):
        # Every colour must route through a semantic / brand token so the
        # dark-mode + tenant-brand cascades own the surface (off-token gate).
        css = _CSS.read_text(encoding="utf-8")
        self.assertNotRegex(css, r"#[0-9a-fA-F]{3,8}\b")
        self.assertNotRegex(css, r"\brgba?\(")

    def test_dashboard_wires_partial_and_stylesheet(self):
        html = _DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("partials/tenant/setup_command_surface.html", html)
        self.assertIn("css/rmc-setup-surface.css", html)

    def test_classes_referenced_are_defined_in_css(self):
        html = render_to_string(
            _PARTIAL,
            {
                "show_setup_landing": True,
                "backend_show_legacy_dashboard": False,
                "rmc_school_onboarding": _ONBOARDING,
            },
        )
        css = _CSS.read_text(encoding="utf-8")
        for cls in set(re.findall(r"rmc-setup-surface[\w-]*", html)):
            self.assertIn("." + cls, css, f"{cls} referenced in template but undefined in CSS")
