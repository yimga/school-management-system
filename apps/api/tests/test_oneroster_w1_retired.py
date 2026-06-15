"""Address-the-backlog (2026-06-15) — oneroster W1 dead read-side retired.

Plain ``unittest`` (no DB).

apps/api/oneroster_w1_extensions.py kept only its two ROUTED bulk-write
endpoints (classes_bulk_post / enrollments_bulk_post). The unrouted read-side
helpers (lineitem_detail, staff_delta, demographics_delta, *_with_fields_mask,
_iter_classes_synthetic + the STUDIO_OS_10X_W1_D_VIEWS tuple) were retired —
they referenced models that do not exist (assessments.Evaluation,
grading.Evaluation, people.Employment, schools.Section, schools.Enrollment) and
had zero callers / zero routes.
"""

from __future__ import annotations

import os
import unittest

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()


class OneRosterW1RetiredTests(unittest.TestCase):

    def test_routed_endpoints_kept(self) -> None:
        from apps.api import oneroster_w1_extensions as m

        self.assertTrue(hasattr(m, "classes_bulk_post"))
        self.assertTrue(hasattr(m, "enrollments_bulk_post"))

    def test_dead_readside_retired(self) -> None:
        from apps.api import oneroster_w1_extensions as m

        for dead in (
            "lineitem_detail",
            "staff_delta",
            "demographics_delta",
            "classes_with_fields_mask",
            "enrollments_with_fields_mask",
            "_iter_classes_synthetic",
            "STUDIO_OS_10X_W1_D_VIEWS",
        ):
            self.assertFalse(hasattr(m, dead), f"{dead} should be retired")

    def test_no_phantom_model_imports_remain(self) -> None:
        import inspect

        from apps.api import oneroster_w1_extensions as m

        src = inspect.getsource(m)
        for phantom in (
            "assessments.models",
            "grading.models",
            "import Employment",
            "import Section",
            "import Enrollment",
        ):
            self.assertNotIn(phantom, src)

    def test_urls_still_resolve(self) -> None:
        # The routed endpoints must still import cleanly from the urlconf.
        from apps.api import urls  # noqa: F401


if __name__ == "__main__":
    unittest.main()
