"""Backlog fix (2026-06-14) — Student 360 reads the real class placement.

Plain ``unittest`` (no DB) so it runs where the Django test runner can't.

Both the 360 summary service and the Academic-tab view imported a non-existent
``academics.ClassEnrollment`` inside a broad ImportError-swallowing ``except`` —
so the "Enrollments" count was permanently 0 and the "Recent enrollments" list
permanently empty. There is no historical per-year enrollment model; a student's
class placement is a single FK (``people.StudentProfile.classroom``). The fix
wires that real relationship in with the ``.classroom`` / ``.academic_year``
shape the template (student_360_page.html) expects.
"""

from __future__ import annotations

import inspect
import os
import pathlib
import unittest

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent


class Student360EnrollmentSourceTests(unittest.TestCase):

    def test_phantom_model_no_longer_imported(self) -> None:
        for rel in ("apps/student360/services.py", "apps/student360/views.py"):
            src = (REPO / rel).read_text(encoding="utf-8", errors="replace")
            self.assertNotIn("import ClassEnrollment", src, rel)

    def test_real_relationship_exists_on_model(self) -> None:
        from apps.people.models import StudentProfile

        names = {f.name for f in StudentProfile._meta.get_fields()}
        self.assertIn("classroom", names)
        self.assertIn("academic_year", names)

    def test_view_builds_template_compatible_enrollment(self) -> None:
        # The Academic tab template iterates academic.enrollments and reads
        # enr.classroom / enr.academic_year — the fix must preserve that shape.
        from apps.student360 import views

        src = inspect.getsource(views._student_360_academic)
        self.assertIn("SimpleNamespace", src)
        self.assertIn("classroom=student.classroom", src)
        self.assertIn("academic_year=", src)

    def test_summary_count_uses_classroom_fk(self) -> None:
        from apps.student360 import services

        src = inspect.getsource(services.get_student_360_summary)
        self.assertIn('getattr(student, "classroom_id", None)', src)


if __name__ == "__main__":
    unittest.main()
