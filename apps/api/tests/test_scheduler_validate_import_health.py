"""Workflow 3 (Timetable/Scheduling) — scheduler-validate import health.

Plain ``unittest`` (no DB) so it runs even where the Django test runner can't.

Guards the 2026-06-10 fix: ``SchedulerValidateView`` imported ``Schedule`` from
``apps.academics.models`` (where it does NOT live — it's in
``apps.academics.scheduling``). That import sat inside a ``try`` whose ``except``
only catches ``Schedule.DoesNotExist``, so every
``GET /api/v1/scheduler/validate?schedule_id=…`` raised an uncaught ImportError
(HTTP 500). This locks the model's true home and the call-site signatures.
"""

from __future__ import annotations

import inspect
import os
import unittest
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

REPO = Path(__file__).resolve().parent.parent.parent.parent


class SchedulerValidateImportHealthTests(unittest.TestCase):

    def test_schedule_lives_in_scheduling_not_models(self) -> None:
        from apps.academics import models as academics_models
        from apps.academics.scheduling import Schedule

        self.assertEqual(Schedule.__module__, "apps.academics.scheduling")
        # The model is NOT exposed by apps.academics.models — importing it there
        # (as the buggy view did) raised ImportError.
        self.assertFalse(hasattr(academics_models, "Schedule"))

    def test_view_source_imports_schedule_from_scheduling(self) -> None:
        src = (REPO / "apps" / "api" / "views_v1.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertNotIn("from apps.academics.models import Schedule", src)
        self.assertIn("from apps.academics.scheduling import Schedule", src)

    def test_generator_signatures_match_call_site(self) -> None:
        from apps.academics.scheduling import ScheduleGenerator

        init = inspect.signature(ScheduleGenerator.__init__)
        self.assertIn("academic_year", init.parameters)
        self.assertIn("term", init.parameters)
        detect = inspect.signature(ScheduleGenerator.detect_conflicts)
        # detect_conflicts(self, schedule)
        self.assertIn("schedule", detect.parameters)


if __name__ == "__main__":
    unittest.main()
