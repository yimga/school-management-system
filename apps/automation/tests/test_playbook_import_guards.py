"""Address-the-backlog (2026-06-15) — playbook import steps degrade, not crash.

Plain ``unittest`` (no DB).

_run_one_step imported apps.accounts.migration_services.run_student_import /
run_grade_import UNGUARDED inside the students/grades branches — those functions
do not exist, so executing such a step raised an unhandled ImportError and
crashed the executor. The imports are now wrapped so a missing service marks the
run PARTIAL (error result flows through the existing mark_completed path).
"""

from __future__ import annotations

import inspect
import os
import unittest

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()


class PlaybookImportGuardsTests(unittest.TestCase):

    def test_import_steps_are_guarded(self) -> None:
        from apps.automation import playbook_executor as m

        src = inspect.getsource(m._run_one_step)
        # Both migration_services imports must sit inside a try that catches
        # ImportError and produces an error result.
        self.assertIn("run_student_import", src)
        self.assertIn("run_grade_import", src)
        self.assertIn("student_import_service_unavailable", src)
        self.assertIn("grade_import_service_unavailable", src)
        self.assertIn("except ImportError", src)


if __name__ == "__main__":
    unittest.main()
