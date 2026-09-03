"""Studio OS routes open under manager urlconf (certification batch 1279)."""

import uuid

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.test_utils.http_clients import MANAGER_HOST, MANAGER_TEST_DEFAULTS, login_manager_client

_MGR_HOST = MANAGER_HOST

STUDIO_ROUTE_NAMES = (
    "studio_os:shell",
    "studio_os:experience",
    "studio_os:automation",
    "studio_os:output",
    "studio_os:launch",
    "studio_os:control",
    "studio_os:preview",
    "studio_os:global_search",
    "studio_os:recommendations",
    "studio_os:audit",
    "studio_os:rollback",
)


@override_settings(
    ALLOWED_HOSTS=["*", _MGR_HOST],
    **MANAGER_TEST_DEFAULTS,
)
class StudioOsWorldClassExperienceTests(TestCase):
    def setUp(self):
        password = "Test1234!"
        user = User.objects.create_user(
            username=f"studio_cp_{uuid.uuid4().hex[:8]}",
            password=password,
            role=User.Role.SUPERADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.client = login_manager_client(user, password=password, host=_MGR_HOST)

    def test_all_studio_routes_reverse(self):
        for name in STUDIO_ROUTE_NAMES:
            with self.subTest(name=name):
                path = reverse(name)
                self.assertTrue(path.startswith("/studio/"))

    def test_studio_shell_returns_200(self):
        response = self.client.get(reverse("studio_os:shell"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")
        self.assertNotIn('href="#"', body)
        self.assertNotIn("javascript:void", body)
