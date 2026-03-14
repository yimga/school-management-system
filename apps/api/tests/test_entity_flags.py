from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.platform_runtime.helpers import get_platform_site_settings_record


class EntityFeatureFlagTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="admin",
            password="pass",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.client.force_authenticate(user=self.admin)
        self.site = get_platform_site_settings_record(create=True)

    def test_bulk_commit_respects_flag(self):
        self.site.backend_feature_flags = {"allow_bulk_commit": False}
        self.site.save()
        resp = self.client.post("/api/entities/students/bulk-commit/", {"rows": []}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("disabled", resp.json().get("error", "").lower())

    def test_bulk_preview_row_limit(self):
        self.site.backend_feature_flags = {"max_bulk_import_rows": 1}
        self.site.save()
        csv_body = "first_name,last_name\nA,B\nC,D"
        resp = self.client.post("/api/entities/students/bulk-preview/", {"csv": csv_body}, format="json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(any("Row limit" in err.get("error", "") for err in data.get("errors", [])))
