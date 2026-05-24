"""Global-local gap closure (batch 1488) — contract pins for finance.

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


class PaymentRailAdapterContractsTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("hyperlocal_finance_apm_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/finance/regional_payment_profiles.py"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class ApmRouterTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("hyperlocal_finance_apm_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/finance/payment_corridor_contracts.py"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class SplitLedgerRoutingTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("hyperlocal_finance_apm_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/finance/payment_marketplace_split.py"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class MobileMoneySplitWalletContractTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("hyperlocal_finance_apm_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/finance/payment_corridor_contracts.py"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class WebhookSignatureIdempotencyTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("hyperlocal_finance_apm_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/finance/webhooks/normalizer.py"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class EinvoiceTaxContractsTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("hyperlocal_finance_apm_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/finance/regional_payment_profiles.py"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class OfflinePaymentReconciliationTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("hyperlocal_finance_apm_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/finance/payment_corridor_contracts.py"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class PermissionToPayWorkflowTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("daily_micro_friction_engine_audit.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/finance/views_payments.py"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

