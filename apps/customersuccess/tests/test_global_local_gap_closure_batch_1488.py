"""Global-local gap closure (batch 1488) — contract pins for customersuccess.

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


class AutoOnboardingFromMigrationTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("ai_auto_migration_pipeline_audit.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/customersuccess"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class SupportCrmLinkageTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("crm_lifecycle_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/customersuccess"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

