from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from apps.platform_runtime.registry_health import evaluate_registry_health


class RegistryDriftDetectionTests(SimpleTestCase):
    def test_registry_drift_detects_missing_route_owner_proof_and_tests(self):
        result = evaluate_registry_health(
            [
                {
                    "name": "billing_sku_registry",
                    "scope": "platform_only",
                    "route": "super:missing",
                    "generated_at": datetime.now(timezone.utc) - timedelta(hours=48),
                }
            ],
            route_inventory={"super:billing_dashboard"},
        )

        row = result["rows"][0]
        self.assertFalse(result["ok"])
        self.assertTrue(row["drift_detected"])
        self.assertTrue(row["missing_owner"])
        self.assertTrue(row["missing_proof"])
        self.assertTrue(row["missing_tests"])
        self.assertEqual(row["severity"], "high")
