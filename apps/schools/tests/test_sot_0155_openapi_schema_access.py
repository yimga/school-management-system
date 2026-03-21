"""§0.1.5 Serious B2: OpenAPI/schema access is login + role gated."""

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User


@override_settings(ALLOWED_HOSTS=["*"])
class OpenApiSchemaAccessSot0155Tests(TestCase):
    def test_schema_json_redirects_when_anonymous(self):
        r = self.client.get(reverse("api-schema"))
        self.assertIn(r.status_code, (302, 403))

    def test_schema_json_allows_superuser(self):
        u = User.objects.create_user(
            username="schema_u",
            password="pw",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(u)
        r = self.client.get(reverse("api-schema"))
        self.assertEqual(r.status_code, 200)
        body = r.content.lower()
        self.assertTrue(
            b"openapi" in body or b"paths" in body or b"swagger" in body,
            "Schema response should look like OpenAPI",
        )

    def test_schema_ui_allows_superuser(self):
        u = User.objects.create_user(
            username="schema_ui_u",
            password="pw",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(u)
        r = self.client.get(reverse("api-schema-ui"))
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"schema", r.content.lower())

    def test_schema_ui_forbidden_for_non_staff(self):
        u = User.objects.create_user(username="plain", password="pw")
        self.client.force_login(u)
        r = self.client.get(reverse("api-schema-ui"))
        self.assertIn(r.status_code, (302, 403))
