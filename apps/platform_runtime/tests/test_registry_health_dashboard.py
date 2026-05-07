from datetime import datetime, timezone

from django.test import SimpleTestCase

from apps.platform_runtime.registry_health import evaluate_registry_health


class RegistryHealthDashboardTests(SimpleTestCase):
    def test_registry_health_row_contains_operational_fields(self):
        result = evaluate_registry_health(
            [
                {
                    "name": "workflow_registry",
                    "owner": "Automation",
                    "scope": "both",
                    "route": "super:workflow_packs_catalog",
                    "proof": "apps/siteconfig/workflow_registry.py",
                    "test": "apps/siteconfig/tests/test_workflow_registry.py",
                    "generated_at": datetime.now(timezone.utc),
                }
            ],
            route_inventory={"super:workflow_packs_catalog"},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["rows"][0]["severity"], "ok")
        self.assertEqual(result["rows"][0]["primary_action"], "Monitor")
