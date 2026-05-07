from __future__ import annotations

from django.test import Client, TestCase, override_settings

from apps.accounts.models import User
from apps.platform_runtime.models import ConfigurationChangeRequest
from apps.schools.models import School


@override_settings(
    ALLOWED_HOSTS=["*", "tenant-boundary.runmycampus.com", "other-boundary.runmycampus.com"],
    ROOT_URLCONF="config.urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class TenantChangeRequestBoundaryTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Tenant Boundary", slug="tenant-boundary", subdomain="tenant-boundary", is_active=True)
        self.other = School.objects.create(name="Other Boundary", slug="other-boundary", subdomain="other-boundary", is_active=True)
        self.admin = User.objects.create_user(username="tenant_boundary_admin", password="x" * 8, role=User.Role.ADMIN, is_staff=True)

    def test_tenant_high_risk_pack_creates_request_not_install(self):
        client = Client(HTTP_HOST="tenant-boundary.runmycampus.com", raise_request_exception=False)
        client.login(username="tenant_boundary_admin", password="x" * 8)

        response = client.post("/school/setup/packs/", {"pack": "network-operator", "pack_type": "dashboard_pack"})

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        self.assertTrue(ConfigurationChangeRequest.objects.filter(school=self.school, target_key="network-operator").exists())

    def test_tenant_cannot_see_other_tenant_request_in_queryset_contract(self):
        ConfigurationChangeRequest.objects.create(
            school=self.other,
            request_type=ConfigurationChangeRequest.RequestType.PACK_APPLY,
            target_key="network-operator",
            target_type="dashboard_pack",
            target_version="1.0.0",
            status=ConfigurationChangeRequest.Status.PENDING_APPROVAL,
            idempotency_key="other-request",
        )

        visible = ConfigurationChangeRequest.objects.filter(school=self.school)

        self.assertFalse(visible.exists())
