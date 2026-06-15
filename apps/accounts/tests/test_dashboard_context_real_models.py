"""Gap-closure (2026-06-14) — dashboard context reads real models / degrades safe.

Plain ``unittest`` (no DB).

apps/accounts/context_processors.py::dashboard_context had three phantom
imports that silently broke live dashboard metrics:

* PARENT block imported ``apps.attendance.models.StudentAttendance`` (no such
  model) and filtered ``status="PRESENT"`` -> every guardian saw
  ``parent_avg_attendance`` = 0. Real model is ``academics.Attendance`` whose
  status values are lowercase (``Attendance.Status.PRESENT`` == "present").
* STUDENT block imported ``evals.MarkEntry`` EAGERLY at the top of the block.
  Since that model does not exist, the ImportError aborted the ENTIRE student
  metrics block — including the correctly-written real-attendance sub-block —
  so students got no attendance/average/pending at all.

evals.MarkEntry and academics.Assignment genuinely have no live model, so they
are kept as guarded best-effort imports (degrade each metric to 0) instead of
nuking the whole block. The parent fix wires the real Attendance model.
"""

from __future__ import annotations

import os
import pathlib
import unittest

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent
SRC = (
    REPO / "apps" / "accounts" / "context_processors.py"
).read_text(encoding="utf-8", errors="replace")


class DashboardContextRealModelsTests(unittest.TestCase):

    def test_no_phantom_attendance_model(self) -> None:
        self.assertNotIn("apps.attendance.models", SRC)
        self.assertNotIn('status="PRESENT"', SRC)

    def test_parent_uses_real_attendance_enum(self) -> None:
        from apps.academics.models import Attendance

        # The real enum value is lowercase; the old literal "PRESENT" matched 0.
        self.assertEqual(str(Attendance.Status.PRESENT), "present")
        self.assertIn("from apps.academics.models import Attendance", SRC)
        self.assertIn("status=Attendance.Status.PRESENT", SRC)

    def test_markentry_import_is_guarded_not_eager(self) -> None:
        # The phantom MarkEntry import must sit inside a try (guarded), never
        # eagerly at the top of the student block where it aborts everything.
        idx = SRC.index("from apps.evals.models import MarkEntry")
        preceding = SRC[:idx]
        # The nearest control keyword before the import must be a `try:`.
        self.assertGreater(
            preceding.rindex("try:"),
            preceding.rindex("student_profile = user.student_profile"),
            "MarkEntry import is not guarded by a try after student_profile",
        )

    def test_soft_failures_cover_importerror(self) -> None:
        from apps.accounts.context_processors import CONTEXT_SOFT_FAILURES

        self.assertIn(ImportError, CONTEXT_SOFT_FAILURES)


if __name__ == "__main__":
    unittest.main()
