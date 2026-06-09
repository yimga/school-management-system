"""API Center surfaces reverse and render for control-plane operators."""

import uuid

from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.test_utils.http_clients import MANAGER_HOST, MANAGER_TEST_DEFAULTS, login_manager_client

_MGR_HOST = MANAGER_HOST


@override_settings(
    ALLOWED_HOSTS=["*", _MGR_HOST],
    **MANAGER_TEST_DEFAULTS,
)
class ApiCenterOpenAndUsableTests(TransactionTestCase):
    def setUp(self):
        password = "Test1234!"
        user = User.objects.create_user(
            username=f"apicenter_cp_{uuid.uuid4().hex[:8]}",
            password=password,
            role=User.Role.SUPERADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.client = login_manager_client(user, password=password, host=_MGR_HOST)

    def test_apicenter_routes_reverse(self):
        for name in (
            "apicenter:dashboard",
            "apicenter:api_portal_docs",
            "apicenter:api_keys",
        ):
            with self.subTest(name=name):
                self.assertTrue(reverse(name).startswith("/api-center/"))

    def test_apicenter_dashboard_200(self):
        response = self.client.get(reverse("apicenter:dashboard"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")
        self.assertNotIn('href="#"', body)

    def test_apicenter_dashboard_uses_control_plane_shell_on_manager(self):
        response = self.client.get(reverse("apicenter:dashboard"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn('id="cp-main-content"', body)
        self.assertIn('id="cpSidebarNav"', body)
        self.assertIn("theme-platform-readability.css", body)
        self.assertIn(reverse("super:dashboard"), body)

    def test_api_schema_routes_exist(self):
        with override_settings(ROOT_URLCONF="config.urls"):
            self.assertEqual(reverse("api-schema"), "/api/schema/")
            self.assertEqual(reverse("api-schema-ui"), "/api/schema/ui/")

    def test_manager_api_key_create_flow(self):
        from apps.apicenter.models import APIKey

        create_url = reverse("apicenter:api_key_create")
        keys_url = reverse("apicenter:api_keys")
        response = self.client.post(
            create_url,
            {"name": "Developer console E2E"},
            HTTP_HOST=_MGR_HOST,
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("Developer console E2E", body)
        self.assertTrue(
            APIKey.objects.filter(name="Developer console E2E").exists()
        )
        list_response = self.client.get(keys_url, HTTP_HOST=_MGR_HOST)
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Developer console E2E")
