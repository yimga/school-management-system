from django.test import SimpleTestCase

from apps.platform_runtime.package_rollout import package_change_request


class PackageChangeRequestFlowTests(SimpleTestCase):
    def test_downgrade_explains_lost_features_and_data_impact(self):
        request = package_change_request(
            {"version": "enterprise", "modules": ["people", "api", "analytics"], "limits": {"students": 1000}, "price": "500"},
            {"version": "starter", "modules": ["people"], "limits": {"students": 100}, "price": "50"},
            tenant_id="school-a",
        )

        self.assertTrue(request["downgrade"])
        self.assertEqual(request["downgrade_posture"], "explain_lost_features_and_data_impact")
        self.assertEqual(request["billing_impact"]["external_psp_state"], "external_required")
