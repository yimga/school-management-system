"""Unit tests for Gilead full-tree classifier path rules (no repo walk)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from django.test import SimpleTestCase


def _load_classifier_module():
    root = Path(__file__).resolve().parents[3]
    path = root / "scripts" / "verify_gilead_full_tree_classification.py"
    spec = importlib.util.spec_from_file_location(
        "verify_gilead_full_tree_classification",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class GileadFullTreeClassificationHelperTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._mod = _load_classifier_module()

    def test_allowed_locale_po(self):
        self.assertTrue(
            self._mod._is_allowed_reference_path("locale/en/LC_MESSAGES/django.po")
        )

    def test_allowed_app_fixtures_json(self):
        self.assertTrue(
            self._mod._is_allowed_reference_path("apps/schools/fixtures/demo.json")
        )

    def test_allowed_docs_and_migrations(self):
        self.assertTrue(self._mod._is_allowed_reference_path("docs/README.md"))
        self.assertTrue(
            self._mod._is_allowed_reference_path(
                "apps/schools/migrations/0001_initial.py"
            )
        )

    def test_runtime_templates_not_allowlisted_by_path(self):
        self.assertFalse(
            self._mod._is_allowed_reference_path("templates/schools/dashboard.html")
        )

    def test_po_in_text_extensions(self):
        self.assertIn(".po", self._mod.TEXT_EXTENSIONS)
