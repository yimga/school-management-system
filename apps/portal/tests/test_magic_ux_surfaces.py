"""Magic UX surfaces — analytics decision overview + student DE empty panels."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase


def _portal_shell_render_ctx(extra: dict) -> dict:
    """Minimal keys expected by portal_base-like ancestors under instrumented test render."""
    base = {"LANGUAGE_CODE": getattr(settings, "LANGUAGE_CODE", "en")}
    base.update(extra)
    return base


class DecisionIntelligenceMagicUxTests(TestCase):
    databases = {"default"}

    def test_insights_empty_branch_action_first(self):
        req = RequestFactory().get("/analytics/")
        req.user = AnonymousUser()
        html = render_to_string(
            "analytics/decision_intelligence_dashboard.html",
            _portal_shell_render_ctx(
                {
                    "insights": [],
                    "global_rollups": [],
                    "surface_key": "overview",
                    "show_founder_nav": False,
                    "rmc_conversion_single_action_enforced": True,
                }
            ),
            request=req,
        )
        self.assertIn("rmc-empty", html)
        self.assertIn("No surfaced insights yet", html)
        self.assertIn('data-task="report_generation"', html)
        self.assertIn("Open governed report builder", html)


class DecisionEngineStudentEmptyMagicUxTests(SimpleTestCase):
    def test_empty_student_surface_has_primary_empty_state(self):
        html = render_to_string(
            "components/decision_engine_surface.html",
            {
                "de_eyebrow": "Student",
                "de_headline_label": "Status",
                "de_headline_value": "Ready",
            },
        )
        self.assertIn('data-rmc-student-de-empty="1"', html)
        self.assertIn("dashboard-empty-state", html)
        self.assertIn('data-task="student_home"', html)
