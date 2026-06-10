"""Workflow 2 (Marks & Gradebook) — grade-import route health.

Plain ``unittest`` (no DB) so it runs even where the Django test runner can't.

Locks two facts established by the 2026-06-10 gradebook audit:

1. The live grade-import chain is wired against the REAL model
   (``apps.analytics.models.GradeImportJob``) and its routes resolve.
2. The retired ``evals:grade_import_job_detail`` route — which pointed at a
   triple-dead view (phantom ``evals.models.GradeImportJob`` model, no template,
   no live caller) — stays retired. Its host module ``views_import_enhanced.py``
   is gone; this guards against a well-meaning re-wire of dead code.
"""

from __future__ import annotations

import os
import unittest

import django
from django.urls import NoReverseMatch, reverse

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()


class GradeImportRouteHealthTests(unittest.TestCase):

    def test_live_import_routes_resolve(self) -> None:
        for name in (
            "evals:grade_import_upload",
            "evals:grade_import_apply_api",
            "evals:import_job_monitor",
            "evals:teacher_marks_entry",
        ):
            with self.subTest(route=name):
                self.assertTrue(reverse(name))

    def test_dead_job_detail_route_stays_retired(self) -> None:
        with self.assertRaises(NoReverseMatch):
            reverse("evals:grade_import_job_detail", kwargs={"job_id": 1})

    def test_live_monitor_uses_real_model(self) -> None:
        # The live monitor reads the registered analytics model, not the phantom.
        from django.apps import apps as django_apps

        model = django_apps.get_model("analytics", "GradeImportJob")
        self.assertEqual(model.__module__, "apps.analytics.models")

    def test_dead_module_is_gone(self) -> None:
        import importlib.util

        self.assertIsNone(
            importlib.util.find_spec("apps.evals.views_import_enhanced"),
            msg="views_import_enhanced.py was retired; it must not return",
        )


if __name__ == "__main__":
    unittest.main()
