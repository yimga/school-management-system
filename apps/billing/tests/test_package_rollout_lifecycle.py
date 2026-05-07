from django.test import SimpleTestCase

from apps.platform_runtime.package_rollout import package_change_request


class PackageRolloutLifecycleTests(SimpleTestCase):
    def test_change_request_requires_preview_approval_effective_date_and_audit(self):
        request = package_change_request(
            {"version": "starter-1", "modules": ["people"], "limits": {"students": 100}, "price": "50"},
            {"version": "growth-1", "modules": ["people", "finance"], "limits": {"students": 250}, "price": "150"},
            tenant_id="school-a",
        )

        self.assertTrue(request["preview_required"])
        self.assertTrue(request["approval_required"])
        self.assertTrue(request["effective_date_required"])
        self.assertTrue(request["auditable"])
        self.assertIn("finance", request["package_diff"]["modules_added"])
