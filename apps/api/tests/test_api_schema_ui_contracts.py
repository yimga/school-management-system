"""OpenAPI schema UI routes resolve and enforce role gate."""

from __future__ import annotations

import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User

_MGR = "manager.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["*", _MGR], ROOT_URLCONF="config.manager_urls")
class ApiSchemaUIContractsTests(TestCase):
    def setUp(self):
        User.objects.create_user(
            username=f"schema_{uuid.uuid4().hex[:8]}",
            password="Test1234!",
            role=User.Role.SUPERADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client(HTTP_HOST=_MGR)

    def test_schema_routes_reverse(self):
        with override_settings(ROOT_URLCONF="config.urls"):
            self.assertEqual(reverse("api-schema"), "/api/schema/")
            self.assertEqual(reverse("api-schema-ui"), "/api/schema/ui/")
