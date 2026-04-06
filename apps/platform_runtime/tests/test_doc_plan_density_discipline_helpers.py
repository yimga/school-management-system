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

    def test_parse_args_base_default_is_repo_root(self):
        args = self._mod.parse_args([])
        self.assertEqual(args.base, str(self._mod.DEFAULT_ROOT))

    def test_resolve_base_accepts_existing_directory(self):
        here = Path(__file__).resolve().parents[3]
        resolved = self._mod._resolve_base(str(here))
        self.assertEqual(resolved, here.resolve())

    def test_resolve_base_rejects_missing_directory(self):
        with self.assertRaises(ValueError):
            self._mod._resolve_base("definitely_missing_doc_plan_density_base")

    def test_inprocess_main_rejects_invalid_base(self):
        self.assertEqual(
            self._mod.main(["--base", "definitely_missing_doc_plan_density_main"]),
            1,
        )

    def test_main_passes_repo_with_default_base(self):
        self.assertEqual(self._mod.main([]), 0)
