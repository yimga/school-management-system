"""Workflow 13 (Payroll) — payslip-line generation matches the live schema.

Plain ``unittest`` (no DB) so it runs even where the Django test runner can't.

Guards the 2026-06-10 fix: migration 0005 collapsed PayslipLine to
(line_type, description, amount) with line_type ∈ {EARNING, DEDUCTION}, dropping
the label/code/employer_amount fields and the CONTRIBUTION choice. But
services.generate_payslips still wrote label=/code=/employer_amount= and
LineType.CONTRIBUTION, so EVERY payslip run crashed (TypeError / AttributeError)
— both the Generate-Payslips UI action and the run_payroll_cycle command.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

REPO = Path(__file__).resolve().parent.parent.parent.parent


class PayslipLineSchemaMatchTests(unittest.TestCase):

    def test_model_schema_is_earning_deduction_description(self) -> None:
        from apps.payroll.models import PayslipLine

        names = {f.name for f in PayslipLine._meta.get_fields()}
        self.assertIn("description", names)
        self.assertNotIn("label", names)
        self.assertNotIn("code", names)
        self.assertNotIn("employer_amount", names)
        self.assertFalse(hasattr(PayslipLine.LineType, "CONTRIBUTION"))

    def test_generate_payslips_uses_current_fields_only(self) -> None:
        src = (REPO / "apps" / "payroll" / "services.py").read_text(
            encoding="utf-8", errors="replace"
        )
        # Isolate the generate_payslips body so we don't trip on comments elsewhere.
        start = src.index("def generate_payslips(")
        body = src[start:]
        self.assertIn("description=", body)
        # None of the removed field names / choice may appear as live kwargs.
        self.assertNotIn("label=", body)
        self.assertNotIn("code=", body)
        self.assertNotIn("employer_amount=", body)
        self.assertNotIn("LineType.CONTRIBUTION", body)


if __name__ == "__main__":
    unittest.main()
