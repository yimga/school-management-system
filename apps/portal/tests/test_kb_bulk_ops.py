from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.portal.kb_bulk_ops_service import run_generate_kb_odt, run_import_docs_to_kb


class KbBulkOpsServiceTests(SimpleTestCase):
    @mock.patch("apps.portal.kb_bulk_ops_service.call_command")
    def test_run_import_docs_to_kb_invokes_command(self, cmd_mock):
        result = run_import_docs_to_kb(category="guides", dry_run=True, generate_odt=True)
        cmd_mock.assert_called_once()
        self.assertIn("stdout", result)

    @mock.patch("apps.portal.kb_bulk_ops_service.call_command")
    def test_run_generate_kb_odt_all_flag(self, cmd_mock):
        run_generate_kb_odt(formats="odt", overwrite=True)
        cmd_mock.assert_called_once()
        _, kwargs = cmd_mock.call_args
        self.assertTrue(kwargs.get("all"))


class ManagerKbBulkOpsRouteTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.user = get_user_model().objects.create_superuser(
            username="kb_bulk_ops_admin",
            email="kb_bulk_ops@example.com",
            password="Test1234!",
        )

    @override_settings(ROOT_URLCONF="config.manager_urls", ALLOWED_HOSTS=["*"])
    def test_manager_kb_bulk_ops_get_renders(self):
        self.client.force_login(self.user)
        url = reverse("manager_kb_bulk_ops")
        response = self.client.get(url, HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "import_docs")

    @override_settings(ROOT_URLCONF="config.manager_urls")
    def test_manager_kb_bulk_ops_url_resolves(self):
        url = reverse("manager_kb_bulk_ops")
        self.assertIn("kb-bulk-ops", url)
