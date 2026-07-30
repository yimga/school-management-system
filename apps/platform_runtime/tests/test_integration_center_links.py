"""Configuration integrations hub links to API Center."""

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.test_utils.http_clients import login_manager_client

_MGR_HOST = "manager.runmycampus.com"


@override_settings(
    ROOT_URLCONF="config.urls",
    ALLOWED_HOSTS=["*", _MGR_HOST],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class IntegrationCenterLinksTests(TestCase):
    def setUp(self):
        operator = User.objects.create_user(
            username="integrations_cp",
            password="Test1234!",
            role=User.Role.SUPERADMIN,
            is_staff=True,
            is_superuser=True,
        )
        # Manager-host operator page: confirmed device + verified MFA on a
        # manager-bound session (a bare client.login bounces 302 to MFA setup).
        self.client = login_manager_client(operator, password="Test1234!", host=_MGR_HOST)

    def test_configuration_integrations_page_200(self):
        response = self.client.get("/configuration/integrations/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")
        with override_settings(ROOT_URLCONF="config.manager_urls"):
            apicenter_path = reverse("apicenter:dashboard")
        self.assertTrue(
            apicenter_path in body or "/api-center/" in body,
            "integrations page should reference API Center",
        )
