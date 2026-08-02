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
            "rmc_dashboard_visual_preset_choices": [
                ("soft-glass", "Soft Glass"),
                ("bento-focus", "Bento Focus"),
            ],
            "rmc_school_readiness": {
                "ok": True,
                "meter_percent": 50,
                "phases": [
                    {"key": "provision", "label": "Provisioned", "done": True, "detail": "ok"},
                    {"key": "configure", "label": "Configured", "done": False, "detail": "50%"},
                    {"key": "launch", "label": "Launch ready", "done": False, "detail": "2 blockers"},
                    {"key": "operate", "label": "Daily operations", "done": False, "detail": "unknown"},
                ],
                "provisioning_slo": {"tone": "progress", "label": "In progress"},
            },
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
        self.assertIn("--rmc-setup-ring-pct: 50%", out)
        self.assertIn("data-rmc-readiness-train", out)
        # stage count is real completed/total, not a fabricated "0/15"
        self.assertIn("3/9", out)
        # step labels + next action come straight from onboarding data
        self.assertIn("Create academic year", out)
        self.assertIn("Configure academic year", out)
        # heading is terminology-aware ("school" by default, tenant term otherwise)
        self.assertIn("Set up your", out)


_WIZARD_STAGES = {
    "stages": [
        {
            "key": "configure",
            "label": "Configure",
            "description": "Set up how your school runs.",
            "step": 2,
            "done": 1,
            "total": 2,
            "cards": [
                {
                    "key": "ai_helpcenter_knowledge_injection",
                    "title": "AI Helpcenter Knowledge Injection",
                    "status": "not_started",
                    "minutes": 10,
                    "steps": 4,
                },
                {
                    "key": "cashless_campus_pos",
                    "title": "Cashless Campus POS",
                    "status": "done",
                    "minutes": 8,
                    "steps": 4,
                },
            ],
        },
    ],
    "overall": {"done": 1, "total": 2, "pct": 50},
}


class SetupCommandSurfaceWizardStageTests(SimpleTestCase):
    """The richer branch: real setup-studio wizards grouped by lifecycle stage."""

    def _render(self, **overrides) -> str:
        ctx = {
            "show_setup_landing": True,
            "backend_show_legacy_dashboard": False,
            "rmc_school_onboarding": _ONBOARDING,
            "rmc_setup_wizard_stages": _WIZARD_STAGES,
        }
        ctx.update(overrides)
        return render_to_string(_PARTIAL, ctx)

    def test_renders_real_wizard_cards_with_time_and_step_meta(self):
        out = self._render()
        self.assertIn("AI Helpcenter Knowledge Injection", out)
        self.assertIn("Cashless Campus POS", out)
        # real estimated_minutes + step count meta (matches the preview)
        self.assertIn("10 min", out)
        self.assertIn("4 steps", out)
        # lifecycle stage heading + per-stage count
        self.assertIn("Configure", out)
        self.assertIn("1/2", out)
        # the done card carries the is-done modifier
        self.assertIn("is-done", out)

    def test_falls_back_to_milestone_cards_when_no_wizard_stages(self):
        out = self._render(rmc_setup_wizard_stages={"stages": []})
        self.assertIn("Create academic year", out)  # milestone branch

    def test_wizard_branch_classes_all_defined_in_css(self):
        out = self._render()
        css = _CSS.read_text(encoding="utf-8")
        # Only scan class="" attribute values — not script src filenames like
        # js/rmc-setup-surface-tabs.js, which are not CSS classes.
        class_tokens = " ".join(re.findall(r'class="([^"]*)"', out))
        for cls in set(re.findall(r"rmc-setup-surface[\w-]*", class_tokens)):
            self.assertIn("." + cls, css, f"{cls} referenced but undefined in CSS")


class SetupWizardStagesHelperTests(SimpleTestCase):
    """build_setup_wizard_stages decorates the real registry — no DB, no school."""

    def test_builds_lifecycle_stages_from_real_registry(self):
        from apps.setup_studio.setup_surface import build_setup_wizard_stages

        result = build_setup_wizard_stages(None)
        self.assertTrue(result["stages"], "expected non-empty wizard stages")
        keys = {c["key"] for s in result["stages"] for c in s["cards"]}
        self.assertIn("ai_helpcenter_knowledge_injection", keys)
        for stage in result["stages"]:
            self.assertTrue(stage["label"])
            self.assertEqual(stage["total"], len(stage["cards"]))
            for card in stage["cards"]:
                self.assertTrue(card["title"])
                self.assertGreaterEqual(card["minutes"], 0)
                self.assertGreaterEqual(card["steps"], 0)
                self.assertIn(card["status"], {"done", "in_progress", "not_started"})


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
        # Only scan class="" attribute values — script src filenames such as
        # js/rmc-setup-surface-readiness.js are not CSS classes.
        class_tokens = " ".join(re.findall(r'class="([^"]*)"', html))
        for cls in set(re.findall(r"rmc-setup-surface[\w-]*", class_tokens)):
            self.assertIn("." + cls, css, f"{cls} referenced in template but undefined in CSS")
