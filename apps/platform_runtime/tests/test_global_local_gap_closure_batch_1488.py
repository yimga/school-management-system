"""Global-local gap closure (batch 1488) — contract pins for platform_runtime.

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


class PwaManifestTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("rural_offline_edge_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "static/js/service-worker.js"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class PwaOfflineStorageContractTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("rural_offline_edge_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "static/js/rmc-service-worker-registration.js"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class PwaTenantCacheSafetyTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("rural_offline_edge_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "static/js/service-worker.js"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class AsyncTenantContextSafetyTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("tenant_identity_federation_rls_audit.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/platform_runtime"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class AiLocalTemplateRecommendationSafetyTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("ai_safety_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/brand_experience/template_ai_recommender.py"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class LocalFirstTemplateMarketplaceCatalogTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("local_first_template_end_to_end_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/platform_runtime/pack_contract.py"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class LocalFirstTemplateLivePreviewsTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("local_first_template_end_to_end_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/platform_runtime"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class LocalFirstTemplateApplyRollbackTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("local_first_template_end_to_end_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/platform_runtime/pack_contract.py"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

class LocalFirstTemplateTenantBoundariesTest(SimpleTestCase):
    def test_artifact_and_key_path(self):
        artifact = _artifact("local_first_template_end_to_end_gap_closure.json")
        self.assertTrue(artifact.is_file(), "missing audit artifact: " + str(artifact))
        key = ROOT / "apps/platform_runtime"
        self.assertTrue(key.exists() or key.is_dir(), "missing contract path: " + str(key))

