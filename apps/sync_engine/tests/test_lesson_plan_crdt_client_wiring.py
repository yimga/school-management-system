"""Metric 25 — lesson-plan page constructs window.rmcCRDT (browser client callers)."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import (
    assert_loads_static,
    assert_markup,
)

_TN_ROOT = Path(__file__).resolve().parents[3]


class LessonPlanCRDTBrowserClientWiringTests(SimpleTestCase):
    def test_enhance_script_constructs_rmc_crdt_client(self):
        root = Path(__file__).resolve().parents[3]
        js = (root / "static" / "js" / "_pages" / "rmc-lesson-plan-crdt-enhance.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("window.rmcCRDT", js)
        self.assertIn("rmcCRDT.Client", js)
        self.assertIn("lwwSet", js)
        self.assertIn('data-rmc-crdt-entity="lesson_plan"', js)
        self.assertIn("lesson_plan", js)

    def test_lesson_notes_template_wires_enhance_script(self):
        root = Path(__file__).resolve().parents[3]
        tpl = (root / "templates" / "teacher" / "lesson_notes.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("data-rmc-crdt-entity=\"lesson_plan\"", tpl)
        self.assertIn("data-rmc-crdt-key=\"draft-title\"", tpl)
        self.assertIn("rmc-lesson-plan-crdt-enhance.js", tpl)
        # The CRDT hooks are attributes the page must carry, and the enhance
        # script is a {% static %} tag -- neither survives an emptied template.
        assert_markup(self, _TN_ROOT / "templates/teacher/lesson_notes.html",
                      'data-rmc-crdt-entity="lesson_plan"')
        assert_loads_static(self, _TN_ROOT / "templates/teacher/lesson_notes.html",
                            "js/_pages/rmc-lesson-plan-crdt-enhance.js")
