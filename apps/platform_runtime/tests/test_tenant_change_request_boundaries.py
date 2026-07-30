from __future__ import annotations

from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.platform_runtime.models import ConfigurationChangeRequest
from apps.schools.models import School
from apps.test_utils.http_clients import login_tenant_admin_client


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

    def _admin_client(self):
        # A tenant ADMIN reaching this tenant-host page must carry a SchoolMembership
        # (else OperatorTenantConfinementMiddleware confines the is_staff user to
        # manager/super/ → 302) plus a confirmed TOTP device + verified session.
        return login_tenant_admin_client(
            self.admin,
            password="x" * 8,
            host="tenant-boundary.runmycampus.com",
            school=self.school,
        )

    def test_tenant_high_risk_pack_creates_request_not_install(self):
        client = self._admin_client()

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
