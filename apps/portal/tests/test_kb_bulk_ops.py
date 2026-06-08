from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse


class ManagerKbBulkOpsTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.user = get_user_model().objects.create_superuser(
            username="kb_bulk_ops_admin",
            email="kb_bulk_ops@example.com",
            password="Test1234!",
        )

    @mock.patch("config.manager_kb_bulk_ops.run_import_docs_to_kb")
    def test_import_docs_post_stores_output(self, import_mock):
        import_mock.return_value = {"stdout": "imported 3 articles", "stderr": ""}
        self.client.force_login(self.user)
        url = reverse("manager_kb_bulk_ops")
        response = self.client.post(
            url,
            {
                "action": "import_docs",
                "category": "system-admin",
                "dry_run": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        import_mock.assert_called_once()
        follow = self.client.get(url)
        self.assertContains(follow, "imported 3 articles")

    @mock.patch("config.manager_kb_bulk_ops.run_generate_kb_odt")
    def test_generate_odt_post(self, generate_mock):
        generate_mock.return_value = {"stdout": "generated odt", "stderr": ""}
        self.client.force_login(self.user)
        url = reverse("manager_kb_bulk_ops")
        response = self.client.post(
            url,
            {"action": "generate_odt", "formats": "odt"},
        )
        self.assertEqual(response.status_code, 302)
        generate_mock.assert_called_once()
