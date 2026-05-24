"""Global-local gap closure (batch 1488) — contract pins for orchestration.

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


class TenantRateLimitHoldQueueTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("tenant_resource_guardrails_audit.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/orchestration"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

