"""GraphQL gateway security contract (certification batch 1279)."""

import json

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from config.graphql_view import _INTROSPECTION_RE, _introspection_allowed


@override_settings(ALLOWED_HOSTS=["*"], GRAPHQL_INTROSPECTION_ENABLED=False, DEBUG=False)
class GraphQLSecurityReviewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant_staff = User.objects.create_user(
            username="graphql_tenant_staff",
            password="Test1234!",
            role=User.Role.ADMIN,
            is_staff=True,
        )

    def test_introspection_disabled_helper(self):
        self.assertFalse(_introspection_allowed())
        self.assertTrue(_INTROSPECTION_RE.search("{ __schema { queryType { name } } }"))

    def test_health_query_via_gateway(self):
        response = self.client.post(
            reverse("graphql"),
            data=json.dumps({"query": "{ health }"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("data", {}).get("health"), "ok")

    def test_introspection_blocked_on_gateway_post(self):
        response = self.client.post(
            reverse("graphql"),
            data=json.dumps({"query": "{ __schema { queryType { name } } }"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_school_count_restricted_for_tenant_staff(self):
        from config.schema import schema

        class Ctx:
            user = self.tenant_staff
            public_host_kind = "tenant"

        result = schema.execute("query { schoolCount }", context_value=Ctx())
        self.assertFalse(result.errors)
        self.assertIsNone((result.data or {}).get("schoolCount"))
