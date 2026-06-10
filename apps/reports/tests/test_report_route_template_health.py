"""Workflow 5 (Report Cards) — route + template health.

Plain ``unittest`` (no DB) so it runs even where the Django test runner can't.

The 2026-06-10 audit verified the report-card chain is connected end to end
(parent download → term/annual_report_context → real evals.Evaluation data →
template render → TermPublishStatus gating). The only issue was a dead
``REPORT_PREVIEW_TEMPLATES`` dict in views.py pointing at two templates that do
not exist — removed. This locks the live routes + their templates and guards the
dead dict from returning.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

import django
from django.template.loader import get_template
from django.urls import reverse

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

REPO = Path(__file__).resolve().parent.parent.parent.parent


class ReportRouteTemplateHealthTests(unittest.TestCase):

    def test_live_report_routes_resolve(self) -> None:
        self.assertTrue(
            reverse("reports:parent_download_term_report", kwargs={"student_id": 1})
        )
        self.assertTrue(
            reverse("reports:parent_download_annual_report", kwargs={"student_id": 1})
        )
        self.assertTrue(reverse("reports:publish_term_results"))

    def test_default_report_templates_exist(self) -> None:
        for tpl in (
            "reports/term_report.html",
            "reports/annual_report.html",
            "reports/publish_term.html",
        ):
            with self.subTest(template=tpl):
                self.assertTrue(get_template(tpl))

    def test_dead_preview_template_dict_stays_removed(self) -> None:
        src = (REPO / "apps" / "reports" / "views.py").read_text(
            encoding="utf-8", errors="replace"
        )
        # The dict named two non-existent templates; it must not come back.
        self.assertNotIn("REPORT_PREVIEW_TEMPLATES", src)
        self.assertNotIn("preview_term_card.html", src)


if __name__ == "__main__":
    unittest.main()
