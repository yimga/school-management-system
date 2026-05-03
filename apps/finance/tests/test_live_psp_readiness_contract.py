"""Repo-side PSP readiness artifacts exist (no live PSP proof asserted here)."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase


class LivePspReadinessContractTests(SimpleTestCase):
    def test_payment_docs_present(self):
        root = Path(__file__).resolve().parents[3]
        for rel in (
            "docs/payments/LIVE_PSP_READINESS_CHECKLIST.md",
            "docs/payments/PAYMENT_ENVIRONMENT_CONTRACT.md",
            "docs/payments/PAYMENT_BLOCKER_CLASSIFICATION.md",
            "docs/external_dependencies_register.json",
        ):
            self.assertTrue((root / rel).is_file(), msg=f"missing {rel}")

    def test_payment_environment_contract_has_safe_headers_only(self):
        root = Path(__file__).resolve().parents[3]
        text = (root / "docs/payments/PAYMENT_ENVIRONMENT_CONTRACT.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("STRIPE_SECRET_KEY", text)
        self.assertIn("never", text.lower())
        self.assertIn("secrets", text.lower())
