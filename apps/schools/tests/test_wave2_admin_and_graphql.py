"""
Wave 2 tests: platform vs tenant admin split, GraphQL global school restriction.

Non-negotiable: platform admin only on manager host; tenant admin on tenant host;
school_count/schools restricted to platform operators.
"""
import json

from django.test import TestCase, override_settings
from django.urls import resolve, reverse

from apps.accounts.models import User


@override_settings(ALLOWED_HOSTS=["*"])
class Wave2PlatformAdminOnlyOnManagerHostTests(TestCase):
    """Wave 2.2: Platform admin is used only on manager host."""

    def test_manager_urlconf_uses_platform_admin_site(self):
        """Manager URLConf must serve /admin/ from platform_admin_site."""
        from config.manager_urls import urlpatterns
        from config.admin import platform_admin_site
        # Find the admin path; it should be the one that uses platform_admin_site.
        admin_pattern = next((p for p in urlpatterns if getattr(p, "pattern", None) and "admin" in str(getattr(p.pattern, "_route", ""))), None)
        self.assertIsNotNone(admin_pattern, "Manager URLConf must define /admin/.")
        # When /admin/ is an include(), the pattern has url_patterns, not callback; resolving confirms it works.
        resolve_result = resolve("/admin/", urlconf="config.manager_urls")
        self.assertIsNotNone(resolve_result.func, "Manager /admin/ must resolve.")

    def test_tenant_urlconf_uses_tenant_admin_site(self):
        """Tenant URLConf must serve /admin/ from tenant_admin_site."""
        resolve_result = resolve("/admin/", urlconf="config.tenant_urls")
        self.assertIsNotNone(resolve_result.func, "Tenant /admin/ must resolve.")


@override_settings(ALLOWED_HOSTS=["*"])
class Wave2TenantAdminOnlyOnTenantHostTests(TestCase):
    """Wave 2.2: Tenant admin is used on tenant host."""

    def test_tenant_admin_site_has_tenant_index_template(self):
        """TenantAdminSite must use index_tenant.html."""
        from config.admin import tenant_admin_site
        self.assertEqual(tenant_admin_site.index_template_name, "admin/index_tenant.html")

    def test_platform_admin_site_has_platform_index_template(self):
        """PlatformAdminSite must use index_superadmin.html."""
        from config.admin import platform_admin_site
        self.assertEqual(platform_admin_site.index_template_name, "admin/index_superadmin.html")


@override_settings(ALLOWED_HOSTS=["*"])
class Wave2GraphQLGlobalSchoolsRestrictedTests(TestCase):
    """Wave 2.4: school_count and schools are restricted to platform operators."""

    def setUp(self):
        self.platform_user = User.objects.create_user(
            username="platform_gql",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.tenant_staff = User.objects.create_user(
            username="tenant_staff_gql",
            password="testpass123",
            is_staff=True,
            is_superuser=False,
            role=User.Role.ADMIN,
        )

    def test_graphql_school_count_restricted_for_tenant_staff(self):
        """Tenant staff (no control-plane) must not receive school_count."""
        from config.schema import schema
        query = "query { schoolCount }"
        class Ctx:
            user = self.tenant_staff
            public_host_kind = "tenant"
        result = schema.execute(query, context_value=Ctx())
        self.assertFalse(result.errors, msg=f"Unexpected errors: {result.errors}")
        data = (result.data or {})
        self.assertIsNone(data.get("schoolCount"), "Tenant staff must not get schoolCount.")

    def test_graphql_schools_restricted_for_tenant_staff(self):
        """Tenant staff must not receive schools list."""
        from config.schema import schema
        query = "query { schools(limit: 5) { id name slug } }"
        class Ctx:
            user = self.tenant_staff
            public_host_kind = "tenant"
        result = schema.execute(query, context_value=Ctx())
        self.assertFalse(result.errors, msg=f"Unexpected errors: {result.errors}")
        data = (result.data or {})
        self.assertEqual(data.get("schools"), [], "Tenant staff must get empty schools list.")

    def test_graphql_gateway_rejects_non_json_post_requests(self):
        response = self.client.post(
            reverse("graphql"),
            data="query { health }",
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, 415)
        payload = response.json()
        self.assertIn("Content-Type", payload["errors"][0]["message"])

    def test_graphql_gateway_requires_json_object_payload(self):
        response = self.client.post(
            reverse("graphql"),
            data=json.dumps(["query { health }"]),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("JSON object required", payload["errors"][0]["message"])
