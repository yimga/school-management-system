"""Full-audit follow-up (2026-06-10) — dead Grade endpoints retired.

Plain ``unittest`` (no DB) so it runs even where the Django test runner can't.

The repo-wide import audit flagged apps/academics/api_views.py importing a
non-existent ``evals.models.Grade`` x4. Both enclosing classes (GradeViewSet,
AssessmentResultsAPI) were UNROUTED dead code (apps/api/urls.py imports only
AttendanceViewSet + ScheduleConflictsAPI; both were on the dead-code-candidates
list). They were retired rather than rebuilt against a phantom model.

This guards: the dead classes stay gone, the phantom import stays gone, and the
two genuinely-routed classes survive.
"""

from __future__ import annotations

import os
import unittest

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()


class GradeViewSetRetiredTests(unittest.TestCase):

    def test_dead_classes_removed(self) -> None:
        from apps.academics import api_views

        self.assertFalse(hasattr(api_views, "GradeViewSet"))
        self.assertFalse(hasattr(api_views, "AssessmentResultsAPI"))

    def test_routed_classes_survive(self) -> None:
        from apps.academics import api_views

        self.assertTrue(hasattr(api_views, "AttendanceViewSet"))
        self.assertTrue(hasattr(api_views, "ScheduleConflictsAPI"))

    def test_phantom_grade_import_gone(self) -> None:
        from pathlib import Path

        repo = Path(__file__).resolve().parent.parent.parent.parent
        src = (repo / "apps" / "academics" / "api_views.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertNotIn("import Grade", src)
        self.assertNotIn("Grade.objects", src)

    def test_live_importer_still_imports(self) -> None:
        # apps/api/urls.py imports AttendanceViewSet + ScheduleConflictsAPI.
        import importlib

        importlib.import_module("apps.api.urls")


if __name__ == "__main__":
    unittest.main()
