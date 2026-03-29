"""Unit tests for doc/plan density canonical-artifact checks (stub detection)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from django.test import SimpleTestCase


def _load_module():
    root = Path(__file__).resolve().parents[3]
    path = root / "scripts" / "verify_doc_plan_density_discipline.py"
    spec = importlib.util.spec_from_file_location(
        "verify_doc_plan_density_discipline",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class DocPlanDensityDisciplineHelperTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._mod = _load_module()

    def test_constants_for_sot_markers(self):
        self.assertIn("RunMyCampus", self._mod._SOT_TITLE_SNIPPET)
        self.assertIn("At a glance", self._mod._SOT_SECTION_SNIPPET)
        self.assertIn("PATH_TO_100", self._mod._SOT_PATH_TO_100_SNIPPET)
        self.assertIn("BACKLOG", self._mod._SOT_BACKLOG_SNIPPET)
        self.assertGreaterEqual(self._mod._MIN_SOT_CHARS, 3000)
        self.assertGreaterEqual(self._mod._MIN_BACKLOG_CHARS, 1000)
