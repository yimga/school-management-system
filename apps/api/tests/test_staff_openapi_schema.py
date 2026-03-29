"""Staff OpenAPI schema path: regression when tenant urls or DRF schema wiring changes."""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import set_urlconf

from apps.schools.models import School

from config.tenant_urls import schema_view

User = get_user_model()


class StaffOpenapiSchemaTests(TestCase):
    def test_staff_openapi_schema_returns_document(self):
        school = School.objects.create(
            name="Schema School",
            slug="schema-school",
            subdomain="schema-school",
            is_active=True,
        )
        user = User.objects.create_user(
            username="schema-staff",
            password="pass",
            is_staff=True,
        )
        request = RequestFactory().get("/api/schema/")
        request.user = user
        request.school = school
        set_urlconf("config.tenant_urls")
        try:
            response = schema_view(request)
        finally:
            set_urlconf(None)
        if hasattr(response, "render"):
            response.render()
        self.assertEqual(response.status_code, 200)
        body = response.content.decode().lower()
        self.assertIn("openapi", body)
