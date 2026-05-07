from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from apps.platform_runtime.metadata_governance import detect_metadata_drift


class MetadataDriftDetectionTests(SimpleTestCase):
    def test_detects_missing_owner_proof_test_and_stale_generation(self):
        result = detect_metadata_drift(
            [{"name": "metadata_registry", "scope": "platform"}],
            generated_at=datetime.now(timezone.utc) - timedelta(hours=72),
        )

        self.assertFalse(result["ok"])
        self.assertTrue(result["stale_generated_artifact"])
        self.assertEqual(result["finding_count"], 1)
        self.assertIn("owner", result["findings"][0]["missing"])
        self.assertIn("proof", result["findings"][0]["missing"])
        self.assertIn("test", result["findings"][0]["missing"])
