"""Unit tests for scripts/check_real_migration_drift.py classification logic.

We test the parser + classifier directly, not the subprocess invocation,
so the tests stay fast and don't need a working Django.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


def _load_drift_module():
    """Import the drift-check script as a module without running main()."""
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_real_migration_drift.py"
    spec = importlib.util.spec_from_file_location(
        "check_real_migration_drift", script_path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_real_migration_drift"] = module
    spec.loader.exec_module(module)
    return module


class ParseOperationsTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_drift_module()

    def test_parses_alter_field_block(self):
        out = (
            "Migrations for 'academics':\n"
            "  apps\\academics\\migrations\\0049_x.py\n"
            "    ~ Alter field uploaded_file on coursesyllabus\n"
            "    ~ Alter field currency on certificationfeetemplate\n"
        )
        ops = self.mod._parse_operations(out)
        self.assertEqual(len(ops), 2)
        self.assertEqual(ops[0]["app"], "academics")
        self.assertEqual(ops[0]["marker"], "~")
        self.assertEqual(
            ops[0]["text"], "Alter field uploaded_file on coursesyllabus"
        )

    def test_handles_multiple_apps(self):
        out = (
            "Migrations for 'analytics':\n"
            "  apps\\analytics\\migrations\\0014_x.py\n"
            "    ~ Alter field uploaded_file on gradeimportjob\n"
            "Migrations for 'billing':\n"
            "    ~ Alter field currency_code on billingaccount\n"
        )
        ops = self.mod._parse_operations(out)
        self.assertEqual(len(ops), 2)
        self.assertEqual(ops[0]["app"], "analytics")
        self.assertEqual(ops[1]["app"], "billing")

    def test_ignores_django_logging_noise(self):
        out = (
            "DEBUG 2026-05-15 sql query stuff\n"
            "Migrations for 'people':\n"
            "    ~ Alter field profile_photo on studentprofile\n"
            "INFO 2026-05-15 something else\n"
        )
        ops = self.mod._parse_operations(out)
        self.assertEqual(len(ops), 1)


class CosmeticClassifierTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_drift_module()

    def test_currency_field_alter_is_cosmetic(self):
        op = {
            "app": "billing",
            "marker": "~",
            "text": "Alter field currency_code on billingaccount",
        }
        self.assertTrue(self.mod._is_cosmetic(op))

    def test_upload_field_alter_is_cosmetic(self):
        for fieldname in ("uploaded_file", "attachment", "profile_photo", "pdf_file"):
            op = {
                "app": "x", "marker": "~",
                "text": f"Alter field {fieldname} on somemodel",
            }
            self.assertTrue(self.mod._is_cosmetic(op), msg=fieldname)

    def test_unknown_field_alter_is_real(self):
        op = {
            "app": "x", "marker": "~",
            "text": "Alter field some_new_business_logic_field on somemodel",
        }
        self.assertFalse(self.mod._is_cosmetic(op))

    def test_add_field_is_real(self):
        op = {"app": "x", "marker": "+", "text": "Add field foo on somemodel"}
        self.assertFalse(self.mod._is_cosmetic(op))

    def test_remove_field_is_real(self):
        op = {"app": "x", "marker": "-", "text": "Remove field foo on somemodel"}
        self.assertFalse(self.mod._is_cosmetic(op))

    def test_create_model_is_real(self):
        op = {"app": "x", "marker": "+", "text": "Create model NewModel"}
        self.assertFalse(self.mod._is_cosmetic(op))

    def test_malformed_op_text_is_real(self):
        # Defensive: anything that doesn't parse cleanly is treated as real
        # drift (better to false-positive than to silently allow a regression).
        op = {"app": "x", "marker": "~", "text": "Alter field"}
        self.assertFalse(self.mod._is_cosmetic(op))


if __name__ == "__main__":
    unittest.main()
