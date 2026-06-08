"""Operator SMTP configure form exposes secret visibility toggles."""

import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.tests.manager_client import login_manager_control_plane

_MANAGER_HOST = "manager.runmycampus.com"
_PASSWORD = "testpass123"


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", _MANAGER_HOST],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SECURE_SSL_REDIRECT=False,
    ROOT_URLCONF="config.manager_urls",
    SESSION_PINNING_ENABLED=False,
    OPERATOR_MFA_REQUIRED_ON_MANAGER=False,
)
class EmailConfigureSecretToggleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username=f"email_cfg_{uuid.uuid4().hex[:8]}",
            password=_PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client(HTTP_HOST=_MANAGER_HOST)
        login_manager_control_plane(
            self.client,
            self.user,
            password=_PASSWORD,
            host=_MANAGER_HOST,
        )

    def test_email_configure_renders_password_toggles(self):
        url = reverse("super:email_configure")
        response = self.client.get(url, HTTP_HOST=_MANAGER_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(
            response.content.count(b"data-rmc-password-toggle"),
            5,
            msg="SMTP password + four webhook secrets should each have a toggle",
        )
