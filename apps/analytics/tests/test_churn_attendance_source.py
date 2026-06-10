"""Workflow 4 (Attendance) — churn-risk attendance source health.

Plain ``unittest`` (no DB) so it runs even where the Django test runner can't.

Guards the 2026-06-10 fix: ``ChurnRiskPredictor.extract_features`` computed the
attendance rate from ``apps.analytics.models.AttendanceLog`` — a ``date``+``status``
stub with NO ``student`` field. ``filter(student=…)`` raised FieldError, which the
surrounding ``except`` swallowed, silently pinning every student's attendance_rate
to 100% and severing attendance from churn scoring. The fix reads the real
``apps.academics.models.Attendance`` (student FK, status ``present``/…).
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

REPO = Path(__file__).resolve().parent.parent.parent.parent


class ChurnAttendanceSourceTests(unittest.TestCase):

    def test_extract_features_reads_real_attendance_model(self) -> None:
        src = (REPO / "apps" / "analytics" / "ml_predictions.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("from apps.academics.models import Attendance", src)
        # Must NOT regress to the student-less analytics stub.
        self.assertNotIn("from apps.analytics.models import AttendanceLog", src)

    def test_real_attendance_model_supports_the_query(self) -> None:
        from apps.academics.models import Attendance

        field_names = {f.name for f in Attendance._meta.get_fields()}
        self.assertIn("student", field_names)
        self.assertIn("date", field_names)
        status_values = {c[0] for c in Attendance._meta.get_field("status").choices}
        self.assertIn("present", status_values)

    def test_analytics_stub_still_lacks_student(self) -> None:
        # The stub remains student-less; this is why the old code path was broken.
        from apps.analytics.models import AttendanceLog

        names = {f.name for f in AttendanceLog._meta.get_fields()}
        self.assertNotIn("student", names)


if __name__ == "__main__":
    unittest.main()
