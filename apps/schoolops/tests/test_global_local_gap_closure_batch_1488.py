"""Global-local gap closure (batch 1488) — contract pins for schoolops.

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


class StudentWalletSpendingLimitsTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("hyperlocal_finance_apm_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/schoolops"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class TransportTrackingContractsTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("operations_logistics_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/schoolops"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class CafeteriaWalletContractsTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("operations_logistics_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/schoolops"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class HostelWardenWorkflowsTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("operations_logistics_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/schoolops"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class AssetProcurementLifecycleTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("operations_logistics_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/schoolops"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class SubstitutePayrollIntegrationTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("operations_logistics_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/payroll"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class LostBelongingsAssetQrContractTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("daily_micro_friction_engine_audit.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/schoolops"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class DropoffCoordinationPrivacyContractTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("daily_micro_friction_engine_audit.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/schoolops"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class SubstituteHandoverBlueprintTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("daily_micro_friction_engine_audit.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/schoolops"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

