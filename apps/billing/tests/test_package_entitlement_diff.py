from django.test import SimpleTestCase

from apps.platform_runtime.package_rollout import package_diff


class PackageEntitlementDiffTests(SimpleTestCase):
    def test_diff_records_modules_limits_support_and_access_changes(self):
        diff = package_diff(
            {"version": "pro-1", "modules": ["people", "api"], "limits": {"api_calls": 1000}, "api_access": True},
            {"version": "starter-1", "modules": ["people"], "limits": {"api_calls": 0}, "api_access": False},
        )

        self.assertIn("api", diff["modules_removed"])
        self.assertEqual(diff["limits_changed"]["api_calls"]["from"], 1000)
        self.assertFalse(diff["api_access_changed"] is False)
