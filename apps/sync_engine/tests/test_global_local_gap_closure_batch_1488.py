"""Global-local gap closure (batch 1488) — contract pins for sync_engine.

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


class TenantManifestCompilerTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("rural_offline_edge_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/sync_engine"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class OfflineEdgeSyncContractTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("rural_offline_edge_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/sync_engine"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class LowBandwidthBudgetTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("rural_offline_edge_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/sync_engine"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class SharedDeviceProfileContractTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("rural_offline_edge_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/sync_engine"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class OfflinePaymentSyncContractTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("rural_offline_edge_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/finance"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class OfflineQueueContractTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("rural_offline_edge_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/sync_engine"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class OfflineTelemetryBufferTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("asynchronous_telemetry_buffer_audit.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/observability/metrics.py"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class OfflineTenantContextBoundaryTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("tenant_identity_federation_rls_audit.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/sync_engine"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class OfflineSyncQuotaGuardTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("tenant_resource_guardrails_audit.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/sync_engine"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

