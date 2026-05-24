"""Global-local gap closure (batch 1488) — contract pins for billing.

Each class verifies that the phase's audit artifact under docs/generated/ exists
and that a key contract file/dir for the test's domain is present.
Uses SimpleTestCase (no DB).
"""
from pathlib import Path
from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]
GEN = ROOT / "docs" / "generated"


def _artifact(name: str) -> Path:
    return GEN / name


class BarcodeVoucherContractTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("hyperlocal_finance_apm_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/finance/regional_payment_profiles.py"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class UsageMeteringQuotaLinkTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("tenant_resource_guardrails_audit.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/billing"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

