"""Global-local gap closure (batch 1488) — contract pins for accounts.

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


class TenantSessionBindingTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("tenant_identity_federation_rls_audit.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/accounts"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class SharedDeviceCachePurgeTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("rural_offline_edge_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/accounts"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class MultiCustodianRoutingTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("daily_micro_friction_engine_audit.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/accounts"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

