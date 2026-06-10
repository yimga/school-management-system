"""Workflow 10 (Vocational/Competency) — endpoints degrade, don't crash.

Plain ``unittest`` (no DB) so it runs even where the Django test runner can't.

Guards the 2026-06-10 fix: VocationalLogHoursView / VocationalVerifySkillView /
VocationalDigitalBadgeView lazily imported apps.evals.models_enhanced — a module
that is unimportable (duplicate EvaluationEvidence → RuntimeError) and has no
migrations. That RuntimeError was NOT in the views' except tuples, so every call
raised an uncaught HTTP 500. The views now route through _vocational_module()
and return a clean HTTP 501 ("not enabled") until the feature is built.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

REPO = Path(__file__).resolve().parent.parent.parent.parent


class VocationalEndpointsDegradeTests(unittest.TestCase):

    def test_unavailable_response_is_501(self) -> None:
        from apps.api.views_v1 import _vocational_unavailable_response

        resp = _vocational_unavailable_response()
        self.assertEqual(resp.status_code, 501)

    def test_module_loader_returns_none_when_unimportable(self) -> None:
        # models_enhanced is currently unimportable; the loader must swallow that
        # and return None rather than propagate (the source of the old 500).
        from apps.api.views_v1 import _vocational_module

        # Either None (current, unbuilt) or a module (if later fixed+built) — but
        # never a raised exception.
        result = _vocational_module()
        self.assertTrue(result is None or hasattr(result, "__name__"))

    def test_all_three_endpoints_route_through_the_guard(self) -> None:
        src = (REPO / "apps" / "api" / "views_v1.py").read_text(
            encoding="utf-8", errors="replace"
        )
        # Each vocational endpoint must guard via _vocational_module(); none may
        # do a bare unguarded `from apps.evals.models_enhanced import` inside a try
        # whose except can't catch the import RuntimeError.
        self.assertEqual(src.count("me = _vocational_module()"), 3)
        self.assertNotIn("from apps.evals.models_enhanced import", src)


if __name__ == "__main__":
    unittest.main()
