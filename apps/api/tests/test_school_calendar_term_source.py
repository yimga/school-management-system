"""Backlog fix (2026-06-10) — school-calendar runtime reads the real Term model.

Plain ``unittest`` (no DB).

school_calendar_runtime imported a non-existent ``academics.AcademicTerm`` inside
``except ImportError`` — so the calendar API silently always returned empty terms.
The real model is ``academics.Term`` (window stored as start_date/end_date, not
starts_on/ends_on), so the fix corrects both the model and the field names
(including the un-guarded ``order_by`` that would otherwise FieldError).
"""

from __future__ import annotations

import os
import pathlib
import unittest

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent


class SchoolCalendarTermSourceTests(unittest.TestCase):

    def test_uses_real_term_model_and_fields(self) -> None:
        src = (REPO / "apps" / "api" / "runtime_endpoints.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("from apps.academics.models import Term", src)
        self.assertNotIn("import AcademicTerm", src)
        self.assertNotIn('order_by("starts_on")', src)
        self.assertIn('order_by("start_date")', src)

    def test_term_query_compiles(self) -> None:
        from apps.academics.models import Term

        q = Term.objects.filter(school_id=1).order_by("start_date")[:64]
        self.assertTrue(str(q.query))
        names = {f.name for f in Term._meta.get_fields()}
        self.assertTrue({"start_date", "end_date", "name", "school"} <= names)


if __name__ == "__main__":
    unittest.main()
