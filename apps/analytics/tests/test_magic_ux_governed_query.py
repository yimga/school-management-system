"""Magic UX governed query / decision analytics instrumentation."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase


def _portal_shell_render_ctx(extra: dict) -> dict:
    base = {"LANGUAGE_CODE": getattr(settings, "LANGUAGE_CODE", "en")}
    base.update(extra)
    return base


class GovernedReportBuilderMagicUxTests(TestCase):
    databases = {"default"}

    def test_strict_preview_primary_exports_more_dropdown(self):
        req = RequestFactory().get("/analytics/")
        req.user = AnonymousUser()
        html = render_to_string(
            "analytics/governed_report_builder.html",
            _portal_shell_render_ctx(
                {
                    "school_id": str(uuid.uuid4()),
                    "rmc_conversion_single_action_enforced": True,
                }
            ),
            request=req,
        )
        self.assertIn('data-rmc-governed-report-builder="1"', html)
        self.assertIn('data-task="governed_report_export"', html)
        self.assertIn('id="gr-preview"', html)
        pv = html.index('id="gr-preview"')
        self.assertIn("btn-primary", html[pv : pv + 160])
        self.assertIn("rmc-conversion-more-actions", html)
        self.assertIn("governed-export-csv", html)

    def test_relaxed_multiple_export_buttons_visible(self):
        req = RequestFactory().get("/analytics/")
        req.user = AnonymousUser()
        html = render_to_string(
            "analytics/governed_report_builder.html",
            _portal_shell_render_ctx(
                {
                    "school_id": str(uuid.uuid4()),
                    "rmc_conversion_single_action_enforced": False,
                }
            ),
            request=req,
        )
        self.assertGreaterEqual(html.count("gr-export-csv"), 1)
        self.assertGreaterEqual(html.count("gr-export-json"), 1)


class DecisionOverviewMagicUxMarkersTests(TestCase):
    databases = {"default"}

    def test_surface_wrap_has_report_generation_task(self):
        req = RequestFactory().get("/analytics/")
        req.user = AnonymousUser()
        html = render_to_string(
            "analytics/decision_intelligence_dashboard.html",
            _portal_shell_render_ctx(
                {
                    "insights": [
                        {"audience": "Admins", "title": "T", "explanation": "E"}
                    ],
                    "global_rollups": [],
                    "surface_key": "overview",
                    "show_founder_nav": False,
                }
            ),
            request=req,
        )
        self.assertIn('data-task="report_generation"', html)
