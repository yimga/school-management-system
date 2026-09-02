"""Metric 25 — counselor caseload constructs window.rmcCRDT for student_note."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup

COUNSELOR_CASELOAD = (
    Path(__file__).resolve().parents[3] / "templates" / "staff" / "counselor_caseload.html"
)


class StudentNoteCRDTBrowserClientWiringTests(SimpleTestCase):
    def test_enhance_script_constructs_rmc_crdt_client(self):
        root = Path(__file__).resolve().parents[3]
        js = (
            root / "static" / "js" / "_pages" / "rmc-student-note-crdt-enhance.js"
        ).read_text(encoding="utf-8")
        self.assertIn("window.rmcCRDT", js)
        self.assertIn("rmcCRDT.Client", js)
        self.assertIn("lwwSet", js)
        self.assertIn('data-rmc-crdt-entity="student_note"', js)
        self.assertIn("student_note", js)

    def test_counselor_caseload_template_wires_enhance_script(self):
        root = Path(__file__).resolve().parents[3]
        tpl = (root / "templates" / "staff" / "counselor_caseload.html").read_text(
            encoding="utf-8"
        )
        # rmc-student-note-crdt-enhance.js builds window.rmcCRDT by reading these
        # two attributes off the DOM, so they have to be emitted; the script name
        # itself is a {% static %} argument and stays a read.
        assert_markup(
            self,
            COUNSELOR_CASELOAD,
            'data-rmc-crdt-entity="student_note"',
            "data-rmc-crdt-key=",
        )
        self.assertIn('data-rmc-crdt-entity="student_note"', tpl)
        self.assertIn("data-rmc-crdt-key=", tpl)
        self.assertIn("rmc-student-note-crdt-enhance.js", tpl)
